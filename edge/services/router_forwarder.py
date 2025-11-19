import time
from typing import Any, Dict

import requests
from requests import Response as RequestsResponse


class RouterForwarderError(Exception):
    """Base exception for router forwarding issues."""


class RouterTimeoutError(RouterForwarderError):
    """Raised when the router times out."""


class RouterUnavailableError(RouterForwarderError):
    """Raised when the router cannot be reached after retries."""


class RouterForwarder:
    """Encapsulates communication with the router service."""

    def __init__(self, router_url: str, ingress_key: str, timeout: int, log_json):
        self.router_url = router_url
        self.ingress_key = ingress_key
        self.timeout = timeout
        self.log_json = log_json

    def forward(self, body: Dict[str, Any], correlation_id: str, edge_key_name: str, destination: str) -> RequestsResponse:
        """Forward the webhook payload to the router, handling retries and logging."""
        self.log_json(
            'info',
            correlation_id,
            'Forwarding to router',
            edge_key=edge_key_name,
            destination=destination,
        )

        try:
            response = self._send(body, correlation_id)
            self._log_router_response(response, correlation_id, edge_key_name, destination)
            return response
        except requests.exceptions.Timeout as exc:
            self.log_json(
                'error',
                correlation_id,
                'Router timeout',
                edge_key=edge_key_name,
                destination=destination,
            )
            raise RouterTimeoutError('Router request timed out') from exc
        except requests.exceptions.ConnectionError as exc:
            self.log_json(
                'error',
                correlation_id,
                'Router connection failed',
                edge_key=edge_key_name,
                destination=destination,
                error=str(exc),
            )
            return self._retry(body, correlation_id, edge_key_name, destination, exc)
        except Exception as exc:
            self.log_json(
                'error',
                correlation_id,
                'Unexpected router error',
                edge_key=edge_key_name,
                destination=destination,
                error=str(exc),
            )
            raise RouterForwarderError('Unexpected router error') from exc

    def _retry(
        self,
        body: Dict[str, Any],
        correlation_id: str,
        edge_key_name: str,
        destination: str,
        original_exc: Exception,
    ) -> RequestsResponse:
        """Retry router communication once after a short delay."""
        try:
            time.sleep(1)
            self.log_json(
                'info',
                correlation_id,
                'Retrying router connection',
                edge_key=edge_key_name,
                destination=destination,
            )
            response = self._send(body, correlation_id)
            self.log_json(
                'info',
                correlation_id,
                'Retry succeeded',
                edge_key=edge_key_name,
                destination=destination,
                status_code=response.status_code,
            )
            self._log_router_response(response, correlation_id, edge_key_name, destination)
            return response
        except Exception as retry_exc:
            self.log_json(
                'error',
                correlation_id,
                'Retry failed',
                edge_key=edge_key_name,
                destination=destination,
                error=str(retry_exc),
            )
            raise RouterUnavailableError('Router unreachable after retry') from original_exc

    def _send(self, body: Dict[str, Any], correlation_id: str) -> RequestsResponse:
        """Send the payload to the router."""
        return requests.post(
            self.router_url,
            json=body,
            headers={
                'Authorization': f'Bearer {self.ingress_key}',
                'X-Correlation-ID': correlation_id,
                'Content-Type': 'application/json',
            },
            timeout=self.timeout,
        )

    def _log_router_response(
        self,
        response: RequestsResponse,
        correlation_id: str,
        edge_key_name: str,
        destination: str,
    ) -> None:
        """Log router response metadata."""
        duration_ms = int(response.elapsed.total_seconds() * 1000) if response.elapsed else None
        payload: Dict[str, Any] = {
            'edge_key': edge_key_name,
            'destination': destination,
            'status_code': response.status_code,
        }
        if duration_ms is not None:
            payload['duration_ms'] = duration_ms
        self.log_json('info', correlation_id, 'Router responded', **payload)
