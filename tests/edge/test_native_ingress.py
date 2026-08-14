"""
Native ingress (/webhook) behaviour.

These are backward-compatibility tests: the contract asserted here is the one
that existed before the adapter refactor, and existing callers depend on it.
"""

import json

import pytest

from edge_support import OWNER, VALID_TOKEN, FakeForwarder
from helpers import FakeResponse, import_service_module


def auth(token=VALID_TOKEN):
    return {'Authorization': f'Bearer {token}'}


def test_valid_request_forwards_to_router(make_edge_client):
    client, forwarder, _ = make_edge_client()

    response = client.post(
        '/webhook',
        headers=auth(),
        json={'destination': 'wikimgr', 'payload': {'text': 'hello'}},
    )

    assert response.status_code == 200
    assert len(forwarder.calls) == 1

    call = forwarder.calls[0]
    assert call['body'] == {'destination': 'wikimgr', 'payload': {'text': 'hello'}}
    assert call['destination'] == 'wikimgr'
    assert call['edge_key_name'] == OWNER
    assert call['correlation_id']


def test_router_response_is_proxied_verbatim(make_edge_client):
    forwarder = FakeForwarder(
        response=FakeResponse(content=b'{"upstream": true}', status_code=201)
    )
    client, _, _ = make_edge_client(forwarder=forwarder)

    response = client.post(
        '/webhook',
        headers=auth(),
        json={'destination': 'wikimgr', 'payload': {}},
    )

    assert response.status_code == 201
    assert response.get_json() == {'upstream': True}


def test_router_404_is_passed_through(make_edge_client):
    """Unknown destinations are the router's call, not the edge's."""
    forwarder = FakeForwarder(
        response=FakeResponse(content=b'{"error": "Unknown destination: nope"}', status_code=404)
    )
    client, _, _ = make_edge_client(forwarder=forwarder)

    response = client.post(
        '/webhook',
        headers=auth(),
        json={'destination': 'nope', 'payload': {}},
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    'headers',
    [
        {},
        {'Authorization': ''},
        {'Authorization': 'Bearer wrong-token'},
        {'Authorization': 'Basic ' + VALID_TOKEN},
        {'Authorization': VALID_TOKEN},
        {'Authorization': f'Bearer  {VALID_TOKEN}'},
    ],
    ids=['missing', 'empty', 'wrong-token', 'wrong-scheme', 'no-scheme', 'double-space'],
)
def test_bad_authorization_is_rejected(make_edge_client, headers):
    client, forwarder, _ = make_edge_client()

    response = client.post(
        '/webhook',
        headers=headers,
        json={'destination': 'wikimgr', 'payload': {}},
    )

    assert response.status_code == 401
    assert response.get_json() == {'error': 'Unauthorized'}
    assert forwarder.calls == []


def test_bearer_scheme_is_case_insensitive(make_edge_client):
    client, forwarder, _ = make_edge_client()

    response = client.post(
        '/webhook',
        headers={'Authorization': f'bearer {VALID_TOKEN}'},
        json={'destination': 'wikimgr', 'payload': {}},
    )

    assert response.status_code == 200
    assert len(forwarder.calls) == 1


@pytest.mark.parametrize(
    'body',
    [
        {'payload': {}},
        {'destination': 'wikimgr'},
        {},
        [1, 2, 3],
        'a string',
    ],
    ids=['no-destination', 'no-payload', 'empty', 'list', 'string'],
)
def test_invalid_envelope_returns_400(make_edge_client, body):
    client, forwarder, _ = make_edge_client()

    response = client.post('/webhook', headers=auth(), json=body)

    assert response.status_code == 400
    assert response.get_json() == {
        'error': 'Request must contain "destination" and "payload" fields'
    }
    assert forwarder.calls == []


def test_malformed_json_returns_400(make_edge_client):
    client, forwarder, _ = make_edge_client()

    response = client.post(
        '/webhook',
        headers={**auth(), 'Content-Type': 'application/json'},
        data=b'{"destination": "wikimgr", ',
    )

    assert response.status_code == 400
    assert response.get_json() == {'error': 'Invalid JSON'}
    assert forwarder.calls == []


def test_auth_is_checked_before_body_parsing(make_edge_client):
    """A bad token with an unparseable body is still a 401, never a 400."""
    client, _, _ = make_edge_client()

    response = client.post(
        '/webhook',
        headers={'Authorization': 'Bearer wrong-token', 'Content-Type': 'application/json'},
        data=b'not json at all',
    )

    assert response.status_code == 401


def test_null_payload_is_accepted(make_edge_client):
    """`payload` is present, so this is a valid envelope even though it is null."""
    client, forwarder, _ = make_edge_client()

    response = client.post(
        '/webhook',
        headers=auth(),
        json={'destination': 'wikimgr', 'payload': None},
    )

    assert response.status_code == 200
    assert forwarder.calls[0]['body'] == {'destination': 'wikimgr', 'payload': None}


@pytest.mark.parametrize(
    'error_name,expected_status',
    [
        ('RouterTimeoutError', 504),
        ('RouterUnavailableError', 502),
        ('RouterForwarderError', 500),
    ],
)
def test_router_failures_map_to_status_codes(make_edge_client, error_name, expected_status):
    router_forwarder = import_service_module('edge', 'services.router_forwarder')
    error_cls = getattr(router_forwarder, error_name)

    forwarder = FakeForwarder(error=error_cls('boom'))
    client, _, _ = make_edge_client(forwarder=forwarder)

    response = client.post(
        '/webhook',
        headers=auth(),
        json={'destination': 'wikimgr', 'payload': {}},
    )

    assert response.status_code == expected_status


def test_health_is_unauthenticated(make_edge_client):
    client, _, _ = make_edge_client()

    response = client.get('/health')

    assert response.status_code == 200
    assert response.get_json() == {'status': 'healthy', 'service': 'edge'}


def test_oversized_body_is_rejected(make_edge_client):
    """
    Pins pre-existing behaviour: MAX_CONTENT_LENGTH makes Werkzeug raise while
    the body is being read, inside the adapter's broad except, so the native
    path reports 400 rather than reaching the app's 413 handler. Preserved as
    is for backward compatibility.
    """
    client, forwarder, _ = make_edge_client()

    oversized = json.dumps({'destination': 'wikimgr', 'payload': {'blob': 'x' * (2 * 1024 * 1024)}})
    response = client.post(
        '/webhook',
        headers={**auth(), 'Content-Type': 'application/json'},
        data=oversized,
    )

    assert response.status_code == 400
    assert forwarder.calls == []


def test_unauthorized_request_is_logged(make_edge_client):
    client, _, log_json = make_edge_client()

    client.post('/webhook', json={'destination': 'wikimgr', 'payload': {}})

    messages = [entry['message'] for entry in log_json.entries]
    assert 'Unauthorized request' in messages
