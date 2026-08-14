# Lightweight Two-Tier Webhook Ingress

A simple, secure webhook proxy system for homelab environments. Accept webhooks on a public edge server and route them securely to internal services over Tailscale.

## Architecture

```
Internet → Edge (Oracle VM) → Tailscale → Router (Home LAN) → Internal Services
           [nginx + HTTPS]                 [100.x.x.x]          [192.168.x.x]
```

The edge exposes one or more **ingress adapters**. Each adapter authenticates
and parses one external protocol, then reduces the request to a canonical
`{destination, payload}` message. Everything past that point is identical
regardless of which adapter handled the request, and the router never learns
which one did.

```
external request
       │
       ▼
┌─────────────────────┐
│   ingress adapter   │   native     → Bearer token + {destination, payload}
│                     │   tailscale  → Tailscale-Webhook-Signature + event batch
└──────────┬──────────┘
           ▼
    IngressMessage(destination, payload, source)
           ▼
     RouterForwarder            (adds ROUTER_INGRESS_KEY)
═══════════╪══════════ tailnet boundary
           ▼
     router /ingest → routes.yml → internal destination
```

Use the **native** adapter whenever the caller can send a bearer token and our
envelope. A provider-specific adapter is only justified when the external
service dictates authentication or payload shape we cannot control.

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local dev)
- Tailscale network configured

### 1. Clone and Configure

```bash
git clone <your-repo>
cd webhook-router

# Copy example configs
cp edge/.env.example edge/.env
cp router/.env.example router/.env
cp router/routes.yml.example router/routes.yml
cp secrets/edge_keys.example.json secrets/edge_keys.json
cp docker-compose.example.yml docker-compose.yml

# Edit with your values
nano edge/.env
nano router/.env
nano router/routes.yml
nano secrets/edge_keys.json
```

### 2. Local Testing

```bash
# Start both services
docker compose --profile edge --profile router up --build

# Smoke-test the full chain (curl against running containers)
./test_script.sh

# Unit tests (no containers required)
pip install -r requirements-dev.txt -r edge/requirements.txt -r router/requirements.txt
./run_tests.sh
```

### 3. Production Deployment

#### Edge Service (Oracle VM)

```bash
cd edge
docker build -t webhook-edge .
docker run -d \
  --name webhook-edge \
  --restart unless-stopped \
  -p 127.0.0.1:8090:8080 \
  --env-file .env \
  -v /path/to/edge_keys.json:/run/secrets/edge_keys.json:ro \
  -e EDGE_KEYS_FILE=/run/secrets/edge_keys.json \
  webhook-edge
```

Configure nginx to proxy HTTPS → the published edge port. nginx forwards
arbitrary paths, so `/webhook` and `/tailscale` both work with no extra
upstream, service, or open port.

#### Router Service (Home LAN)

```bash
cd router
docker build -t webhook-router .
docker run -d \
  --name webhook-router \
  --restart unless-stopped \
  -p 8091:8080 \
  --env-file .env \
  -v $(pwd)/routes.yml:/app/routes.yml:ro \
  webhook-router
```

Both containers listen on port 8080 internally. Bind the router to its
Tailscale IP in production: `-p 100.x.x.x:8091:8080`

## Configuration

### Edge Service (.env)

```bash
# Path to the JSON file holding the edge keys (see below)
EDGE_KEYS_FILE=/run/secrets/edge_keys.json

# Router endpoint (Tailscale IP)
ROUTER_URL=http://100.64.1.5:8091/ingest

# Shared secret for edge→router auth
ROUTER_INGRESS_KEY=router_secret_def456

# Optional: Tailscale webhook ingress (POST /tailscale)
# When unset the edge still starts and /webhook works; /tailscale returns 503.
TAILSCALE_WEBHOOK_SECRET=

# Optional settings
REQUEST_TIMEOUT=30
MAX_BODY_SIZE_MB=1
RATE_LIMIT_PER_MINUTE=100
```

### Edge Keys (secrets/edge_keys.json)

Edge keys are file-backed, not inline in `.env`. The file is a JSON object of
`{owner: token}`; every token is a valid bearer credential and the owner name
is what shows up in the logs.

```json
{
  "alice": "edge_abc123",
  "bob": "edge_xyz789"
}
```

The edge refuses to start if the file is missing, malformed, empty, or maps
one token to two different owners. Generate tokens with `openssl rand -hex 32`.

### Router Service (.env)

```bash
# Shared secret (must match edge ROUTER_INGRESS_KEY)
ROUTER_INGRESS_KEY=router_secret_def456

# Optional per-destination auth tokens
GITHUB_SERVICE_TOKEN=optional_token_123
HOMEASSISTANT_TOKEN=optional_token_456
```

### Router Service (routes.yml)

```yaml
destinations:
  github-handler:
    method: POST
    url: http://192.168.1.50:3000/webhooks/github
    auth_env: GITHUB_SERVICE_TOKEN  # Optional
    timeout_seconds: 25

  # Tailscale events arrive here as an ordinary destination.
  tailscale:
    method: POST
    url: http://192.168.1.101:9000/hooks/tailscale
    timeout_seconds: 10

  custom-service:
    method: POST
    url: http://192.168.1.75:5000/events
    # No auth needed
```

## Usage

### Native ingress (POST /webhook)

The default. For any caller that can set a header and send our envelope.

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

### Tailscale ingress (POST /tailscale)

Tailscale controls its own request format, so it gets an adapter. Create the
webhook in the Tailscale admin console pointing at
`https://your-edge-domain.com/tailscale`, then put the secret it shows you in
`TAILSCALE_WEBHOOK_SECRET`.

The adapter verifies the `Tailscale-Webhook-Signature` header
(HMAC-SHA256 over `"<timestamp>.<raw body>"`, rejecting anything more than 5
minutes old) and forwards the event batch unchanged as:

```json
{"destination": "tailscale", "payload": [ ...events... ]}
```

Add a `tailscale` destination to `routes.yml` to say where those events go.
The router has no Tailscale-specific code.

### Adding Team Members

Add an entry to the edge keys JSON file and restart the edge service. Each
person uses their own key; logs show which owner was used via the `edge_key`
field.

## Security Notes

- **Edge keys**: Distribute to external services/team members (rotatable)
- **ROUTER_INGRESS_KEY**: Never leaves your infrastructure
- **TAILSCALE_WEBHOOK_SECRET**: Stays on the edge; never sent to the router
- **Per-destination tokens**: Optional auth for internal services
- All keys should be random, high-entropy strings (use `openssl rand -hex 32`)
- Never commit `.env` files or `secrets/edge_keys.json` to git
- Router should only listen on Tailscale interface in production

## Monitoring

### Health Checks

```bash
# Edge
curl http://localhost:8090/health

# Router
curl http://localhost:8091/health
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

For Tailscale-sourced requests the `edge_key` field reads `tailscale`.

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
| 401 | Unauthorized - invalid/missing bearer token, or bad Tailscale signature |
| 404 | Not Found - unknown destination |
| 413 | Payload Too Large - body exceeded MAX_BODY_SIZE_MB |
| 500 | Internal Error - edge/router failure |
| 502 | Bad Gateway - internal service returned error |
| 503 | Unavailable - /tailscale requested but TAILSCALE_WEBHOOK_SECRET is unset |
| 504 | Gateway Timeout - internal service timeout |

## Troubleshooting

### Edge can't reach router
- Check Tailscale connectivity: `tailscale ping 100.x.x.x`
- Verify ROUTER_URL in edge/.env
- Check router is listening: `netstat -tlnp | grep 8091`

### Router can't reach internal service
- Verify URL in routes.yml
- Check internal service is running
- Test manually: `curl http://192.168.1.50:3000/webhooks/github`

### Authentication failures
- Check ROUTER_INGRESS_KEY matches in both .env files
- Verify the token you are sending exists in the edge keys JSON file
- Check Authorization header format: `Bearer <key>` (exactly one space)

### /tailscale returns 503
`TAILSCALE_WEBHOOK_SECRET` is unset. The edge logs a warning at startup when
this is the case. Native ingress is unaffected.

### /tailscale returns 401
- Confirm the secret matches the one Tailscale showed at webhook creation
- Check clock skew: signatures older than 5 minutes are rejected
- Confirm nothing between Tailscale and the edge rewrites the request body;
  the signature covers the raw bytes

## File Structure

```
webhook-router/
├── edge/
│   ├── app.py                  # Application factory
│   ├── adapters/               # Ingress adapters
│   │   ├── types.py            #   IngressMessage / IngressError
│   │   ├── native.py           #   Bearer token + {destination, payload}
│   │   └── tailscale.py        #   Tailscale signature + event batch
│   ├── config/settings.py      # EdgeConfig loading
│   ├── http_handlers/          # Routes and error handlers
│   ├── services/               # RouterForwarder
│   ├── logging_utils.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── router/
│   ├── app.py                  # Application factory
│   ├── config/routes_loader.py
│   ├── http_handlers/          # /ingest and error handlers
│   ├── services/               # auth + destination forwarder
│   ├── logging_utils.py
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── routes.yml.example
│   └── routes.yml              # (gitignored)
├── secrets/
│   ├── edge_keys.example.json
│   └── edge_keys.json          # (gitignored)
├── tests/
│   ├── helpers.py
│   ├── edge/                   # Native + Tailscale ingress tests
│   └── router/                 # Ingest routing tests
├── docker-compose.example.yml
├── nginx_config.yml
├── pytest.ini
├── requirements-dev.txt
├── run_tests.sh                # Unit tests
└── test_script.sh              # Live smoke test
```

## Adding a New Ingress Adapter

Only add one when a provider cannot speak the native protocol. If it can send
`Authorization: Bearer ...` and `{destination, payload}`, use the native
adapter and configure a destination instead.

1. Add `edge/adapters/<provider>.py` exposing
   `adapt(config, log_json, correlation_id) -> IngressMessage`.
2. Authenticate however that provider dictates; raise `IngressError(status,
   message)` on rejection. Verify signatures before parsing the body.
3. Register a route in `edge/http_handlers/webhook.py` that calls
   `_handle_ingress(<provider>_adapter.adapt)`.
4. Add any secret to `EdgeConfig` rather than reading `os.getenv` in the adapter.
5. Add a destination to `routes.yml`. The router needs no changes.

There is no registry, base class, or plugin lifecycle to hook into.

## Next Steps

After MVP is running:
- Add Prometheus metrics endpoints
- Set up Grafana dashboards
- Add request/response body logging (debug mode)
- Implement hot-reload for routes.yml
- Implement the advertised EDGE_KEYS_PEPPER / EDGE_KEYS_RELOAD_SECONDS options
  (currently present in .env.example but not read by the code)
