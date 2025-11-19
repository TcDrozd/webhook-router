from typing import Dict, Any, Callable

import requests
from flask import Blueprint, jsonify, request, Response

from services.auth import validate_bearer_token
from services.forwarder import forward_to_destination

LogJsonFn = Callable[..., None]


def create_router_blueprint(
    routes: Dict[str, Dict[str, Any]],
    ingress_key: str,
    log_json: LogJsonFn,
) -> Blueprint:
    """
    Create a Flask blueprint containing the router HTTP endpoints.
    """
    bp = Blueprint('router', __name__)

    @bp.route('/health', methods=['GET'])
    def health():
        return jsonify({
            'status': 'healthy',
            'service': 'router',
            'destinations': len(routes)
        }), 200

    @bp.route('/ingest', methods=['POST'])
    def ingest():
        correlation_id = request.headers.get('X-Correlation-ID', 'unknown')

        auth_header = request.headers.get('Authorization')
        if not validate_bearer_token(auth_header, ingress_key):
            log_json('warn', correlation_id, 'Unauthorized ingress request',
                     remote_addr=request.remote_addr)
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            body = request.get_json(force=True)
        except Exception as exc:  # noqa: BLE001
            log_json('warn', correlation_id, 'Invalid JSON body', error=str(exc))
            return jsonify({'error': 'Invalid JSON'}), 400

        if not isinstance(body, dict) or 'destination' not in body or 'payload' not in body:
            log_json('warn', correlation_id, 'Missing destination or payload')
            return jsonify({'error': 'Request must contain "destination" and "payload" fields'}), 400

        destination = body['destination']
        payload = body['payload']

        if destination not in routes:
            log_json('warn', correlation_id, 'Unknown destination', destination=destination)
            return jsonify({'error': f'Unknown destination: {destination}'}), 404

        route_config = routes[destination]
        log_json('info', correlation_id, 'Received from edge', destination=destination)

        try:
            response = forward_to_destination(destination, route_config, payload, correlation_id, log_json)

            return Response(
                response.content,
                status=response.status_code,
                content_type=response.headers.get('Content-Type', 'application/json')
            )

        except requests.exceptions.Timeout:
            log_json('error', correlation_id, 'Internal service timeout',
                     destination=destination,
                     url=route_config['url'])
            return jsonify({'error': 'Gateway timeout - internal service did not respond'}), 504

        except requests.exceptions.ConnectionError as exc:
            log_json('error', correlation_id, 'Internal service connection failed',
                     destination=destination,
                     url=route_config['url'],
                     error=str(exc))
            return jsonify({'error': 'Bad gateway - internal service unreachable'}), 502

        except Exception as exc:  # noqa: BLE001
            log_json('error', correlation_id, 'Unexpected error',
                     destination=destination,
                     error=str(exc),
                     error_type=type(exc).__name__)
            return jsonify({'error': 'Internal server error'}), 500

    return bp
