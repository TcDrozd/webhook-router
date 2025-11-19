import uuid
from typing import Any, Dict, Optional

from flask import Blueprint, Response, jsonify, request

from config.settings import EdgeConfig
from services.router_forwarder import (
    RouterForwarder,
    RouterForwarderError,
    RouterTimeoutError,
    RouterUnavailableError,
)


def create_edge_blueprint(config: EdgeConfig, router_forwarder: RouterForwarder, log_json) -> Blueprint:
    """Create the blueprint containing the edge HTTP routes."""
    blueprint = Blueprint('edge', __name__)

    @blueprint.before_app_request
    def add_correlation_id():
        request.correlation_id = str(uuid.uuid4())

    @blueprint.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'healthy', 'service': 'edge'}), 200

    @blueprint.route('/webhook', methods=['POST'])
    def webhook():
        correlation_id = getattr(request, 'correlation_id', str(uuid.uuid4()))
        edge_key_name = _validate_bearer_token(request.headers.get('Authorization'), config.edge_keys)

        if not edge_key_name:
            log_json(
                'warn',
                correlation_id,
                'Unauthorized request',
                remote_addr=request.remote_addr,
            )
            return jsonify({'error': 'Unauthorized'}), 401

        body, error_response = _parse_request_body(correlation_id, log_json, edge_key_name)
        if error_response is not None:
            return error_response

        destination = body['destination']
        log_json(
            'info',
            correlation_id,
            'Received webhook',
            edge_key=edge_key_name,
            destination=destination,
            remote_addr=request.remote_addr,
        )

        try:
            router_response = router_forwarder.forward(body, correlation_id, edge_key_name, destination)
            return _proxy_response(router_response)
        except RouterTimeoutError:
            return jsonify({'error': 'Gateway timeout'}), 504
        except RouterUnavailableError:
            return jsonify({'error': 'Bad gateway - router unreachable'}), 502
        except RouterForwarderError:
            return jsonify({'error': 'Internal server error'}), 500

    return blueprint


def _validate_bearer_token(auth_header: Optional[str], edge_keys: Dict[str, str]) -> Optional[str]:
    """Validate bearer token and return key name if valid."""
    if not auth_header:
        return None

    parts = auth_header.split(' ')
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None

    token = parts[1]
    return edge_keys.get(token)


def _parse_request_body(correlation_id: str, log_json, edge_key_name: str) -> tuple[Optional[Dict[str, Any]], Optional[Response]]:
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
        return None, (jsonify({'error': 'Invalid JSON'}), 400)

    if not isinstance(body, dict) or 'destination' not in body or 'payload' not in body:
        log_json(
            'warn',
            correlation_id,
            'Missing destination or payload',
            edge_key=edge_key_name,
        )
        return None, (
            jsonify({'error': 'Request must contain "destination" and "payload" fields'}),
            400,
        )

    return body, None


def _proxy_response(router_response) -> Response:
    """Convert the router response into a Flask Response."""
    return Response(
        router_response.content,
        status=router_response.status_code,
        content_type=router_response.headers.get('Content-Type', 'application/json'),
    )
