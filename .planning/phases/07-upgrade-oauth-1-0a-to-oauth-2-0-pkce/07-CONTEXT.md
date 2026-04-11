# Phase 7 Context: Upgrade OAuth 1.0a to OAuth 2.0 PKCE

**Project:** X Following Organizer
**Phase:** 7 / v1.1
**Created:** 2026-04-11

## Prior Art

- Phase 1 established OAuth 1.0a authentication via tweepy Client with `XAuth` dataclass
- `research.md` in project root documents the OAuth 2.0 PKCE architecture difference vs OAuth 1.0a
- tweepy 4.16.0 (installed, requires >=4.14.0) supports `OAuth2UserHandler` since 4.8

## Files Affected

- `src/auth/x_auth.py` — XAuth dataclass, get_auth(), verify_credentials()
- `src/enrich/api_client.py` — tweepy.Client instantiation with OAuth 1.0a credentials
- `tests/test_x_auth.py` — auth module tests

## Current State (OAuth 1.0a)

```python
# XAuth dataclass fields
api_key, api_secret, access_token, access_token_secret, bearer_token

# tweepy.Client initialization
tweepy.Client(
    consumer_key=auth.api_key,
    consumer_secret=auth.api_secret,
    access_token=auth.access_token,
    access_token_secret=auth.access_token_secret,
    bearer_token=auth.bearer_token,
)
```

## Target State (OAuth 2.0 PKCE)

```python
# XAuth dataclass fields
client_id, client_secret, access_token, refresh_token, bearer_token

# OAuth2UserHandler (initial auth only; stored tokens used afterward)
tweepy.OAuth2UserHandler(
    client_id=auth.client_id,
    redirect_uri="http://127.0.0.1:8080/callback",
    scope=["tweet.read", "users.read", "list.read", "list.write", "offline.access"]
)

# tweepy.Client with stored tokens
tweepy.Client(bearer_token=auth.access_token)
```

## Key Changes

1. **XAuth dataclass**: Replace `api_key/api_secret/access_token/access_token_secret` with `client_id/client_secret/access_token/refresh_token`
2. **get_auth()**: Load from new env vars — `X_CLIENT_ID`, `X_CLIENT_SECRET`, `X_ACCESS_TOKEN`, `X_REFRESH_TOKEN`
3. **First-run flow**: `OAuth2UserHandler` requires browser redirect + code exchange; store resulting access + refresh tokens
4. **verify_credentials()**: Update to use OAuth 2.0 Bearer token with tweepy.Client
5. **api_client.py**: Update tweepy.Client initialization to use stored access_token (Bearer)
6. **Token refresh**: Implement refresh logic before token expiry

## Scope Notes

- First-run auth flow (browser redirect) is in scope — requires callback server
- Token persistence (save/load tokens to disk) is in scope
- API call patterns (`client.get_users()`, `client.create_list()`) are unchanged
