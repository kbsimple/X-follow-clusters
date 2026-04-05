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
        monkeypatch.setenv("X_API_KEY", "test_api_key")
        monkeypatch.setenv("X_API_SECRET", "test_api_secret")
        monkeypatch.setenv("X_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "test_access_token_secret")
        monkeypatch.setenv("X_BEARER_TOKEN", "test_bearer_token")

        from src.auth.x_auth import get_auth, XAuth

        auth = get_auth()

        assert isinstance(auth, XAuth)
        assert auth.api_key == "test_api_key"
        assert auth.api_secret == "test_api_secret"
        assert auth.access_token == "test_access_token"
        assert auth.access_token_secret == "test_access_token_secret"
        assert auth.bearer_token == "test_bearer_token"

    def test_get_auth_raises_auth_error_when_api_key_missing(self, monkeypatch):
        """Test that get_auth() raises AuthError when X_API_KEY is missing."""
        monkeypatch.delenv("X_API_KEY", raising=False)
        monkeypatch.setenv("X_API_SECRET", "test_api_secret")
        monkeypatch.setenv("X_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "test_access_token_secret")

        from src.auth.x_auth import get_auth, AuthError

        with pytest.raises(AuthError) as exc_info:
            get_auth()

        assert "X_API_KEY" in str(exc_info.value)
        assert "missing" in str(exc_info.value).lower()

    def test_get_auth_raises_auth_error_when_access_token_missing(self, monkeypatch):
        """Test that get_auth() raises AuthError when X_ACCESS_TOKEN is missing."""
        monkeypatch.setenv("X_API_KEY", "test_api_key")
        monkeypatch.setenv("X_API_SECRET", "test_api_secret")
        monkeypatch.delenv("X_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "test_access_token_secret")

        from src.auth.x_auth import get_auth, AuthError

        with pytest.raises(AuthError) as exc_info:
            get_auth()

        assert "X_ACCESS_TOKEN" in str(exc_info.value)
        assert "missing" in str(exc_info.value).lower()


class TestVerifyCredentials:
    """Test verify_credentials() against GET /2/users/me."""

    def test_verify_credentials_calls_get_me(self, monkeypatch):
        """Test that verify_credentials() calls tweepy Client.get_me()."""
        monkeypatch.setenv("X_API_KEY", "test_api_key")
        monkeypatch.setenv("X_API_SECRET", "test_api_secret")
        monkeypatch.setenv("X_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "test_access_token_secret")

        from src.auth.x_auth import XAuth, verify_credentials

        auth = XAuth(
            api_key="test_api_key",
            api_secret="test_api_secret",
            access_token="test_access_token",
            access_token_secret="test_access_token_secret",
        )

        mock_client = MagicMock()
        mock_client.get_me.return_value = {"data": {"id": "123", "username": "testuser"}}

        with patch("src.auth.x_auth.tweepy.Client", return_value=mock_client):
            result = verify_credentials(auth)

        mock_client.get_me.assert_called_once()
        assert result == {"data": {"id": "123", "username": "testuser"}}

    def test_verify_credentials_raises_auth_error_on_401(self, monkeypatch):
        """Test that verify_credentials() raises AuthError on 401 response."""
        monkeypatch.setenv("X_API_KEY", "test_api_key")
        monkeypatch.setenv("X_API_SECRET", "test_api_secret")
        monkeypatch.setenv("X_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "test_access_token_secret")

        from src.auth.x_auth import XAuth, verify_credentials, AuthError

        auth = XAuth(
            api_key="test_api_key",
            api_secret="test_api_secret",
            access_token="test_access_token",
            access_token_secret="test_access_token_secret",
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
        monkeypatch.setenv("X_API_KEY", "test_api_key")
        monkeypatch.setenv("X_API_SECRET", "test_api_secret")
        monkeypatch.setenv("X_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "test_access_token_secret")

        from src.auth.x_auth import XAuth, verify_credentials, AuthError

        auth = XAuth(
            api_key="test_api_key",
            api_secret="test_api_secret",
            access_token="test_access_token",
            access_token_secret="test_access_token_secret",
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
