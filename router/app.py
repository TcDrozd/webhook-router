"""
Webhook Router Service
Receives from edge, validates ingress key, routes to internal services.
"""

import os
import sys
from functools import partial

from flask import Flask

from config.routes_loader import load_routes
from http_handlers.error_handlers import register_error_handlers
from http_handlers.routes import create_router_blueprint
from logging_utils import setup_logging, log_json

# Configuration
ROUTER_INGRESS_KEY = os.getenv('ROUTER_INGRESS_KEY', '')


def create_app() -> Flask:
    """Application factory to keep side effects out of the module import path."""
    logger = setup_logging()

    if not ROUTER_INGRESS_KEY:
        logger.error('ROUTER_INGRESS_KEY environment variable not set')
        sys.exit(1)

    routes = load_routes()
    app = Flask(__name__)

    json_logger = partial(log_json, logger)
    router_blueprint = create_router_blueprint(routes, ROUTER_INGRESS_KEY, json_logger)
    app.register_blueprint(router_blueprint)
    register_error_handlers(app, json_logger)

    logger.info('Router service starting')
    logger.info('Configured destinations: %s', ', '.join(routes.keys()))

    return app


app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
