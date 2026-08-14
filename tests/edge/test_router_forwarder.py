"""
Edge to router forwarding.

Both ingress paths must reach the router the same way they always have:
Authorization: Bearer <ROUTER_INGRESS_KEY>, with the correlation ID attached.
The Tailscale webhook secret must never leave the edge.
"""

import json
from unittest.mock import patch

import pytest
from flask import Flask

from edge_support import TAILSCALE_SECRET, VALID_TOKEN, sign
from helpers import FakeResponse, collecting_logger, import_service_module

ROUTER_INGRESS_KEY = 'router-ingress-key'
ROUTER_URL = 'http://router.test/ingest'


@pytest.fixture
def real_forwarder_client(make_edge_config):
    """An edge client wired to the real RouterForwarder, with requests.post patched."""
    webhook_module = import_service_module('edge', 'http_handlers.webhook')
    error_handlers = import_service_module('edge', 'http_handlers.error_handlers')
    router_forwarder_module = import_service_module('edge', 'services.router_forwarder')

    config = make_edge_config(
        router_url=ROUTER_URL,
        router_ingress_key=ROUTER_INGRESS_KEY,
    )
    log_json = collecting_logger()
    forwarder = router_forwarder_module.RouterForwarder(
        config.router_url,
        config.router_ingress_key,
        config.request_timeout,
        log_json,
    )

    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = config.max_body_size_mb * 1024 * 1024
    app.register_blueprint(webhook_module.create_edge_blueprint(config, forwarder, log_json))
    error_handlers.register_error_handlers(app, log_json)

    with patch.object(router_forwarder_module.requests, 'post') as mock_post:
        mock_post.return_value = FakeResponse()
        yield app.test_client(), mock_post


def test_native_ingress_uses_router_ingress_key(real_forwarder_client):
    client, mock_post = real_forwarder_client

    response = client.post(
        '/webhook',
        headers={'Authorization': f'Bearer {VALID_TOKEN}'},
        json={'destination': 'wikimgr', 'payload': {'a': 1}},
    )

    assert response.status_code == 200
    assert mock_post.call_count == 1

    args, kwargs = mock_post.call_args
    assert args[0] == ROUTER_URL
    assert kwargs['headers']['Authorization'] == f'Bearer {ROUTER_INGRESS_KEY}'
    assert kwargs['headers']['X-Correlation-ID']
    assert kwargs['json'] == {'destination': 'wikimgr', 'payload': {'a': 1}}


def test_tailscale_ingress_uses_router_ingress_key(real_forwarder_client):
    client, mock_post = real_forwarder_client

    events = [{'type': 'test', 'tailnet': 'example.com', 'data': None}]
    body = json.dumps(events).encode('utf-8')

    response = client.post(
        '/tailscale',
        headers={
            'Tailscale-Webhook-Signature': sign(body),
            'Content-Type': 'application/json',
        },
        data=body,
    )

    assert response.status_code == 200
    assert mock_post.call_count == 1

    _, kwargs = mock_post.call_args
    assert kwargs['headers']['Authorization'] == f'Bearer {ROUTER_INGRESS_KEY}'
    assert kwargs['json'] == {'destination': 'tailscale', 'payload': events}


def test_tailscale_secret_never_reaches_the_router(real_forwarder_client):
    client, mock_post = real_forwarder_client

    events = [{'type': 'test'}]
    body = json.dumps(events).encode('utf-8')

    client.post(
        '/tailscale',
        headers={
            'Tailscale-Webhook-Signature': sign(body),
            'Content-Type': 'application/json',
        },
        data=body,
    )

    _, kwargs = mock_post.call_args
    serialized = json.dumps({
        'headers': kwargs['headers'],
        'json': kwargs['json'],
    })

    assert TAILSCALE_SECRET not in serialized
    assert 'Tailscale-Webhook-Signature' not in kwargs['headers']


def test_edge_key_is_not_forwarded_to_the_router(real_forwarder_client):
    client, mock_post = real_forwarder_client

    client.post(
        '/webhook',
        headers={'Authorization': f'Bearer {VALID_TOKEN}'},
        json={'destination': 'wikimgr', 'payload': {}},
    )

    _, kwargs = mock_post.call_args
    assert VALID_TOKEN not in json.dumps(kwargs['headers'])
