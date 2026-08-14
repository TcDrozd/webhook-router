"""
Shared constants and stand-ins for the edge suite.

Kept out of conftest.py because both suites have a conftest and only one can
own that module name in a single interpreter.
"""

import hashlib
import hmac
import time

from helpers import FakeResponse

VALID_TOKEN = 'valid-edge-token'
OWNER = 'trevor'
TAILSCALE_SECRET = 'ts-webhook-secret'


class FakeForwarder:
    """Records what the edge would have sent to the router."""

    def __init__(self, response=None, error=None):
        self.calls = []
        self.response = response if response is not None else FakeResponse()
        self.error = error

    def forward(self, body, correlation_id, edge_key_name, destination):
        self.calls.append({
            'body': body,
            'correlation_id': correlation_id,
            'edge_key_name': edge_key_name,
            'destination': destination,
        })
        if self.error is not None:
            raise self.error
        return self.response


def sign(body: bytes, secret: str = TAILSCALE_SECRET, timestamp=None) -> str:
    """Build a Tailscale-Webhook-Signature header value for `body`."""
    timestamp = str(int(time.time())) if timestamp is None else str(timestamp)
    signature = hmac.new(
        secret.encode('utf-8'),
        f'{timestamp}.'.encode('utf-8') + body,
        hashlib.sha256,
    ).hexdigest()
    return f't={timestamp},v1={signature}'
