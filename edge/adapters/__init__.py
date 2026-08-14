"""
Ingress adapters for the edge service.

An adapter turns an externally-shaped webhook request into an IngressMessage.
Each adapter owns the authentication and payload format dictated by its
external caller, and knows nothing about the eventual internal recipient.

Adapters are plain modules exposing a single function:

    adapt(config: EdgeConfig, log_json, correlation_id: str) -> IngressMessage

There is deliberately no registry, base class, or discovery mechanism.
"""

from .types import IngressError, IngressMessage  # noqa: F401
