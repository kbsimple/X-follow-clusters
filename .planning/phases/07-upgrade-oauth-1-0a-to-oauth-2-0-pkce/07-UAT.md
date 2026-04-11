---
status: testing
phase: 07-upgrade-oauth-1-0a-to-oauth-2-0-pkce
source: 07-01-SUMMARY.md, 07-02-SUMMARY.md, 07-03-SUMMARY.md, 07-04-SUMMARY.md, 07-05-SUMMARY.md, 07-06-SUMMARY.md
started: 2026-04-11T18:30:00Z
updated: 2026-04-11T18:30:00Z
---

## Current Test

number: 1
name: XAuth dataclass has OAuth 2.0 field names
expected: |
  `from src.auth.x_auth import XAuth; XAuth(client_id='x', client_secret='y', access_token='z', refresh_token='r')`
  succeeds without error
awaiting: user response

## Tests

### 1. XAuth dataclass has OAuth 2.0 field names
expected: XAuth can be instantiated with client_id, client_secret, access_token, refresh_token (no api_key/api_secret/access_token_secret)
result: pending

### 2. get_auth() reads OAuth 2.0 env vars
expected: With X_CLIENT_ID, X_CLIENT_SECRET, X_ACCESS_TOKEN, X_REFRESH_TOKEN set, get_auth() returns XAuth with correct values
result: pending

### 3. get_auth() raises AuthError on missing client_id
expected: With X_CLIENT_SECRET, X_ACCESS_TOKEN, X_REFRESH_TOKEN set but X_CLIENT_ID missing, AuthError is raised mentioning X_CLIENT_ID
result: pending

### 4. OAuth2UserHandler get_authorization_url() exists
expected: `from src.auth.x_auth import get_authorization_url; url = get_authorization_url()` returns a string starting with https://x.com/i/oauth2/authorize
result: pending

### 5. save_tokens() and load_tokens() roundtrip
expected: save_tokens() writes data/tokens.json, load_tokens() reads it back with identical values
result: pending

### 6. verify_credentials() uses Bearer token only
expected: tweepy.Client called with bearer_token=auth.access_token only (no consumer_key/secret/access_token params)
result: pending

### 7. api_client XEnrichmentClient uses Bearer token only
expected: tweepy.Client initialized with bearer_token=auth.access_token only
result: pending

### 8. All 13 tests pass
expected: `python3 -m pytest tests/test_x_auth.py -q` shows 13 passed
result: pending

## Summary

total: 8
passed: 0
issues: 0
pending: 8
skipped: 0
blocked: 0

## Gaps

<!-- Populated when issues are found -->

