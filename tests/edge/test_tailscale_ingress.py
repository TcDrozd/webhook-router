"""Tailscale ingress (/tailscale) behaviour."""

import hashlib
import hmac
import json
import time

import pytest

from edge_support import TAILSCALE_SECRET, VALID_TOKEN, FakeForwarder, sign
from helpers import import_service_module

SIGNATURE_HEADER = 'Tailscale-Webhook-Signature'

# Shaped after Tailscale's documented batch payload.
EVENTS = [
    {
        'timestamp': '2022-09-21T13:37:51.658918-04:00',
        'version': 1,
        'type': 'nodeCreated',
        'tailnet': 'example.com',
        'message': 'user added a new node called laptop',
        'data': {'nodeID': 'nBFsxCbC1', 'deviceName': 'laptop'},
    },
    {
        'timestamp': '2022-09-21T13:38:00.000000-04:00',
        'version': 1,
        'type': 'nodeApproved',
        'tailnet': 'example.com',
        'message': 'user approved node laptop',
        'data': {'nodeID': 'nBFsxCbC1'},
    },
]


def body_bytes(events=None):
    return json.dumps(events if events is not None else EVENTS).encode('utf-8')


def post(client, body, signature=None, extra_headers=None):
    headers = {'Content-Type': 'application/json'}
    if signature is not None:
        headers[SIGNATURE_HEADER] = signature
    if extra_headers:
        headers.update(extra_headers)
    return client.post('/tailscale', headers=headers, data=body)


def test_valid_signed_request_is_accepted(make_edge_client):
    client, forwarder, _ = make_edge_client()
    body = body_bytes()

    response = post(client, body, sign(body))

    assert response.status_code == 200
    assert len(forwarder.calls) == 1


def test_forwarded_body_uses_tailscale_destination_and_preserves_batch(make_edge_client):
    client, forwarder, _ = make_edge_client()
    body = body_bytes()

    post(client, body, sign(body))

    call = forwarder.calls[0]
    assert call['body'] == {'destination': 'tailscale', 'payload': EVENTS}
    assert call['destination'] == 'tailscale'
    assert call['edge_key_name'] == 'tailscale'

    # The batch array survives element for element, unnormalized.
    assert isinstance(call['body']['payload'], list)
    assert len(call['body']['payload']) == 2
    assert call['body']['payload'][0]['type'] == 'nodeCreated'
    assert call['body']['payload'][1]['type'] == 'nodeApproved'


def test_single_event_batch_is_preserved_as_a_list(make_edge_client):
    client, forwarder, _ = make_edge_client()
    body = body_bytes([EVENTS[0]])

    post(client, body, sign(body))

    assert forwarder.calls[0]['body']['payload'] == [EVENTS[0]]


def test_invalid_signature_returns_401(make_edge_client):
    client, forwarder, _ = make_edge_client()
    body = body_bytes()

    timestamp = str(int(time.time()))
    bad = 'a' * 64
    response = post(client, body, f't={timestamp},v1={bad}')

    assert response.status_code == 401
    assert response.get_json() == {'error': 'Unauthorized'}
    assert forwarder.calls == []


def test_signature_from_wrong_secret_returns_401(make_edge_client):
    client, forwarder, _ = make_edge_client()
    body = body_bytes()

    response = post(client, body, sign(body, secret='not-the-secret'))

    assert response.status_code == 401
    assert forwarder.calls == []


def test_signature_over_a_different_body_returns_401(make_edge_client):
    """A valid signature cannot be replayed onto tampered content."""
    client, forwarder, _ = make_edge_client()
    signature = sign(body_bytes())

    response = post(client, body_bytes([EVENTS[0]]), signature)

    assert response.status_code == 401
    assert forwarder.calls == []


@pytest.mark.parametrize(
    'header',
    [
        None,
        '',
        't=123456789',
        'v1=' + 'a' * 64,
        'garbage',
        't=notanumber,v1=' + 'a' * 64,
        't=,v1=' + 'a' * 64,
    ],
    ids=['missing', 'empty', 'no-v1', 'no-t', 'garbage', 'non-integer-t', 'blank-t'],
)
def test_malformed_signature_header_returns_401(make_edge_client, header):
    client, forwarder, _ = make_edge_client()

    response = post(client, body_bytes(), header)

    assert response.status_code == 401
    assert forwarder.calls == []


def test_stale_timestamp_returns_401(make_edge_client):
    client, forwarder, _ = make_edge_client()
    body = body_bytes()

    stale = int(time.time()) - 600
    response = post(client, body, sign(body, timestamp=stale))

    assert response.status_code == 401
    assert forwarder.calls == []


def test_far_future_timestamp_returns_401(make_edge_client):
    client, forwarder, _ = make_edge_client()
    body = body_bytes()

    future = int(time.time()) + 600
    response = post(client, body, sign(body, timestamp=future))

    assert response.status_code == 401
    assert forwarder.calls == []


def test_timestamp_inside_tolerance_is_accepted(make_edge_client):
    client, forwarder, _ = make_edge_client()
    body = body_bytes()

    recent = int(time.time()) - 120
    response = post(client, body, sign(body, timestamp=recent))

    assert response.status_code == 200
    assert len(forwarder.calls) == 1


def test_second_v1_candidate_is_accepted(make_edge_client):
    """Tailscale sends multiple v1 values while a secret is being rotated."""
    client, forwarder, _ = make_edge_client()
    body = body_bytes()

    timestamp = str(int(time.time()))
    good = hmac.new(
        TAILSCALE_SECRET.encode('utf-8'),
        f'{timestamp}.'.encode('utf-8') + body,
        hashlib.sha256,
    ).hexdigest()
    header = f't={timestamp},v1={"b" * 64},v1={good}'

    response = post(client, body, header)

    assert response.status_code == 200
    assert len(forwarder.calls) == 1


def test_valid_signature_over_malformed_json_returns_400(make_edge_client):
    """Signature verification happens before the body is parsed."""
    client, forwarder, _ = make_edge_client()
    body = b'{"events": '

    response = post(client, body, sign(body))

    assert response.status_code == 400
    assert response.get_json() == {'error': 'Invalid JSON'}
    assert forwarder.calls == []


def test_missing_secret_returns_503_and_does_not_forward(make_edge_client):
    client, forwarder, _ = make_edge_client(tailscale_webhook_secret='')
    body = body_bytes()

    response = post(client, body, sign(body))

    assert response.status_code == 503
    assert response.get_json() == {'error': 'Tailscale ingress not configured'}
    assert forwarder.calls == []


def test_native_bearer_token_is_not_accepted_on_tailscale(make_edge_client):
    """Adapters do not fall back to each other's authentication."""
    client, forwarder, _ = make_edge_client()

    response = post(
        client,
        body_bytes(),
        signature=None,
        extra_headers={'Authorization': f'Bearer {VALID_TOKEN}'},
    )

    assert response.status_code == 401
    assert forwarder.calls == []


def test_tailscale_signature_is_not_accepted_on_native_webhook(make_edge_client):
    """And the native path does not learn about signatures."""
    client, forwarder, _ = make_edge_client()
    body = body_bytes()

    response = client.post(
        '/webhook',
        headers={SIGNATURE_HEADER: sign(body), 'Content-Type': 'application/json'},
        data=body,
    )

    assert response.status_code == 401
    assert forwarder.calls == []


def test_router_failures_map_to_status_codes(make_edge_client):
    router_forwarder = import_service_module('edge', 'services.router_forwarder')
    forwarder = FakeForwarder(error=router_forwarder.RouterTimeoutError('slow'))
    client, _, _ = make_edge_client(forwarder=forwarder)

    body = body_bytes()
    response = post(client, body, sign(body))

    assert response.status_code == 504


def test_oversized_body_returns_413(make_edge_client):
    """
    The Tailscale path reads the raw body outside any broad except, so an
    oversized request reaches the app's 413 handler. The native path predates
    that handler and still answers 400; see test_native_ingress.
    """
    client, forwarder, _ = make_edge_client()
    body = json.dumps([{'blob': 'x' * (2 * 1024 * 1024)}]).encode('utf-8')

    response = post(client, body, sign(body))

    assert response.status_code == 413
    assert forwarder.calls == []


def test_get_is_not_allowed(make_edge_client):
    client, _, _ = make_edge_client()

    assert client.get('/tailscale').status_code == 405


def test_signature_tolerance_matches_tailscale_guidance():
    tailscale = import_service_module('edge', 'adapters.tailscale')

    assert tailscale.SIGNATURE_TOLERANCE_SECONDS == 300
    assert tailscale.SIGNATURE_HEADER == SIGNATURE_HEADER
