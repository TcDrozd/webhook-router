import logging
import sys
from pathlib import Path
from typing import Dict, Any

import yaml


BASE_DIR = Path(__file__).resolve().parent.parent
ROUTES_FILE = BASE_DIR / 'routes.yml'
logger = logging.getLogger(__name__)


def load_routes() -> Dict[str, Dict[str, Any]]:
    """
    Load and validate destination routes from the YAML configuration file.
    """
    try:
        with ROUTES_FILE.open('r') as f:
            config = yaml.safe_load(f)

        if not config or 'destinations' not in config:
            logger.error('Invalid routes file: missing "destinations" key')
            sys.exit(1)

        routes = config['destinations']

        for dest_name, route_config in routes.items():
            if 'url' not in route_config:
                logger.error('Route "%s" missing required "url" field', dest_name)
                sys.exit(1)

            route_config.setdefault('method', 'POST')
            route_config.setdefault('timeout_seconds', 25)
            route_config.setdefault('auth_env', None)

        logger.info('Loaded %d routes from %s', len(routes), ROUTES_FILE)
        return routes

    except FileNotFoundError:
        logger.error('Routes file not found: %s', ROUTES_FILE)
        sys.exit(1)
    except yaml.YAMLError as exc:
        logger.error('Invalid YAML in routes file: %s', exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.error('Failed to load routes: %s', exc)
        sys.exit(1)
