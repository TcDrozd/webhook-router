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

# Load edge key from .env
if [ ! -f "edge/.env" ]; then
    echo -e "${RED}❌ edge/.env not found${NC}"
    exit 1
fi

EDGE_KEY=$(grep EDGE_KEYS edge/.env | cut -d'=' -f2 | cut -d',' -f1 | cut -d':' -f2)

if [ -z "$EDGE_KEY" ]; then
    echo -e "${RED}❌ Could not extract EDGE_KEY from edge/.env${NC}"
    exit 1
fi

echo "Using edge key: ${EDGE_KEY:0:10}..."
echo ""

# Test 1: Health checks
echo -e "${YELLOW}Test 1: Health Checks${NC}"
echo "---"

echo -n "Edge health check... "
EDGE_HEALTH=$(curl -s http://localhost:8080/health)
if echo "$EDGE_HEALTH" | grep -q "healthy"; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
    echo "$EDGE_HEALTH"
    exit 1
fi

echo -n "Router health check... "
ROUTER_HEALTH=$(curl -s http://localhost:8081/health)
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
    -X POST http://localhost:8080/webhook \
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
    -X POST http://localhost:8080/webhook \
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
    -X POST http://localhost:8080/webhook \
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
    -X POST http://localhost:8080/webhook \
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

# Test 6: Valid request (if you have a test destination configured)
echo -e "${YELLOW}Test 6: Valid Request (if configured)${NC}"
echo "---"
echo "To test a valid request, ensure you have a destination configured in routes.yaml"
echo "Then run:"
echo ""
echo "  curl -X POST http://localhost:8080/webhook \\"
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
echo "  1. Configure your routes in router/routes.yaml"
echo "  2. Test with real internal services"
echo "  3. Deploy edge to Oracle VM"
echo "  4. Deploy router to homelab"