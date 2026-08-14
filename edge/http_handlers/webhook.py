import uuid
from typing import Callable

from flask import Blueprint, Response, jsonify, request

from adapters import IngressError, IngressMessage
from adapters import native as native_adapter
from adapters import tailscale as tailscale_adapter
from config.settings import EdgeConfig
from services.router_forwarder import (
    RouterForwarder,
    RouterForwarderError,
    RouterTimeoutError,
    RouterUnavailableError,
)

AdaptFn = Callable[[EdgeConfig, Callable[..., None], str], IngressMessage]


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
        return _handle_ingress(native_adapter.adapt)

    @blueprint.route('/tailscale', methods=['POST'])
    def tailscale():
        return _handle_ingress(tailscale_adapter.adapt)

    def _handle_ingress(adapt: AdaptFn):
        """
        Run an ingress adapter and forward its canonical message to the router.

        Every ingress path converges here, so this function stays free of
        provider-specific behaviour.
        """
        correlation_id = getattr(request, 'correlation_id', str(uuid.uuid4()))

        try:
            message = adapt(config, log_json, correlation_id)
        except IngressError as exc:
            return jsonify({'error': exc.message}), exc.status_code

        log_json(
            'info',
            correlation_id,
            'Received webhook',
            edge_key=message.source,
            destination=message.destination,
            remote_addr=request.remote_addr,
        )

        body = {'destination': message.destination, 'payload': message.payload}

        try:
            router_response = router_forwarder.forward(
                body,
                correlation_id,
                message.source,
                message.destination,
            )
            return _proxy_response(router_response)
        except RouterTimeoutError:
            return jsonify({'error': 'Gateway timeout'}), 504
        except RouterUnavailableError:
            return jsonify({'error': 'Bad gateway - router unreachable'}), 502
        except RouterForwarderError:
            return jsonify({'error': 'Internal server error'}), 500

    return blueprint


def _proxy_response(router_response) -> Response:
    """Convert the router response into a Flask Response."""
    return Response(
        router_response.content,
        status=router_response.status_code,
        content_type=router_response.headers.get('Content-Type', 'application/json'),
    )
