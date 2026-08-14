"""Fixtures for the edge ingress tests."""

import pytest
from flask import Flask

from edge_support import OWNER, TAILSCALE_SECRET, VALID_TOKEN, FakeForwarder
from helpers import collecting_logger, import_service_module


@pytest.fixture
def edge_config_cls():
    return import_service_module('edge', 'config.settings').EdgeConfig


@pytest.fixture
def make_edge_config(edge_config_cls):
    def _make(**overrides):
        defaults = {
            'router_url': 'http://router.test/ingest',
            'router_ingress_key': 'router-ingress-key',
            'request_timeout': 5,
            'max_body_size_mb': 1,
            'rate_limit_per_minute': 100,
            'edge_keys': {VALID_TOKEN: OWNER},
            'tailscale_webhook_secret': TAILSCALE_SECRET,
        }
        defaults.update(overrides)
        return edge_config_cls(**defaults)

    return _make


@pytest.fixture
def make_edge_client(make_edge_config):
    """
    Build a Flask test client around the edge blueprint.

    Mirrors edge/app.py's wiring without importing it, since that module calls
    create_app() at import time and exits when config env vars are missing.
    """
    webhook_module = import_service_module('edge', 'http_handlers.webhook')
    error_handlers = import_service_module('edge', 'http_handlers.error_handlers')

    def _make(forwarder=None, config=None, **config_overrides):
        config = config or make_edge_config(**config_overrides)
        forwarder = forwarder or FakeForwarder()
        log_json = collecting_logger()

        app = Flask(__name__)
        app.config['MAX_CONTENT_LENGTH'] = config.max_body_size_mb * 1024 * 1024
        app.register_blueprint(
            webhook_module.create_edge_blueprint(config, forwarder, log_json)
        )
        error_handlers.register_error_handlers(app, log_json)

        return app.test_client(), forwarder, log_json

    return _make
