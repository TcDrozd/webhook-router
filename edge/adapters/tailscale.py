"""
Tailscale ingress adapter.

Tailscale controls the shape of its outbound webhooks, so it cannot speak the
native protocol: it signs requests with an HMAC header rather than a bearer
token, and it POSTs a batch array of events rather than our envelope.

Signature scheme (see https://tailscale.com/kb/1213/webhooks):

    Tailscale-Webhook-Signature: t=<unix-seconds>,v1=<hex-hmac>[,v1=<hex-hmac>]

    string_to_sign = "<t>." + <raw request body>
    signature      = hex(HMAC-SHA256(secret, string_to_sign))

Several v1 values may be present while a webhook secret is being rotated, so
any matching candidate is accepted.

This module is the only place in the project that knows Tailscale exists. It
knows nothing about the internal service the events end up at.
"""

import hashlib
import hmac
import json
import time
from typing import List, Optional, Tuple

from flask import request

from config.settings import EdgeConfig

from .types import IngressError, IngressMessage

SIGNATURE_HEADER = 'Tailscale-Webhook-Signature'
SIGNATURE_TOLERANCE_SECONDS = 300

DESTINATION = 'tailscale'
SOURCE = 'tailscale'


def adapt(config: EdgeConfig, log_json, correlation_id: str) -> IngressMessage:
    """Verify a Tailscale webhook signature and parse its event batch."""
    if not config.tailscale_webhook_secret:
        log_json(
            'warn',
            correlation_id,
            'Tailscale ingress not configured',
            remote_addr=request.remote_addr,
        )
        raise IngressError(503, 'Tailscale ingress not configured')

    raw_body = request.get_data()
    signature_header = request.headers.get(SIGNATURE_HEADER)

    if not _verify_signature(raw_body, signature_header, config.tailscale_webhook_secret):
        log_json(
            'warn',
            correlation_id,
            'Invalid Tailscale webhook signature',
            remote_addr=request.remote_addr,
        )
        raise IngressError(401, 'Unauthorized')

    # Only parse once the bytes are known to be authentic.
    try:
        events = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError) as exc:
        log_json(
            'warn',
            correlation_id,
            'Invalid JSON body',
            edge_key=SOURCE,
            error=str(exc),
        )
        raise IngressError(400, 'Invalid JSON') from exc

    # Tailscale sends a batch of events; keep that structure intact rather
    # than inventing a per-event schema.
    return IngressMessage(destination=DESTINATION, payload=events, source=SOURCE)


def _verify_signature(raw_body: bytes, signature_header: Optional[str], secret: str) -> bool:
    """Return True when the header carries a fresh, valid signature for the body."""
    if not signature_header:
        return False

    timestamp, candidates = _parse_signature_header(signature_header)
    if timestamp is None or not candidates:
        return False

    if abs(time.time() - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        return False

    # Sign the timestamp exactly as it arrived, not a reformatted copy of it.
    string_to_sign = f'{timestamp}.'.encode('utf-8') + raw_body
    expected = hmac.new(
        secret.encode('utf-8'),
        string_to_sign,
        hashlib.sha256,
    ).hexdigest().encode('utf-8')

    return any(
        hmac.compare_digest(expected, candidate.encode('utf-8', errors='replace'))
        for candidate in candidates
    )


def _parse_signature_header(signature_header: str) -> Tuple[Optional[str], List[str]]:
    """
    Split the header into its timestamp and its list of v1 signatures.

    The timestamp is returned as the original string so it can be signed
    verbatim; it is only validated as an integer here.
    """
    timestamp: Optional[str] = None
    candidates: List[str] = []

    for part in signature_header.split(','):
        key, separator, value = part.strip().partition('=')
        if not separator:
            continue

        if key == 't':
            try:
                int(value)
            except ValueError:
                return None, []
            timestamp = value
        elif key == 'v1':
            candidates.append(value)

    return timestamp, candidates
