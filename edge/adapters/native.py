"""
Native ingress adapter.

The original webhook-router protocol: a bearer token from EDGE_KEYS_FILE plus
a {"destination": ..., "payload": ...} envelope. This remains the default
escape hatch for any caller that can speak it.
"""

from typing import Dict, Optional

from flask import request

from config.settings import EdgeConfig

from .types import IngressError, IngressMessage


def adapt(config: EdgeConfig, log_json, correlation_id: str) -> IngressMessage:
    """Authenticate and parse a native webhook request."""
    edge_key_name = _validate_bearer_token(request.headers.get('Authorization'), config.edge_keys)

    if not edge_key_name:
        log_json(
            'warn',
            correlation_id,
            'Unauthorized request',
            remote_addr=request.remote_addr,
        )
        raise IngressError(401, 'Unauthorized')

    body = _parse_request_body(correlation_id, log_json, edge_key_name)

    return IngressMessage(
        destination=body['destination'],
        payload=body['payload'],
        source=edge_key_name,
    )


def _validate_bearer_token(auth_header: Optional[str], edge_keys: Dict[str, str]) -> Optional[str]:
    """Validate bearer token and return key name if valid."""
    if not auth_header:
        return None

    parts = auth_header.split(' ')
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None

    token = parts[1]
    return edge_keys.get(token)


def _parse_request_body(correlation_id: str, log_json, edge_key_name: str) -> Dict:
    """Parse the JSON payload and validate required fields."""
    try:
        body = request.get_json(force=True)
    except Exception as exc:  # pylint: disable=broad-except
        log_json(
            'warn',
            correlation_id,
            'Invalid JSON body',
            edge_key=edge_key_name,
            error=str(exc),
        )
        raise IngressError(400, 'Invalid JSON') from exc

    if not isinstance(body, dict) or 'destination' not in body or 'payload' not in body:
        log_json(
            'warn',
            correlation_id,
            'Missing destination or payload',
            edge_key=edge_key_name,
        )
        raise IngressError(400, 'Request must contain "destination" and "payload" fields')

    return body
