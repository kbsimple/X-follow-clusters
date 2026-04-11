"""Tests for X API authentication module.

These tests verify:
1. get_auth() loads credentials from environment variables
2. get_auth() raises AuthError when required vars are missing
3. verify_credentials() calls tweepy Client and GET /2/users/me
4. verify_credentials() raises AuthError on 401 (unauthorized)
5. verify_credentials() raises AuthError on 429 (rate limit)
"""

import pytest
from unittest.mock import MagicMock, patch


class TestGetAuth:
    """Test get_auth() environment variable loading."""

    def test_get_auth_with_all_env_vars_returns_xauth(self, monkeypatch):
        """Test that get_auth() returns XAuth with correct values when all env vars are set."""
        monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("X_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("X_REFRESH_TOKEN", "test_refresh_token")
        monkeypatch.setenv("X_BEARER_TOKEN", "test_bearer_token")

        from src.auth.x_auth import get_auth, XAuth

        auth = get_auth()

        assert isinstance(auth, XAuth)
        assert auth.client_id == "test_client_id"
        assert auth.client_secret == "test_client_secret"
        assert auth.access_token == "test_access_token"
        assert auth.refresh_token == "test_refresh_token"
        assert auth.bearer_token == "test_bearer_token"

    def test_get_auth_raises_auth_error_when_client_id_missing(self, monkeypatch):
        """Test that get_auth() raises AuthError when X_CLIENT_ID is missing."""
        monkeypatch.delenv("X_CLIENT_ID", raising=False)
        monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("X_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("X_REFRESH_TOKEN", "test_refresh_token")

        from src.auth.x_auth import get_auth, AuthError

        with pytest.raises(AuthError) as exc_info:
            get_auth()

        assert "X_CLIENT_ID" in str(exc_info.value)
        assert "missing" in str(exc_info.value).lower()

    def test_get_auth_raises_auth_error_when_client_secret_missing(self, monkeypatch):
        """Test that get_auth() raises AuthError when X_CLIENT_SECRET is missing."""
        monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
        monkeypatch.delenv("X_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("X_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("X_REFRESH_TOKEN", "test_refresh_token")

        from src.auth.x_auth import get_auth, AuthError

        with pytest.raises(AuthError) as exc_info:
            get_auth()

        assert "X_CLIENT_SECRET" in str(exc_info.value)
        assert "missing" in str(exc_info.value).lower()


class TestVerifyCredentials:
    """Test verify_credentials() against GET /2/users/me."""

    def test_verify_credentials_calls_get_me(self, monkeypatch):
        """Test that verify_credentials() calls tweepy Client.get_me()."""
        monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("X_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("X_REFRESH_TOKEN", "test_refresh_token")

        from src.auth.x_auth import XAuth, verify_credentials

        auth = XAuth(
            client_id="test_client_id",
            client_secret="test_client_secret",
            access_token="test_access_token",
            refresh_token="test_refresh_token",
        )

        mock_client = MagicMock()
        mock_client.get_me.return_value = {"data": {"id": "123", "username": "testuser"}}

        with patch("src.auth.x_auth.tweepy.Client", return_value=mock_client):
            result = verify_credentials(auth)

        mock_client.get_me.assert_called_once()
        assert result == {"data": {"id": "123", "username": "testuser"}}

    def test_verify_credentials_raises_auth_error_on_401(self, monkeypatch):
        """Test that verify_credentials() raises AuthError on 401 response."""
        monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("X_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("X_REFRESH_TOKEN", "test_refresh_token")

        from src.auth.x_auth import XAuth, verify_credentials, AuthError

        auth = XAuth(
            client_id="test_client_id",
            client_secret="test_client_secret",
            access_token="test_access_token",
            refresh_token="test_refresh_token",
        )

        import tweepy

        mock_client = MagicMock()
        error_response = MagicMock()
        error_response.status_code = 401
        error_response.text = "Unauthorized"

        fake_exc = tweepy.TweepyException("401 Unauthorized")
        fake_exc.response = error_response

        mock_client.get_me.side_effect = fake_exc

        with patch("src.auth.x_auth.tweepy.Client", return_value=mock_client):
            with pytest.raises(AuthError) as exc_info:
                verify_credentials(auth)

        assert "401" in str(exc_info.value) or "Unauthorized" in str(exc_info.value)

    def test_verify_credentials_raises_auth_error_on_rate_limit_429(self, monkeypatch):
        """Test that verify_credentials() raises AuthError with message about rate limits on 429."""
        monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("X_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("X_REFRESH_TOKEN", "test_refresh_token")

        from src.auth.x_auth import XAuth, verify_credentials, AuthError

        auth = XAuth(
            client_id="test_client_id",
            client_secret="test_client_secret",
            access_token="test_access_token",
            refresh_token="test_refresh_token",
        )

        import tweepy

        mock_client = MagicMock()
        error_response = MagicMock()
        error_response.status_code = 429
        error_response.text = "Rate limit exceeded"

        fake_exc = tweepy.TweepyException("429 Rate limit exceeded")
        fake_exc.response = error_response

        mock_client.get_me.side_effect = fake_exc

        with patch("src.auth.x_auth.tweepy.Client", return_value=mock_client):
            with pytest.raises(AuthError) as exc_info:
                verify_credentials(auth)

        error_msg = str(exc_info.value).lower()
        assert "429" in str(exc_info.value) or "rate" in error_msg


class TestTokenPersistence:
    """Test save_tokens() and load_tokens() functions."""

    def test_save_and_load_tokens_roundtrip(self, tmp_path):
        """Test that tokens can be saved and loaded correctly."""
        from src.auth.x_auth import save_tokens, load_tokens
        token_file = tmp_path / "tokens.json"
        save_tokens("test_access_token", "test_refresh_token", token_file)
        result = load_tokens(token_file)
        assert result == ("test_access_token", "test_refresh_token")

    def test_load_tokens_returns_none_if_file_missing(self):
        """Test that load_tokens returns None when file does not exist."""
        from src.auth.x_auth import load_tokens
        result = load_tokens("/nonexistent/path/tokens.json")
        assert result is None

    def test_save_tokens_creates_directory(self, tmp_path):
        """Test that save_tokens creates parent directories."""
        from src.auth.x_auth import save_tokens
        token_file = tmp_path / "subdir" / "tokens.json"
        save_tokens("at", "rt", token_file)
        assert token_file.exists()


class TestOAuth2UserHandlerFlow:
    """Test OAuth 2.0 PKCE handler flow."""

    def test_get_authorization_url_returns_url(self, monkeypatch):
        """Test that get_authorization_url returns a valid X authorization URL."""
        mock_handler = MagicMock()
        mock_handler.get_authorization_url.return_value = "https://x.com/i/oauth2/authorize?client_id=test"
        monkeypatch.setattr("src.auth.x_auth.tweepy.OAuth2UserHandler", lambda **kwargs: mock_handler)

        from src.auth.x_auth import get_authorization_url
        url = get_authorization_url("test_client_id", "test_client_secret")
        assert "x.com/i/oauth2/authorize" in url
        mock_handler.get_authorization_url.assert_called_once()

    def test_exchange_code_for_token(self, monkeypatch):
        """Test that exchange_code_for_token exchanges code for tokens."""
        mock_handler = MagicMock()
        mock_handler.fetch_token.return_value = {"access_token": "exchanged_access_token", "refresh_token": "exchanged_refresh_token"}
        monkeypatch.setattr("src.auth.x_auth.tweepy.OAuth2UserHandler", lambda **kwargs: mock_handler)

        from src.auth.x_auth import get_authorization_url, exchange_code_for_token
        # First set up the handler
        get_authorization_url("test_client_id", "test_client_secret")
        # Then exchange
        import src.auth.x_auth as x_auth_module
        x_auth_module._oauth2_handler = mock_handler
        access_token, refresh_token = exchange_code_for_token("auth_code_123")
        mock_handler.fetch_token.assert_called_once()

    def test_ensure_authenticated_loads_existing_tokens(self, monkeypatch, tmp_path):
        """Test ensure_authenticated returns XAuth if tokens.json exists."""
        monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")
        token_file = tmp_path / "tokens.json"
        # Pre-create tokens file
        import json
        token_file.write_text(json.dumps({"access_token": "stored_at", "refresh_token": "stored_rt"}))

        import src.auth.x_auth as x_auth_module
        original_load_tokens = x_auth_module.load_tokens
        x_auth_module.load_tokens = lambda p=None: ("stored_at", "stored_rt")

        from src.auth.x_auth import ensure_authenticated
        auth = ensure_authenticated()
        assert auth.access_token == "stored_at"
        assert auth.refresh_token == "stored_rt"

        x_auth_module.load_tokens = original_load_tokens

    def test_ensure_authenticated_raises_when_client_id_missing(self, monkeypatch):
        """Test ensure_authenticated raises AuthError when X_CLIENT_ID is missing."""
        monkeypatch.delenv("X_CLIENT_ID", raising=False)
        monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")

        from src.auth.x_auth import ensure_authenticated, AuthError
        with pytest.raises(AuthError) as exc_info:
            ensure_authenticated()

        assert "X_CLIENT_ID" in str(exc_info.value)
