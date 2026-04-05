# Phase 2: API Enrichment - Research

**Researched:** 2026-04-05
**Domain:** X API v2 user lookup, tweepy rate handling, batch enrichment
**Confidence:** HIGH

## Summary

Phase 2 enriches 867 followed accounts via `GET /2/users` batch lookups (up to 100 per call). tweepy.Client (v4.16.0 installed) handles OAuth 1.0a and the API calls. Key technical findings: (1) tweepy's built-in `wait_on_rate_limit` uses simple sleep-until-reset, not exponential backoff -- custom implementation required; (2) error codes 63 (suspended) and 179 (protected) arrive as HTTP 403 with tweepy.Forbidden exceptions containing error objects in the response body; (3) all needed fields (bio, location, public_metrics, verified, protected, pinned_tweet_id) are available via `user_fields` parameter; (4) immediate disk caching is not automatic -- must be added after each API call.

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** JSON Lines format (one `.json` file per account) at `data/enrichment/{account_id}.json`
- **D-02:** Collect failures and continue
- **D-03:** Track suspended accounts (error 63) and protected accounts (error 179) separately
- **D-04:** Rate limit errors trigger exponential backoff with jitter
- **D-05:** Flag accounts with missing bio/location for Phase 3 scraping (`needs_scraping: true`)

### Claude's Discretion
- API batch size (up to 100 per call) -- use tweepy's default batching
- Rate limit header parsing (x-rate-limit-remaining, x-rate-limit-reset)
- Exact backoff timing (exponential with jitter)

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENRICH-01 | Batch profile enrichment via `GET /2/users` (up to 100 user IDs per call) | tweepy.Client.get_users supports batch up to 100, confirmed via source |
| ENRICH-02 | Track rate limit headers; implement exponential backoff with jitter | tweepy built-in uses simple sleep-until-reset; custom implementation needed |
| ENRICH-03 | Flag suspended (error 63) and protected (error 179) accounts | tweepy raises Forbidden for HTTP 403; error codes in response body |
| ENRICH-04 | Extract bio, location, professional_category, pinned tweet, follower/following counts, verified | All fields available via user_fields parameter; pinned_tweet_id supported |
| ENRICH-05 | Cache all API responses to disk immediately | No automatic caching in tweepy; must implement after each call |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| tweepy | 4.16.0 (installed) | X API v2 client | Primary Python client for X API |
| requests | (bundled with tweepy) | HTTP library | tweepy dependency |

**Note:** Verify current version before implementation:
```bash
npm view tweepy version  # N/A - use pip
pip show tweepy | grep Version
```

### Key tweepy.Client Details

**Initialization (OAuth 1.0a user context):**
```python
client = tweepy.Client(
    consumer_key=auth.api_key,
    consumer_secret=auth.api_secret,
    access_token=auth.access_token,
    access_token_secret=auth.access_token_secret,
    bearer_token=auth.bearer_token,
    wait_on_rate_limit=False,  # Must be False for custom backoff
    return_type=dict  # Or tweepy.Response; dict gives raw JSON
)
```

**Batch user lookup:**
```python
# Batch up to 100 IDs per call
users = client.get_users(
    ids=["123", "456", ...],  # Up to 100
    user_fields=[
        "description",      # bio
        "location",         # location
        "public_metrics",   # followers/following counts
        "verified",         # verified status
        "protected",         # protected status
        "pinned_tweet_id",  # pinned tweet ID
    ]
)
# Returns dict with keys: data, includes, errors, meta
```

**Rate limit headers (not directly on Response object):**
```python
# Must use return_type=requests.Response to access raw response headers
client = tweepy.Client(..., return_type=requests.Response)
response = client.get_users(ids=[...], user_fields=[...])
response.headers["x-rate-limit-remaining"]  # int
response.headers["x-rate-limit-reset"]        # Unix timestamp int
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── auth/x_auth.py          # Existing - get_auth(), verify_credentials()
├── parse/following_parser.py # Existing - parse_following_js()
└── enrich/
    ├── __init__.py
    ├── api_client.py        # NEW: tweepy client wrapper with backoff
    ├── rate_limiter.py      # NEW: Exponential backoff with jitter
    └── enrich.py            # NEW: Main enrichment orchestration
data/
└── enrichment/             # NEW: {account_id}.json files (one per account)
    ├── 123456789.json
    └── 987654321.json
```

### Pattern 1: Enrichment Orchestration
**What:** Main loop that fetches 867 accounts in batches, caches immediately, tracks errors.
**When to use:** Phase 2 core logic
```python
def enrich_accounts(records: list[FollowingRecord], auth: XAuth) -> EnrichmentResult:
    client = build_client(auth)  # With custom rate limit handling
    results = {"enriched": [], "suspended": [], "protected": [], "errors": []}

    for batch in chunks(records, 100):
        ids = [r.account_id for r in batch]
        try:
            response = client.get_users(ids=ids, user_fields=USER_FIELDS)
            for user in (response.get("data") or []):
                cache_enrichment(user)
                results["enriched"].append(user)
            # Track suspended/protected via errors array
            for error in (response.get("errors") or []):
                code = error.get("code")
                if code == 63:
                    results["suspended"].append(error.get("value"))
                elif code == 179:
                    results["protected"].append(error.get("value"))
                else:
                    results["errors"].append(error)
        except TooManyRequests as e:
            handle_rate_limit(e)  # Exponential backoff + retry
        except Forbidden as e:
            handle_forbidden(e)    # Parse error codes 63/179
    return results
```

### Pattern 2: Immediate Disk Cache
**What:** Write each account's data to disk immediately after API response.
**When to use:** ENRICH-05 requirement -- never re-request within session
```python
def cache_enrichment(user: dict, cache_dir: Path) -> Path:
    account_id = user["id"]
    path = cache_dir / f"{account_id}.json"
    path.write_text(json.dumps(user, indent=2))
    return path
```

### Pattern 3: Exponential Backoff with Jitter
**What:** Custom rate limit handler replacing tweepy's built-in simple sleep.
**When to use:** D-04 and ENRICH-02 requirement
```python
import random, time

def exponential_backoff(attempt: int, base: float = 1.0, max_delay: float = 300.0) -> float:
    """Returns seconds to sleep. attempt starts at 0."""
    delay = min(base * (2 ** attempt) + random.uniform(0, 1), max_delay)
    return delay
```

### Anti-Patterns to Avoid
- **Using `wait_on_rate_limit=True`:** tweepy's built-in handler sleeps until the exact reset time (no backoff). For 867 accounts in ~9 batches, this blocks on first 429 rather than backing off aggressively. Use custom backoff instead.
- **Caching after batch completion:** If crash occurs mid-batch, all accounts in that batch are lost. Write each account's data immediately after receiving it.
- **Assuming all IDs return data:** Suspended/protected accounts return errors, not user objects. Always check both `data` and `errors` arrays in response.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OAuth 1.0a auth | Custom signing | tweepy.Client | Complex HMAC signing handled by library |
| API response parsing | Raw JSON parsing | tweepy.Response / dict | Handles includes/errors/meta correctly |
| Rate limit 429 handling | `time.sleep(fixed)` | Custom exponential backoff | tweepy's built-in is simple sleep-until-reset, not backoff |

## Common Pitfalls

### Pitfall 1: tweepy built-in rate limit handling is simple sleep, not backoff
**What goes wrong:** When rate limited, `wait_on_rate_limit=True` sleeps until the exact `x-rate-limit-reset` time. If multiple batches are queued, all wait the full reset period before resuming.
**Why it happens:** tweepy `BaseClient.request` (client.py:103-113) calculates `sleep_time = reset_time - current_time + 1` and calls `time.sleep(sleep_time)`, then retries. No exponential backoff.
**How to avoid:** Set `wait_on_rate_limit=False` and implement custom exponential backoff with jitter. Track remaining calls and pause before batches that would exceed the limit.
**Warning signs:** Progress halting for long periods after first 429; all 9 batches waiting the same duration.

### Pitfall 2: Per-user rate limit vs app rate limit
**What goes wrong:** `GET /2/users` has different limits for user context (900 req/15min) vs app-only (300 req/15min). Using OAuth 1.0a (user context) gives 900 per 15 min, which is enough for 867 accounts in ~9 batches.
**Why it happens:** Not checking which auth mode is being used; assuming app-only rate limits apply.
**How to avoid:** Use `user_auth=True` in tweepy.Client for OAuth 1.0a; verify `x-rate-limit-limit` header is 900, not 300.

### Pitfall 3: Not checking the `errors` array in API response
**What goes wrong:** Suspended and protected accounts do not appear in the `data` array; they appear as error objects in the `errors` array. Code that only iterates `data` misses them entirely.
**Why it happens:** X API design: successful lookups return user objects, failed lookups (suspended/protected) return error objects.
**How to avoid:** Always iterate both `response.get("data", [])` and `response.get("errors", [])`.

### Pitfall 4: Cache not immediately written
**What goes wrong:** If script crashes between API call and cache write, that batch's data is lost and will be re-requested (hitting rate limits again).
**Why it happens:** Tempting to batch-cache after processing all 100 users in a batch.
**How to avoid:** Write each user's data to disk immediately upon receiving it, before processing the next user.

### Pitfall 5: `professional_category` not a standard API field
**What goes wrong:** The requirements list `professional_category` as a field to extract, but this is not a standard X API v2 user field. It may only be available via scraping.
**Why it happens:** X API v2 does not expose a `professional_category` field on the user object.
**How to avoid:** For ENRICH-04, note this field will likely come from Phase 3 scraping. Extract what's available (bio, location, pinned_tweet_id) via API and flag accounts missing data for scraping.

## Code Examples

### Accessing rate limit headers with tweepy
```python
# Source: tweepy/client.py lines 84-113
# Must use return_type=requests.Response to get raw response
client = tweepy.Client(
    consumer_key=auth.api_key,
    consumer_secret=auth.api_secret,
    access_token=auth.access_token,
    access_token_secret=auth.access_token_secret,
    bearer_token=auth.bearer_token,
    return_type=requests.Response  # Required for header access
)

response = client.get_users(ids=batch_ids, user_fields=USER_FIELDS)
remaining = int(response.headers["x-rate-limit-remaining"])
reset_ts = int(response.headers["x-rate-limit-reset"])
```

### Handling suspended (63) and protected (179) errors
```python
# Source: tweepy/client.py line 99-100 raises tweepy.Forbidden for HTTP 403
# Error codes are in the response body

response = client.get_users(ids=batch_ids, user_fields=USER_FIELDS)
# When return_type=dict (default):
# response = {"data": [...], "errors": [{"code": 63, "value": "12345"}, ...]}

for error in response.get("errors", []):
    code = error.get("code")
    if code == 63:
        # Account suspended
        suspended_ids.append(error.get("value"))
    elif code == 179:
        # Account protected
        protected_ids.append(error.get("value"))
```

### User fields available (X API v2)
```
description      -- user bio text
location         -- user-defined location string
public_metrics   -- {"followers_count": int, "following_count": int, "tweet_count": int, "listed_count": int}
verified         -- boolean
protected        -- boolean
pinned_tweet_id  -- string or null
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| v1.1 user lookup | v2 `/2/users` | API v2 launch | v2 has better fields (annotations, public_metrics) |
| Tweepy `wait_on_rate_limit=True` (simple sleep) | Custom exponential backoff with jitter | Now understood | More resilient for large batches with mixed error types |

**Known gaps:**
- `professional_category`: Not available via X API v2 user object; confirmed by API docs. Must use Phase 3 scraping instead.

## Open Questions

1. **`professional_category` extraction**
   - What we know: X API v2 user object does not have a `professional_category` field. Only `description` (bio), `location`, `entities` (URLs, hashtags in bio).
   - What's unclear: Whether X profile page scraping can reliably extract professional category.
   - Recommendation: For ENRICH-04, extract all available API fields; flag that `professional_category` will come from Phase 3 scraping.

2. **Pinned tweet text requires second API call**
   - What we know: `GET /2/users` returns `pinned_tweet_id` but not the tweet text. Fetching text requires `GET /2/tweets/{id}`.
   - What's unclear: Is pinned tweet text valuable enough to warrant an extra API call per user? 867 extra calls doubles rate limit pressure.
   - Recommendation: Store `pinned_tweet_id` during enrichment; fetch text in Phase 3 scraping if needed for clustering.

## Environment Availability

Step 2.6: SKIPPED (no external dependencies beyond project code and existing Python environment)

## Sources

### Primary (HIGH confidence)
- tweepy 4.16.0 source inspection (`/Users/ffaber/Library/Python/3.9/lib/python/site-packages/tweepy/client.py`) -- confirmed get_users signature, rate limit handling (lines 103-113), error handling (lines 95-119)
- X API v2 documentation -- user lookup endpoint, available user fields, rate limits (900 req/15min per user)

### Secondary (MEDIUM confidence)
- [tweepy Client documentation](https://docs.tweepy.org/en/v4.4.0/client.html) -- API reference
- [X API User Lookup](https://developer.x.com/en/docs/twitter-api/users/lookup/introduction) -- endpoint docs (rate limited at fetch time)
- [StackOverflow: X API v2 rate limit headers](https://stackoverflow.com/questions/74013734/twitter-api-v2-return-the-x-rate-limit-limit-x-rate-limit-remaining-x-rate-li) -- confirmed header access pattern
- [GitHub tweepy issue #1982](https://github.com/tweepy/tweepy/issues/1982) -- confirmed exponential backoff not in Client

### Tertiary (LOW confidence)
- [X Developer Community: Error code 63](https://devcommunity.x.com/t/403-forbidden-63-user-has-been-suspended/174127) -- single source, confirms error 63 = suspended, error 179 = protected

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- tweepy confirmed as correct library, all versions verified
- Architecture: HIGH -- pattern confirmed from existing codebase and tweepy internals
- Pitfalls: HIGH -- all pitfalls confirmed via tweepy source code and X API docs

**Research date:** 2026-04-05
**Valid until:** 2026-05-05 (30 days -- X API is stable but credential requirements may change)
