"""
Shared constants for the router suite.

Kept out of conftest.py because both suites have a conftest and only one can
own that module name in a single interpreter.
"""

INGRESS_KEY = 'router-ingress-key'

ROUTES = {
    'wikimgr': {
        'method': 'POST',
        'url': 'http://wikimgr.internal:8000/append',
        'auth_env': None,
        'timeout_seconds': 10,
    },
    'tailscale': {
        'method': 'POST',
        'url': 'http://notifier.internal:9000/tailscale',
        'auth_env': None,
        'timeout_seconds': 10,
    },
}
