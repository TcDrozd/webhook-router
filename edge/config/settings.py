import os
import sys
import json
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
    edge_keys: Dict[str, str]  # token -> owner


def _load_edge_keys_from_file(logger: Logger) -> Dict[str, str]:
    """
    Load edge keys from a JSON file pointed to by EDGE_KEYS_FILE.

    Expected JSON (plaintext, first pass):
      {
        "trevor": "SUPER_SECRET_KEY",
        "dev": "another_edge_key_here"
      }

    Returned mapping:
      { "SUPER_SECRET_KEY": "trevor", "another_edge_key_here": "bob" }
    """
    path = os.getenv("EDGE_KEYS_FILE", "").strip()
    if not path:
        logger.error("EDGE_KEYS_FILE environment variable not set")
        sys.exit(1)

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        logger.error("EDGE_KEYS_FILE not found: %s", path)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        logger.error("EDGE_KEYS_FILE contains invalid JSON (%s): %s", path, str(exc))
        sys.exit(1)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to read EDGE_KEYS_FILE (%s): %s", path, str(exc))
        sys.exit(1)

    if not isinstance(raw, dict):
        logger.error("EDGE_KEYS_FILE must contain a JSON object of {owner: token}")
        sys.exit(1)

    edge_keys: Dict[str, str] = {}
    for owner, token in raw.items():
        if not isinstance(owner, str) or not isinstance(token, str):
            logger.error("EDGE_KEYS_FILE entries must be strings. Bad entry: %r: %r", owner, token)
            sys.exit(1)

        owner_clean = owner.strip()
        token_clean = token.strip()

        if not owner_clean or not token_clean:
            logger.error("EDGE_KEYS_FILE contains empty owner/token. Bad entry: %r: %r", owner, token)
            sys.exit(1)

        if token_clean in edge_keys and edge_keys[token_clean] != owner_clean:
            logger.error(
                "Duplicate token found in EDGE_KEYS_FILE for owners %r and %r",
                edge_keys[token_clean],
                owner_clean,
            )
            sys.exit(1)

        edge_keys[token_clean] = owner_clean

    if not edge_keys:
        logger.error("No valid edge keys found in EDGE_KEYS_FILE: %s", path)
        sys.exit(1)

    return edge_keys


def load_edge_config(logger: Logger) -> EdgeConfig:
    """Load edge configuration from environment variables."""
    router_url = os.getenv("ROUTER_URL", "http://localhost:8081/ingest")
    router_ingress_key = os.getenv("ROUTER_INGRESS_KEY", "").strip()
    request_timeout = int(os.getenv("REQUEST_TIMEOUT", "30"))
    max_body_size_mb = int(os.getenv("MAX_BODY_SIZE_MB", "1"))
    rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "100"))

    edge_keys = _load_edge_keys_from_file(logger)

    if not router_ingress_key:
        logger.error("ROUTER_INGRESS_KEY environment variable not set")
        sys.exit(1)

    return EdgeConfig(
        router_url=router_url,
        router_ingress_key=router_ingress_key,
        request_timeout=request_timeout,
        max_body_size_mb=max_body_size_mb,
        rate_limit_per_minute=rate_limit_per_minute,
        edge_keys=edge_keys,
    )