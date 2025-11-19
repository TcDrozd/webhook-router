"""
Webhook Edge Service
Application factory that wires configuration, logging, and HTTP handlers.
"""

from functools import partial

from flask import Flask

from config import load_edge_config
from http_handlers.error_handlers import register_error_handlers
from http_handlers.webhook import create_edge_blueprint
from logging_utils import log_json, setup_logging
from services.router_forwarder import RouterForwarder


def create_app() -> Flask:
    """Create and configure the Flask application."""
    logger = setup_logging()
    config = load_edge_config(logger)

    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = config.max_body_size_mb * 1024 * 1024

    json_logger = partial(log_json, logger)
    router_forwarder = RouterForwarder(
        config.router_url,
        config.router_ingress_key,
        config.request_timeout,
        json_logger,
    )

    app.register_blueprint(create_edge_blueprint(config, router_forwarder, json_logger))
    register_error_handlers(app, json_logger)

    logger.info('Edge service starting with %s keys configured', len(config.edge_keys))
    logger.info('Router URL: %s', config.router_url)
    logger.info('Request timeout: %ss', config.request_timeout)

    return app


app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
