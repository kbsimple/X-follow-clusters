"""X API authentication module.

Provides credential loading from environment variables and verification
via GET /2/users/me using tweepy.

Usage:
    from src.auth import get_auth, verify_credentials

    auth = get_auth()
    user = verify_credentials(auth)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
import tweepy

logger = logging.getLogger(__name__)


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
    """X API OAuth 2.0 PKCE credentials.

    Attributes:
        client_id: X API client ID (App ID).
        client_secret: X API client secret (App Secret).
        access_token: OAuth 2.0 access token (Bearer).
        refresh_token: OAuth 2.0 refresh token.
        bearer_token: Bearer token for app-only auth (optional).
    """

    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    bearer_token: str | None = None


def get_auth() -> XAuth:
    """Load X API credentials from environment variables.

    Required environment variables:
        X_CLIENT_ID: X API client ID (App ID)
        X_CLIENT_SECRET: X API client secret (App Secret)
        X_ACCESS_TOKEN: OAuth 2.0 access token
        X_REFRESH_TOKEN: OAuth 2.0 refresh token

    Optional:
        X_BEARER_TOKEN: Bearer token for app-only authentication

    Returns:
        XAuth instance populated with credentials.

    Raises:
        AuthError: If X_CLIENT_ID or X_CLIENT_SECRET is missing.
    """
    client_id = os.environ.get("X_CLIENT_ID")
    client_secret = os.environ.get("X_CLIENT_SECRET")
    access_token = os.environ.get("X_ACCESS_TOKEN")
    refresh_token = os.environ.get("X_REFRESH_TOKEN")
    bearer_token = os.environ.get("X_BEARER_TOKEN")

    if not client_id:
        raise AuthError(
            "Missing required X API environment variable: X_CLIENT_ID"
        )
    if not client_secret:
        raise AuthError(
            "Missing required X API environment variable: X_CLIENT_SECRET"
        )

    # access_token may be absent during first-run OAuth flow
    # refresh_token may also be absent initially
    return XAuth(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token or "",
        refresh_token=refresh_token or "",
        bearer_token=bearer_token,
    )


def verify_credentials(auth: XAuth) -> dict[str, Any]:
    """Verify X API credentials by calling GET /2/users/me.

    Creates a tweepy Client using the OAuth 2.0 access token and calls the
    /2/users/me endpoint to confirm credentials are valid.

    Args:
        auth: XAuth instance with credentials to verify.

    Returns:
        Dict containing the authenticated user's profile data from GET /2/users/me.

    Raises:
        AuthError: If credentials are invalid (401) or rate limited (429).
    """
    client = tweepy.Client(bearer_token=auth.access_token)

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


# Module-level OAuth2UserHandler instance for PKCE flow
_oauth2_handler: tweepy.OAuth2UserHandler | None = None


def get_authorization_url(client_id: str, client_secret: str) -> str:
    """Create OAuth 2.0 PKCE authorization URL.

    Creates a tweepy.OAuth2UserHandler and returns the authorization URL
    the user must visit in their browser to authorize the app.

    Args:
        client_id: X API client ID (App ID).
        client_secret: X API client secret (App Secret).

    Returns:
        Authorization URL to visit in browser.

    Stores the handler instance for use in exchange_code_for_token().
    """
    global _oauth2_handler
    _oauth2_handler = tweepy.OAuth2UserHandler(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://127.0.0.1:8080/callback",
        scope=["tweet.read", "users.read", "list.read", "list.write", "offline.access"],
    )
    return _oauth2_handler.get_authorization_url()


def exchange_code_for_token(code: str) -> tuple[str, str]:
    """Exchange authorization code for access and refresh tokens.

    Uses the OAuth2UserHandler stored by get_authorization_url() to
    fetch the access token and refresh token using the authorization code.

    Args:
        code: Authorization code returned from X OAuth redirect.

    Returns:
        Tuple of (access_token, refresh_token).
    """
    if _oauth2_handler is None:
        raise AuthError(
            "OAuth2UserHandler not initialized. Call get_authorization_url() first."
        )
    logger.info("Exchanging authorization code for access token…")
    try:
        access_token = _oauth2_handler.fetch_token(authorization_response=code)
        logger.info("Access token received.")
    except requests.exceptions.Timeout:
        logger.error("Token exchange timed out after 30 seconds.")
        raise AuthError("Token exchange timed out. X API may be slow or unreachable.")
    except requests.exceptions.ConnectionError as e:
        logger.error("Token exchange connection failed: %s", e)
        raise AuthError(f"Token exchange connection failed: {e}")
    except Exception as e:
        logger.error("Token exchange failed: %s", e)
        raise AuthError(f"Token exchange failed: {e}")
    # fetch_token returns the full token dict; extract access_token and refresh_token
    access_token_str = access_token.get("access_token", "") if isinstance(access_token, dict) else access_token
    refresh_token_str = _oauth2_handler.refresh_token or ""
    logger.info("Refresh token: %s", "received" if refresh_token_str else "not received")
    return access_token_str, refresh_token_str


def save_tokens(access_token: str, refresh_token: str, path: str | Path = "data/tokens.json") -> None:
    """Persist OAuth 2.0 tokens to a JSON file.

    Args:
        access_token: OAuth 2.0 access token.
        refresh_token: OAuth 2.0 refresh token.
        path: File path for token storage. Defaults to data/tokens.json.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"access_token": access_token, "refresh_token": refresh_token}, f)


def load_tokens(path: str | Path = "data/tokens.json") -> tuple[str, str] | None:
    """Load OAuth 2.0 tokens from a JSON file.

    Args:
        path: File path for token storage. Defaults to data/tokens.json.

    Returns:
        Tuple of (access_token, refresh_token) if file exists, else None.
    """
    try:
        with open(path) as f:
            data = json.load(f)
        return data["access_token"], data["refresh_token"]
    except FileNotFoundError:
        return None


def wait_for_callback(port: int = 8080, timeout: int = 300) -> str:
    """Start a temporary HTTP server to capture the OAuth callback code.

    Starts an HTTP server on 127.0.0.1:port that listens for a single
    GET request to /callback?code=XXX, extracts the code parameter,
    and returns it. The server shuts down after the callback is received
    or after the timeout elapses.

    Args:
        port: Port to listen on. Defaults to 8080.
        timeout: Seconds to wait before raising TimeoutError. Defaults to 300.

    Returns:
        The authorization code from the callback redirect.

    Raises:
        TimeoutError: If no callback is received within the timeout period.
    """
    code_received = threading.Event()
    received_code = [None]

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/callback"):
                qs = parse_qs(urlparse(self.path).query)
                if "code" in qs:
                    received_code[0] = qs["code"][0]
                    code_received.set()
                    logger.info("Callback received. Authorization code captured.")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<html><body>Authorization complete. You may close this window.</body></html>")
                else:
                    logger.warning("Callback received but no 'code' parameter found.")
                    self.send_response(400)
                    self.wfile.write(b"Missing code parameter")
            else:
                self.send_response(404)

        def log_message(self, *args):
            pass  # suppress default HTTP logging

    logger.info("Starting OAuth callback server on port %d (timeout=%ds)…", port, timeout)
    server = HTTPServer(("127.0.0.1", port), CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    if not code_received.wait(timeout):
        server.shutdown()
        logger.error("OAuth callback timed out after %d seconds.", timeout)
        raise TimeoutError(f"No callback received within {timeout} seconds")

    server.shutdown()
    thread.join()
    logger.info("Callback server shut down.")
    return received_code[0]


def ensure_authenticated() -> XAuth:
    """Ensure valid OAuth 2.0 tokens are available, running interactive flow if needed.

    Orchestrates the full first-run OAuth 2.0 PKCE flow:
      1. Try loading tokens from data/tokens.json
      2. If tokens exist, build XAuth from stored tokens + env var client_id/client_secret
      3. If no tokens, start interactive OAuth 2.0 PKCE flow:
         a. Get authorization URL
         b. Print URL for user to open in browser
         c. Start callback server
         d. Exchange code for tokens
         e. Save tokens to data/tokens.json
      4. Return XAuth instance

    Returns:
        XAuth instance with valid access and refresh tokens.

    Raises:
        AuthError: If X_CLIENT_ID/X_CLIENT_SECRET env vars are missing,
                   or if the OAuth flow fails.
    """
    client_id = os.environ.get("X_CLIENT_ID")
    client_secret = os.environ.get("X_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise AuthError("X_CLIENT_ID and X_CLIENT_SECRET must be set in environment")

    # Try loading stored tokens
    tokens = load_tokens()
    if tokens:
        access_token, refresh_token = tokens
        logger.info("Loaded stored tokens from data/tokens.json.")
        return XAuth(
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    # First-run: initiate OAuth 2.0 PKCE
    logger.info("No stored tokens found. Initiating OAuth 2.0 PKCE flow.")
    auth_url = get_authorization_url(client_id, client_secret)
    logger.info("Authorization URL generated.")
    print(f"Open this URL in your browser and authorize:\n{auth_url}")

    logger.info("Waiting for OAuth callback on port 8080…")
    code = wait_for_callback()
    logger.info("Authorization code received. Exchanging for tokens…")
    access_token, refresh_token = exchange_code_for_token(code)
    save_tokens(access_token, refresh_token)
    logger.info("Tokens saved to data/tokens.json.")

    return XAuth(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        refresh_token=refresh_token,
    )
