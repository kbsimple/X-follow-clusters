"""X API authentication.

Exports:
    XAuth: Dataclass holding X API OAuth credentials.
    get_auth: Load credentials from environment variables.
    verify_credentials: Verify credentials via GET /2/users/me.
    AuthError: Exception raised on auth failure or missing credentials.
"""

from src.auth.x_auth import (
    AuthError,
    XAuth,
    get_auth,
    verify_credentials,
)

__all__ = [
    "AuthError",
    "XAuth",
    "get_auth",
    "verify_credentials",
]
