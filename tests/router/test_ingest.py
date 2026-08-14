"""
Router ingest behaviour.

The point of the ingress adapter layer is that the router never learns about
any external provider. These tests pin that: a Tailscale batch routes through
exactly the same generic destination lookup as anything else.
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import REPO_ROOT, FakeResponse
from router_support import INGRESS_KEY, ROUTES

TAILSCALE_EVENTS = [
    {
        'timestamp': '2022-09-21T13:37:51.658918-04:00',
        'version': 1,
        'type': 'nodeCreated',
        'tailnet': 'example.com',
        'message': 'user added a new node called laptop',
        'data': {'nodeID': 'nBFsxCbC1'},
    }
]


def auth(key=INGRESS_KEY):
    return {'Authorization': f'Bearer {key}'}


@pytest.fixture
def mock_request(router_modules):
    with patch.object(router_modules['forwarder'].requests, 'request') as mock:
        mock.return_value = FakeResponse()
        yield mock


def test_tailscale_destination_routes_like_any_other(router_client, mock_request):
    client, _ = router_client

    response = client.post(
        '/ingest',
        headers=auth(),
        json={'destination': 'tailscale', 'payload': TAILSCALE_EVENTS},
    )

    assert response.status_code == 200

    _, kwargs = mock_request.call_args
    assert kwargs['url'] == ROUTES['tailscale']['url']
    assert kwargs['method'] == 'POST'
    assert kwargs['timeout'] == 10
    # Payload reaches the internal service unchanged.
    assert kwargs['json'] == TAILSCALE_EVENTS


def test_ordinary_destination_still_routes(router_client, mock_request):
    client, _ = router_client

    response = client.post(
        '/ingest',
        headers=auth(),
        json={'destination': 'wikimgr', 'payload': {'text': 'hello'}},
    )

    assert response.status_code == 200

    _, kwargs = mock_request.call_args
    assert kwargs['url'] == ROUTES['wikimgr']['url']
    assert kwargs['json'] == {'text': 'hello'}


def test_correlation_id_is_propagated(router_client, mock_request):
    client, _ = router_client

    client.post(
        '/ingest',
        headers={**auth(), 'X-Correlation-ID': 'abc-123'},
        json={'destination': 'tailscale', 'payload': TAILSCALE_EVENTS},
    )

    _, kwargs = mock_request.call_args
    assert kwargs['headers']['X-Correlation-ID'] == 'abc-123'


@pytest.mark.parametrize(
    'headers',
    [{}, {'Authorization': 'Bearer wrong-key'}, {'Authorization': INGRESS_KEY}],
    ids=['missing', 'wrong', 'no-scheme'],
)
def test_bad_ingress_key_returns_401(router_client, mock_request, headers):
    client, _ = router_client

    response = client.post(
        '/ingest',
        headers=headers,
        json={'destination': 'tailscale', 'payload': TAILSCALE_EVENTS},
    )

    assert response.status_code == 401
    assert response.get_json() == {'error': 'Unauthorized'}
    assert mock_request.call_count == 0


def test_unknown_destination_returns_404(router_client, mock_request):
    client, _ = router_client

    response = client.post(
        '/ingest',
        headers=auth(),
        json={'destination': 'not-configured', 'payload': {}},
    )

    assert response.status_code == 404
    assert mock_request.call_count == 0


@pytest.mark.parametrize(
    'body',
    [{'payload': {}}, {'destination': 'tailscale'}, {}, [1, 2]],
    ids=['no-destination', 'no-payload', 'empty', 'list'],
)
def test_invalid_envelope_returns_400(router_client, mock_request, body):
    client, _ = router_client

    response = client.post('/ingest', headers=auth(), json=body)

    assert response.status_code == 400
    assert mock_request.call_count == 0


def test_health_reports_destination_count(router_client):
    client, _ = router_client

    response = client.get('/health')

    assert response.status_code == 200
    assert response.get_json() == {
        'status': 'healthy',
        'service': 'router',
        'destinations': len(ROUTES),
    }


def test_router_source_contains_no_tailscale_logic():
    """
    Only routes.yml.example may mention Tailscale, and only as a destination
    entry. Any .py hit means provider knowledge leaked into the router.
    """
    router_dir = Path(REPO_ROOT) / 'router'
    result = subprocess.run(
        ['grep', '-ril', 'tailscale', '--include=*.py', '.'],
        cwd=router_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.stdout.strip() == '', f'Tailscale logic found in router: {result.stdout}'
