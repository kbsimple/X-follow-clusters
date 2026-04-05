"""X API authentication module.

Provides credential loading from environment variables and verification
via GET /2/users/me using tweepy.

Usage:
    from src.auth import get_auth, verify_credentials

    auth = get_auth()
    user = verify_credentials(auth)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import tweepy


class AuthError(Exception):
    """Raised when X API authentication fails or credentials are missing.

    Attributes:
        message: Human-readable error description.
        status_code: HTTP status code if available (e.g. 401, 429).
        response_body: Raw response body for debugging.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"(HTTP {self.status_code})")
        if self.response_body:
            parts.append(f"Response: {self.response_body}")
        return " ".join(parts)


@dataclass
class XAuth:
    """X API OAuth 1.0a credentials.

    Attributes:
        api_key: X API key (Consumer Key).
        api_secret: X API secret (Consumer Secret).
        access_token: OAuth access token.
        access_token_secret: OAuth access token secret.
        bearer_token: Bearer token for app-only auth (optional).
    """

    api_key: str
    api_secret: str
    access_token: str
    access_token_secret: str
    bearer_token: str | None = None


def get_auth() -> XAuth:
    """Load X API credentials from environment variables.

    Required environment variables:
        X_API_KEY: X API key (Consumer Key)
        X_API_SECRET: X API secret (Consumer Secret)
        X_ACCESS_TOKEN: OAuth access token
        X_ACCESS_TOKEN_SECRET: OAuth access token secret

    Optional:
        X_BEARER_TOKEN: Bearer token for app-only authentication

    Returns:
        XAuth instance populated with credentials.

    Raises:
        AuthError: If any required environment variable is missing.
    """
    missing: list[str] = []
    api_key = os.environ.get("X_API_KEY")
    api_secret = os.environ.get("X_API_SECRET")
    access_token = os.environ.get("X_ACCESS_TOKEN")
    access_token_secret = os.environ.get("X_ACCESS_TOKEN_SECRET")
    bearer_token = os.environ.get("X_BEARER_TOKEN")

    if not api_key:
        missing.append("X_API_KEY")
    if not api_secret:
        missing.append("X_API_SECRET")
    if not access_token:
        missing.append("X_ACCESS_TOKEN")
    if not access_token_secret:
        missing.append("X_ACCESS_TOKEN_SECRET")

    if missing:
        raise AuthError(
            f"Missing required X API environment variables: {', '.join(missing)}"
        )

    return XAuth(
        api_key=api_key,
        api_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        bearer_token=bearer_token,
    )


def verify_credentials(auth: XAuth) -> dict[str, Any]:
    """Verify X API credentials by calling GET /2/users/me.

    Creates a tweepy Client using OAuth1UserHandler and calls the
    /2/users/me endpoint to confirm credentials are valid.

    Args:
        auth: XAuth instance with credentials to verify.

    Returns:
        Dict containing the authenticated user's profile data from GET /2/users/me.

    Raises:
        AuthError: If credentials are invalid (401) or rate limited (429).
    """
    client = tweepy.Client(
        consumer_key=auth.api_key,
        consumer_secret=auth.api_secret,
        access_token=auth.access_token,
        access_token_secret=auth.access_token_secret,
        bearer_token=auth.bearer_token,
    )

    try:
        response = client.get_me()
        if response is None:
            raise AuthError("GET /2/users/me returned None")
        return response
    except tweepy.TweepyException as e:
        # Extract HTTP status code and response body from the exception if available
        status_code: int | None = None
        response_body: str | None = None

        # tweepy exceptions may have a .response attribute
        if hasattr(e, "response") and e.response is not None:
            status_code = getattr(e.response, "status_code", None)
            response_body = getattr(e.response, "text", None)

        error_msg = str(e)

        # Add helpful context for common error codes
        if status_code == 401:
            raise AuthError(
                "X API authentication failed: credentials are invalid or expired",
                status_code=status_code,
                response_body=response_body,
            ) from e
        elif status_code == 429:
            raise AuthError(
                "X API rate limit exceeded",
                status_code=status_code,
                response_body=response_body,
            ) from e
        else:
            raise AuthError(
                f"X API request failed: {error_msg}",
                status_code=status_code,
                response_body=response_body,
            ) from e
