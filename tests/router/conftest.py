"""Fixtures for the router ingest tests."""

import pytest
from flask import Flask

from helpers import collecting_logger, import_service_module
from router_support import INGRESS_KEY, ROUTES


@pytest.fixture
def router_modules():
    return {
        'routes': import_service_module('router', 'http_handlers.routes'),
        'error_handlers': import_service_module('router', 'http_handlers.error_handlers'),
        'forwarder': import_service_module('router', 'services.forwarder'),
    }


@pytest.fixture
def router_client(router_modules):
    """
    Build a Flask test client around the router blueprint.

    router/app.py is deliberately not imported: it calls create_app() at import
    time, which exits when ROUTER_INGRESS_KEY or routes.yml is missing.
    """
    log_json = collecting_logger()

    app = Flask(__name__)
    app.register_blueprint(
        router_modules['routes'].create_router_blueprint(ROUTES, INGRESS_KEY, log_json)
    )
    router_modules['error_handlers'].register_error_handlers(app, log_json)

    return app.test_client(), log_json
