# Phase 07 Plan 02: OAuth 2.0 PKCE First-Run Auth Flow Summary

## Plan Overview

| Field | Value |
|-------|-------|
| **Plan** | 07-02 |
| **Phase** | 07-upgrade-oauth-1-0a-to-oauth-2-0-pkce |
| **Type** | upgrade |
| **Status** | complete |
| **Requirements** | OAUTH2-03 |
| **Committed** | 1126f4c |

## One-Liner

OAuth 2.0 PKCE first-run browser auth flow with callback server, code exchange, and token persistence to data/tokens.json.

## Objectives

Implement the first-run OAuth 2.0 PKCE browser authorization flow: authorization URL generation, callback server, code exchange, and token persistence. Tokens are saved to data/tokens.json and reloaded on subsequent runs.

## Tasks Completed

| # | Task | Name | Commit | Verification |
|---|------|------|--------|--------------|
| 1 | Task 1 | Add OAuth 2.0 PKCE helper functions | 1126f4c | `python3 -c "from src.auth.x_auth import get_authorization_url, exchange_code_for_token, save_tokens, load_tokens; print('import OK')"` |
| 2 | Task 2 | Implement callback server for code capture | 1126f4c | `python3 -c "from src.auth.x_auth import wait_for_callback; print('wait_for_callback exists')"` |
| 3 | Task 3 | Add ensure_authenticated() orchestrator | 1126f4c | `python3 -c "from src.auth.x_auth import ensure_authenticated; print('ensure_authenticated exists')"` |

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Use module-level `_oauth2_handler` to store OAuth2UserHandler between get_authorization_url and exchange_code_for_token | tweepy.OAuth2UserHandler requires the same handler instance for both URL generation and token exchange |
| Threading-based HTTPServer for callback capture | Non-blocking server that can run in the foreground while user authorizes in browser |
| Return None from load_tokens when file missing | Allows ensure_authenticated to distinguish "no tokens yet" from "tokens exist" |

## Files Created / Modified

| File | Changes |
|------|---------|
| src/auth/x_auth.py | +197 lines: added get_authorization_url, exchange_code_for_token, save_tokens, load_tokens, wait_for_callback, ensure_authenticated; added required imports |

## Functions Added

| Function | Signature | Purpose |
|----------|-----------|---------|
| get_authorization_url | `(client_id: str, client_secret: str) -> str` | Creates OAuth2UserHandler, returns authorization URL |
| exchange_code_for_token | `(code: str) -> tuple[str, str]` | Exchanges auth code for access + refresh tokens |
| save_tokens | `(access_token: str, refresh_token: str, path: str \| Path = "data/tokens.json") -> None` | Persists tokens to JSON |
| load_tokens | `(path: str \| Path = "data/tokens.json") -> tuple[str, str] \| None` | Loads tokens from JSON; None if missing |
| wait_for_callback | `(port: int = 8080, timeout: int = 300) -> str` | HTTP server captures ?code= from X redirect |
| ensure_authenticated | `() -> XAuth` | Orchestrates full flow: load or interactive auth |

## Must-Have Truths Verified

| Truth | Status |
|-------|--------|
| get_authorization_url() returns X authorization URL with PKCE challenge | Implemented via tweepy.OAuth2UserHandler.get_authorization_url() |
| Callback server captures authorization code from X redirect | wait_for_callback() uses HTTPServer + threading.Event |
| exchange_code_for_token() exchanges code for access_token + refresh_token | Uses handler.fetch_token() and handler.refresh_token |
| save_tokens() persists tokens to data/tokens.json | Writes JSON with access_token and refresh_token keys |
| load_tokens() reloads tokens from data/tokens.json | Reads JSON; returns None on FileNotFoundError |
| First-run auth flow skips browser step if tokens already exist | ensure_authenticated() checks load_tokens() first |

## Deviations from Plan

None - plan executed exactly as written.

## Verification Commands

```bash
# Import check
python3 -c "from src.auth.x_auth import get_authorization_url, exchange_code_for_token, save_tokens, load_tokens, wait_for_callback, ensure_authenticated; print('import OK')"

# Token save/load roundtrip
python3 -c "
from src.auth.x_auth import save_tokens, load_tokens
import tempfile, os
tmp = tempfile.mktemp(suffix='.json')
save_tokens('at', 'rt', tmp)
assert load_tokens(tmp) == ('at', 'rt')
assert load_tokens('/nonexistent.json') is None
print('All token persistence checks passed')
"
```

## Self-Check

**PASSED**

- src/auth/x_auth.py: FOUND (modified with +197 lines)
- Commit 1126f4c: FOUND
- All 6 functions exist and are importable
- Token save/load roundtrip works correctly
- load_tokens returns None for missing files
