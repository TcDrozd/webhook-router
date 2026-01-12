# Router Service Deployment Runbook

## Overview
This runbook covers deploying only the Router service from the webhook-router system. The Router service receives webhooks from the Edge service (or directly if bypassing Edge), validates authentication, and forwards requests to configured internal services.

## Prerequisites
- Docker and Docker Compose installed
- Access to internal services that the router will forward to
- Network connectivity to destination services (e.g., Wiki Manager, Slack ingest, etc.)

## Configuration

### 1. Environment Variables
```bash
cd /path/to/webhook-router

# Copy the example environment file
cp router/.env.example router/.env

# Edit with your values
nano router/.env
```

**Required Variables:**
- `ROUTER_INGRESS_KEY`: Shared secret for authentication (generate with `openssl rand -hex 32`)

**Optional Variables:**
- Authentication tokens for internal services (set only those referenced in `routes.yml`)

### 2. Routes Configuration
Edit `router/routes.yml` to configure your destination services:
```bash
nano router/routes.yml
```

Example configuration:
```yaml
destinations:
  my-service:
    method: POST
    url: http://internal-service:8080/webhook
    auth_env: MY_SERVICE_TOKEN  # optional
    timeout_seconds: 30
```

## Deployment

### Build and Start Router Service
```bash
# Build and start only the router service
docker-compose --profile router up --build -d

# Or for development with logs:
docker-compose --profile router up --build
```

### Verify Deployment
```bash
# Check container status
docker-compose --profile router ps

# View logs
docker-compose --profile router logs -f router
```

The router service will be available on port 8091 (mapped from container port 8080).

## Testing

### Health Check
```bash
# Test basic connectivity (if you have a health endpoint configured)
curl -X GET http://localhost:8091/health
```

### Full Webhook Test
```bash
# Test with a sample webhook payload
curl -X POST http://localhost:8091/ingest \
  -H "Authorization: Bearer YOUR_ROUTER_INGRESS_KEY" \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

Replace `YOUR_ROUTER_INGRESS_KEY` with the value from your `.env` file.

## Monitoring

### Logs
```bash
# Follow router logs
docker-compose --profile router logs -f router

# View recent logs
docker-compose --profile router logs --tail=50 router
```

### Container Status
```bash
# Check running containers
docker-compose --profile router ps

# Check resource usage
docker stats $(docker-compose --profile router ps -q)
```

## Troubleshooting

### Common Issues

**Container fails to start:**
- Check `.env` file exists and `ROUTER_INGRESS_KEY` is set
- Verify `routes.yml` is valid YAML and contains required fields
- Check logs: `docker-compose --profile router logs router`

**Authentication failures:**
- Ensure the `Authorization: Bearer <key>` header matches `ROUTER_INGRESS_KEY`
- Check logs for authentication errors

**Forwarding failures:**
- Verify destination URLs are reachable from the container
- Check authentication tokens are set for services requiring them
- Review timeout settings in `routes.yml`

**Network issues:**
- Ensure destination services are running and accessible
- Check firewall rules if running on different networks

### Debugging
```bash
# Enter container for debugging
docker-compose --profile router exec router bash

# Check environment variables
docker-compose --profile router exec router env | grep ROUTER

# Test internal connectivity
docker-compose --profile router exec router curl -I http://destination-service:port/health
```

## Maintenance

### Updates
```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose --profile router up --build -d
```

### Backups
- Backup `router/.env` (contains secrets)
- Backup `router/routes.yml` (contains configuration)

### Cleanup
```bash
# Stop and remove containers
docker-compose --profile router down

# Remove images (optional)
docker-compose --profile router down --rmi all
```

## Security Notes
- Keep `ROUTER_INGRESS_KEY` secure and rotate periodically
- Use strong, unique tokens for internal service authentication
- Monitor logs for unauthorized access attempts
- Consider network segmentation for production deployments