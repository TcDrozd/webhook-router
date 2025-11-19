import os
import sys
from dataclasses import dataclass
from typing import Dict

from logging import Logger


@dataclass(frozen=True)
class EdgeConfig:
    router_url: str
    router_ingress_key: str
    request_timeout: int
    max_body_size_mb: int
    rate_limit_per_minute: int
    edge_keys: Dict[str, str]


def _parse_edge_keys(logger: Logger) -> Dict[str, str]:
    """Parse EDGE_KEYS env var into a dict of token -> name."""
    keys_str = os.getenv('EDGE_KEYS', '')
    if not keys_str:
        logger.error('EDGE_KEYS environment variable not set')
        sys.exit(1)

    keys: Dict[str, str] = {}
    for raw_pair in keys_str.split(','):
        pair = raw_pair.strip()
        if not pair:
            continue
        try:
            name, key = pair.split(':', 1)
            keys[key.strip()] = name.strip()
        except ValueError:
            logger.error('Invalid EDGE_KEYS format: %s', pair)
            sys.exit(1)

    if not keys:
        logger.error('No valid edge keys found in EDGE_KEYS')
        sys.exit(1)

    return keys


def load_edge_config(logger: Logger) -> EdgeConfig:
    """Load edge configuration from environment variables."""
    router_url = os.getenv('ROUTER_URL', 'http://localhost:8081/ingest')
    router_ingress_key = os.getenv('ROUTER_INGRESS_KEY', '')
    request_timeout = int(os.getenv('REQUEST_TIMEOUT', '30'))
    max_body_size_mb = int(os.getenv('MAX_BODY_SIZE_MB', '1'))
    rate_limit_per_minute = int(os.getenv('RATE_LIMIT_PER_MINUTE', '100'))
    edge_keys = _parse_edge_keys(logger)

    if not router_ingress_key:
        logger.error('ROUTER_INGRESS_KEY environment variable not set')
        sys.exit(1)

    return EdgeConfig(
        router_url=router_url,
        router_ingress_key=router_ingress_key,
        request_timeout=request_timeout,
        max_body_size_mb=max_body_size_mb,
        rate_limit_per_minute=rate_limit_per_minute,
        edge_keys=edge_keys,
    )
