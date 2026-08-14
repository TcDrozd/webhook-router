"""Canonical ingress types shared by every ingress adapter."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IngressMessage:
    """
    The canonical result of an ingress adapter.

    Every adapter authenticates and parses according to its own external
    protocol, then reduces the request to this shape. Everything downstream
    of an adapter deals only in IngressMessage.
    """

    destination: str
    payload: Any
    source: str


class IngressError(Exception):
    """
    Raised by an adapter when a request cannot be accepted.

    Carries the HTTP status and the client-facing message so the shared
    handler can render the project's standard {'error': ...} response
    without knowing which adapter raised it.
    """

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
