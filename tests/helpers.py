"""
Shared test helpers.

The edge and router services each expose flat top-level modules (`config`,
`services`, `http_handlers`, `logging_utils`) that only resolve because their
Dockerfiles set PYTHONPATH=/app. Those names collide between the two services,
so a test must activate exactly one service at a time before importing from it.

`run_tests.sh` runs tests/edge and tests/router as separate pytest processes,
which makes that isolation structural. `activate_service` additionally makes a
single combined `pytest` run correct, by re-priming sys.path and evicting the
other service's modules before each import.

Neither service's app.py is ever imported: both call create_app() at import
time and sys.exit(1) without their environment configured. The tests drive the
blueprint factories directly, which already take everything by injection.
"""

import importlib
import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SERVICE_DIRS = ('edge', 'router')

# Top-level module names defined by both services.
SHARED_MODULE_NAMES = (
    'adapters',
    'app',
    'config',
    'http_handlers',
    'logging_utils',
    'services',
)


_active_service = None


def activate_service(name: str) -> None:
    """
    Make `name`'s modules the ones that bare imports resolve to.

    This is a no-op when `name` is already active. That matters: purging
    sys.modules mid-suite would hand out fresh class objects, so an exception
    class imported by a test would no longer be the one the handler catches.
    """
    global _active_service

    if _active_service == name:
        return

    for module_name in list(sys.modules):
        root = module_name.split('.', 1)[0]
        if root in SHARED_MODULE_NAMES:
            del sys.modules[module_name]

    for service in SERVICE_DIRS:
        service_dir = str(REPO_ROOT / service)
        while service_dir in sys.path:
            sys.path.remove(service_dir)

    sys.path.insert(0, str(REPO_ROOT / name))
    _active_service = name


def import_service_module(service: str, module_name: str):
    """Import a module from `service`, activating it first."""
    activate_service(service)
    return importlib.import_module(module_name)


class FakeResponse:
    """Stand-in for a requests.Response, with the attributes the code reads."""

    def __init__(self, content=b'{"status": "ok"}', status_code=200, content_type='application/json'):
        self.content = content
        self.status_code = status_code
        self.headers = {'Content-Type': content_type}
        self.elapsed = timedelta(milliseconds=12)


def collecting_logger():
    """A log_json stand-in that records entries instead of writing them."""
    entries = []

    def log_json(level, correlation_id, message, **kwargs):
        entries.append({
            'level': level,
            'correlation_id': correlation_id,
            'message': message,
            **kwargs,
        })

    log_json.entries = entries
    return log_json
