import os
from typing import Dict, Any, Callable

import requests

LogFn = Callable[[str, str, str], None]


def _emit_log(log_json: Callable[..., None], level: str, correlation_id: str, message: str, **kwargs) -> None:
    log_json(level, correlation_id, message, **kwargs)


def forward_to_destination(
    destination: str,
    route_config: Dict[str, Any],
    payload: Dict[str, Any],
    correlation_id: str,
    log_json: Callable[..., None],
) -> requests.Response:
    """
    Forward a payload to an internal destination and return the upstream response.
    """
    forward_headers = {
        'X-Correlation-ID': correlation_id,
        'Content-Type': 'application/json'
    }

    if route_config['auth_env']:
        auth_token = os.getenv(route_config['auth_env'])
        if auth_token:
            forward_headers['Authorization'] = f'Bearer {auth_token}'
        else:
            _emit_log(
                log_json,
                'warn',
                correlation_id,
                'Auth token env var not set',
                destination=destination,
                auth_env=route_config['auth_env']
            )

    _emit_log(
        log_json,
        'info',
        correlation_id,
        'Forwarding to internal service',
        destination=destination,
        url=route_config['url'],
        method=route_config['method']
    )

    response = requests.request(
        method=route_config['method'],
        url=route_config['url'],
        json=payload,
        headers=forward_headers,
        timeout=route_config['timeout_seconds']
    )

    _emit_log(
        log_json,
        'info',
        correlation_id,
        'Internal service responded',
        destination=destination,
        status_code=response.status_code,
        duration_ms=int(response.elapsed.total_seconds() * 1000)
    )

    return response
