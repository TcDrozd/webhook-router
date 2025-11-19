# Lightweight Two-Tier Webhook Ingress

A simple, secure webhook proxy system for homelab environments. Accept webhooks on a public edge server and route them securely to internal services over Tailscale.

## Architecture

```
Internet → Edge (Oracle VM) → Tailscale → Router (Home LAN) → Internal Services
           [nginx + HTTPS]                 [100.x.x.x]          [192.168.x.x]
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local dev)
- Tailscale network configured

### 1. Clone and Configure

```bash
git clone <your-repo>
cd webhook-ingress

# Copy example configs
cp edge/.env.example edge/.env
cp router/.env.example router/.env
cp router/routes.yaml.example router/routes.yaml

# Edit with your values
nano edge/.env
nano router/.env
nano router/routes.yaml
```

### 2. Local Testing (Both services on localhost)

```bash
# Start both services
docker-compose up --build

# Test the full chain
./test-local.sh
```

### 3. Production Deployment

#### Edge Service (Oracle VM)

```bash
cd edge
docker build -t webhook-edge .
docker run -d \
  --name webhook-edge \
  --restart unless-stopped \
  -p 8080:8080 \
  --env-file .env \
  webhook-edge
```

Configure nginx to proxy HTTPS → `http://localhost:8080`

#### Router Service (Home LAN)

```bash
cd router
docker build -t webhook-router .
docker run -d \
  --name webhook-router \
  --restart unless-stopped \
  -p 8081:8080 \
  --env-file .env \
  -v $(pwd)/routes.yaml:/app/routes.yaml:ro \
  webhook-router
```

Bind to Tailscale IP: `-p 100.x.x.x:8081:8080`

## Configuration

### Edge Service (.env)

```bash
# Comma-separated list of valid edge keys
# Format: key_name:key_value,key_name2:key_value2
EDGE_KEYS=alice:edge_abc123,bob:edge_xyz789

# Router endpoint (Tailscale IP)
ROUTER_URL=http://100.64.1.5:8081/ingest

# Shared secret for edge→router auth
ROUTER_INGRESS_KEY=router_secret_def456

# Optional settings
REQUEST_TIMEOUT=30
MAX_BODY_SIZE_MB=1
RATE_LIMIT_PER_MINUTE=100
```

### Router Service (.env)

```bash
# Shared secret (must match edge ROUTER_INGRESS_KEY)
ROUTER_INGRESS_KEY=router_secret_def456

# Optional per-destination auth tokens
GITHUB_SERVICE_TOKEN=optional_token_123
HOMEASSISTANT_TOKEN=optional_token_456
```

### Router Service (routes.yaml)

```yaml
destinations:
  github-handler:
    method: POST
    url: http://192.168.1.50:3000/webhooks/github
    auth_env: GITHUB_SERVICE_TOKEN  # Optional
    timeout_seconds: 25

  home-assistant:
    method: POST
    url: http://192.168.1.100:8123/api/webhook/my-id
    timeout_seconds: 10

  custom-service:
    method: POST
    url: http://192.168.1.75:5000/events
    # No auth needed
```

## Usage

### Sending a Webhook

```bash
curl -X POST https://your-edge-domain.com/webhook \
  -H "Authorization: Bearer edge_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "destination": "github-handler",
    "payload": {
      "event": "push",
      "data": "your webhook data here"
    }
  }'
```

### Adding Team Members

Edit `edge/.env`:
```bash
EDGE_KEYS=alice:edge_abc123,bob:edge_xyz789,charlie:edge_new_key_999
```

Restart edge service. Each person uses their own key; router logs will show which key was used.

## Security Notes

- **EDGE_KEYS**: Distribute to external services/team members (rotatable)
- **ROUTER_INGRESS_KEY**: Never leaves your infrastructure
- **Per-destination tokens**: Optional auth for internal services
- All keys should be random, high-entropy strings (use `openssl rand -hex 32`)
- Never commit `.env` files to git
- Router should only listen on Tailscale interface in production

## Monitoring

### Health Checks

```bash
# Edge
curl http://localhost:8080/health

# Router
curl http://localhost:8081/health
```

### Logs

Both services output structured JSON logs with correlation IDs:

```json
{
  "timestamp": "2025-01-15T10:30:45Z",
  "level": "info",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "service": "edge",
  "edge_key": "alice",
  "message": "Forwarding to router",
  "destination": "github-handler"
}
```

View logs:
```bash
docker logs -f webhook-edge
docker logs -f webhook-router
```

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success - internal service responded OK |
| 400 | Bad Request - missing destination or invalid JSON |
| 401 | Unauthorized - invalid/missing bearer token |
| 404 | Not Found - unknown destination |
| 500 | Internal Error - edge/router failure |
| 502 | Bad Gateway - internal service returned error |
| 504 | Gateway Timeout - internal service timeout |

## Troubleshooting

### Edge can't reach router
- Check Tailscale connectivity: `tailscale ping 100.x.x.x`
- Verify ROUTER_URL in edge/.env
- Check router is listening: `netstat -tlnp | grep 8081`

### Router can't reach internal service
- Verify URL in routes.yaml
- Check internal service is running
- Test manually: `curl http://192.168.1.50:3000/webhooks/github`

### Authentication failures
- Check ROUTER_INGRESS_KEY matches in both .env files
- Verify EDGE_KEYS format (no spaces around colons/commas)
- Check Authorization header format: `Bearer <key>`

## File Structure

```
webhook-ingress/
├── edge/
│   ├── app.py              # Edge service
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                # (gitignored)
├── router/
│   ├── app.py              # Router service
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── .env                # (gitignored)
│   ├── routes.yaml.example
│   └── routes.yaml         # (gitignored)
├── docker-compose.yml      # Local testing
├── test-local.sh           # Test script
└── README.md
```

## Next Steps

After MVP is running:
- Add Prometheus metrics endpoints
- Set up Grafana dashboards
- Add request/response body logging (debug mode)
- Implement hot-reload for routes.yaml
- Add webhook signature verification for external providers