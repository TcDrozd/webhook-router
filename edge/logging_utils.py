import json
import logging
import sys
from datetime import datetime


def setup_logging() -> logging.Logger:
    """Configure structured logging to stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s',
        stream=sys.stdout
    )
    return logging.getLogger('edge')


def log_json(logger: logging.Logger, level: str, correlation_id: str, message: str, **kwargs) -> None:
    """Emit a structured JSON log entry."""
    log_entry = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'level': level,
        'correlation_id': correlation_id,
        'service': 'edge',
        'message': message,
        **kwargs
    }
    logger.info(json.dumps(log_entry))
