#!/bin/bash
set -e

echo "🧪 Testing Webhook Ingress System"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Host URLs. Defaults match docker-compose.example.yml, which publishes the
# edge on 8090 and the router on 8091. Override for other setups:
#   EDGE_URL=http://localhost:8080 ./test_script.sh
EDGE_URL="${EDGE_URL:-http://localhost:8090}"
ROUTER_URL="${ROUTER_URL:-http://localhost:8091}"

if [ ! -f "edge/.env" ]; then
    echo -e "${RED}❌ edge/.env not found${NC}"
    exit 1
fi

# Read a KEY=value from edge/.env, tolerating '=' inside the value.
env_value() {
    grep -E "^${1}=" edge/.env | tail -n1 | cut -d'=' -f2-
}

# Edge keys are file-backed via EDGE_KEYS_FILE. The file is a JSON object of
# {owner: token}; any token in it is a valid bearer credential.
KEYS_FILE="${EDGE_KEYS_FILE:-$(env_value EDGE_KEYS_FILE)}"
if [ -z "$KEYS_FILE" ]; then
    KEYS_FILE="secrets/edge_keys.json"
fi

if [ ! -f "$KEYS_FILE" ]; then
    echo -e "${RED}❌ Edge keys file not found: $KEYS_FILE${NC}"
    echo "   Set EDGE_KEYS_FILE in edge/.env to a host-readable path,"
    echo "   or export EDGE_KEYS_FILE before running this script."
    exit 1
fi

EDGE_KEY=$(python3 -c '
import json, sys
with open(sys.argv[1]) as f:
    keys = json.load(f)
tokens = [t for t in keys.values() if isinstance(t, str) and t.strip()]
print(tokens[0] if tokens else "")
' "$KEYS_FILE")

if [ -z "$EDGE_KEY" ]; then
    echo -e "${RED}❌ Could not extract an edge key from $KEYS_FILE${NC}"
    exit 1
fi

TAILSCALE_SECRET="${TAILSCALE_WEBHOOK_SECRET:-$(env_value TAILSCALE_WEBHOOK_SECRET)}"

echo "Edge:   $EDGE_URL"
echo "Router: $ROUTER_URL"
echo "Using edge key: ${EDGE_KEY:0:10}... (from $KEYS_FILE)"
echo ""

# Test 1: Health checks
echo -e "${YELLOW}Test 1: Health Checks${NC}"
echo "---"

echo -n "Edge health check... "
EDGE_HEALTH=$(curl -s "$EDGE_URL/health")
if echo "$EDGE_HEALTH" | grep -q "healthy"; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    echo "$EDGE_HEALTH"
    exit 1
fi

echo -n "Router health check... "
ROUTER_HEALTH=$(curl -s "$ROUTER_URL/health")
if echo "$ROUTER_HEALTH" | grep -q "healthy"; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    echo "$ROUTER_HEALTH"
    exit 1
fi

echo ""

# Test 2: Unauthorized request
echo -e "${YELLOW}Test 2: Unauthorized Request${NC}"
echo "---"

echo -n "Request without auth header... "
RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/test_response.json \
    -X POST "$EDGE_URL/webhook" \
    -H "Content-Type: application/json" \
    -d '{"destination":"test","payload":{}}')

if [ "$RESPONSE" = "401" ]; then
    echo -e "${GREEN}✓ PASS (401 Unauthorized)${NC}"
else
    echo -e "${RED}✗ FAIL (Expected 401, got $RESPONSE)${NC}"
    cat /tmp/test_response.json
    exit 1
fi

echo ""

# Test 3: Invalid bearer token
echo -e "${YELLOW}Test 3: Invalid Bearer Token${NC}"
echo "---"

echo -n "Request with invalid token... "
RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/test_response.json \
    -X POST "$EDGE_URL/webhook" \
    -H "Authorization: Bearer invalid_token" \
    -H "Content-Type: application/json" \
    -d '{"destination":"test","payload":{}}')

if [ "$RESPONSE" = "401" ]; then
    echo -e "${GREEN}✓ PASS (401 Unauthorized)${NC}"
else
    echo -e "${RED}✗ FAIL (Expected 401, got $RESPONSE)${NC}"
    cat /tmp/test_response.json
    exit 1
fi

echo ""

# Test 4: Missing destination
echo -e "${YELLOW}Test 4: Missing Destination Field${NC}"
echo "---"

echo -n "Request without destination... "
RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/test_response.json \
    -X POST "$EDGE_URL/webhook" \
    -H "Authorization: Bearer $EDGE_KEY" \
    -H "Content-Type: application/json" \
    -d '{"payload":{"test":"data"}}')

if [ "$RESPONSE" = "400" ]; then
    echo -e "${GREEN}✓ PASS (400 Bad Request)${NC}"
else
    echo -e "${RED}✗ FAIL (Expected 400, got $RESPONSE)${NC}"
    cat /tmp/test_response.json
    exit 1
fi

echo ""

# Test 5: Unknown destination
echo -e "${YELLOW}Test 5: Unknown Destination${NC}"
echo "---"

echo -n "Request to non-existent destination... "
RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/test_response.json \
    -X POST "$EDGE_URL/webhook" \
    -H "Authorization: Bearer $EDGE_KEY" \
    -H "Content-Type: application/json" \
    -d '{"destination":"does-not-exist","payload":{"test":"data"}}')

if [ "$RESPONSE" = "404" ]; then
    echo -e "${GREEN}✓ PASS (404 Not Found)${NC}"
else
    echo -e "${RED}✗ FAIL (Expected 404, got $RESPONSE)${NC}"
    cat /tmp/test_response.json
    exit 1
fi

echo ""

# Test 6: Tailscale ingress
echo -e "${YELLOW}Test 6: Tailscale Ingress${NC}"
echo "---"

TS_BODY='[{"timestamp":"2022-09-21T13:37:51.658918-04:00","version":1,"type":"test","tailnet":"example.com","message":"This is a test event","data":null}]'

echo -n "Request with an invalid signature... "
RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/test_response.json \
    -X POST "$EDGE_URL/tailscale" \
    -H "Tailscale-Webhook-Signature: t=$(date +%s),v1=$(printf 'a%.0s' {1..64})" \
    -H "Content-Type: application/json" \
    -d "$TS_BODY")

if [ -z "$TAILSCALE_SECRET" ] && [ "$RESPONSE" = "503" ]; then
    echo -e "${GREEN}✓ PASS (503, Tailscale ingress not configured)${NC}"
elif [ "$RESPONSE" = "401" ]; then
    echo -e "${GREEN}✓ PASS (401 Unauthorized)${NC}"
else
    echo -e "${RED}✗ FAIL (Expected 401, got $RESPONSE)${NC}"
    cat /tmp/test_response.json
    exit 1
fi

if [ -z "$TAILSCALE_SECRET" ]; then
    echo -e "${YELLOW}⊘ SKIP signed request - TAILSCALE_WEBHOOK_SECRET not set in edge/.env${NC}"
else
    echo -n "Request with a valid signature... "
    TS_TIMESTAMP=$(date +%s)
    # string_to_sign is "<timestamp>.<raw body>"; printf avoids the trailing
    # newline that echo would append and that would break the HMAC.
    TS_SIGNATURE=$(printf '%s.%s' "$TS_TIMESTAMP" "$TS_BODY" \
        | openssl dgst -sha256 -hmac "$TAILSCALE_SECRET" -r | cut -d' ' -f1)

    RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/test_response.json \
        -X POST "$EDGE_URL/tailscale" \
        -H "Tailscale-Webhook-Signature: t=$TS_TIMESTAMP,v1=$TS_SIGNATURE" \
        -H "Content-Type: application/json" \
        -d "$TS_BODY")

    # The signature is what is under test here. A 404 means the edge accepted
    # the request and the router simply has no 'tailscale' destination yet.
    if [ "$RESPONSE" = "401" ]; then
        echo -e "${RED}✗ FAIL (signature rejected)${NC}"
        cat /tmp/test_response.json
        exit 1
    elif [ "$RESPONSE" = "404" ]; then
        echo -e "${GREEN}✓ PASS (signature accepted; add a 'tailscale' destination to routes.yml)${NC}"
    else
        echo -e "${GREEN}✓ PASS (signature accepted, router returned $RESPONSE)${NC}"
    fi
fi

echo ""

# Test 7: Valid request (if you have a test destination configured)
echo -e "${YELLOW}Test 7: Valid Request (if configured)${NC}"
echo "---"
echo "To test a valid request, ensure you have a destination configured in router/routes.yml"
echo "Then run:"
echo ""
echo "  curl -X POST $EDGE_URL/webhook \\"
echo "    -H \"Authorization: Bearer $EDGE_KEY\" \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{\"destination\":\"your-destination\",\"payload\":{\"test\":\"data\"}}'"
echo ""

# Cleanup
rm -f /tmp/test_response.json

echo ""
echo -e "${GREEN}✅ All tests passed!${NC}"
echo ""
echo "Next steps:"
echo "  1. Configure your routes in router/routes.yml"
echo "  2. Test with real internal services"
echo "  3. Deploy edge to Oracle VM"
echo "  4. Deploy router to homelab"
