from typing import Optional


def validate_bearer_token(auth_header: Optional[str], expected_token: str) -> bool:
    """Validate that the provided Authorization header matches the ingress key."""
    if not auth_header:
        return False

    parts = auth_header.split(' ')
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return False

    return parts[1] == expected_token
