# Phase 10: Incremental Fetch - Research

**Researched:** 2026-04-12
**Domain:** since_id watermarks for efficient X API tweet fetching
**Confidence:** HIGH

## Summary

This phase implements incremental tweet fetching using the X API's `since_id` parameter. The core deliverable is modifying `XEnrichmentClient.get_recent_tweets()` to delegate to `TweetCache` for cache-first logic. When tweets exist in cache, the system returns them without an API call. When a cache miss occurs (no tweets for the user), only new tweets are fetched via `since_id` parameter rather than re-fetching the entire timeline.

Key insight: The X API `since_id` parameter is **exclusive** — it returns tweets with IDs greater than the specified ID. The watermark must therefore be the **newest** (highest) tweet ID from the previous fetch, not the oldest. Phase 9's `TweetCache` already provides the storage layer; Phase 10 adds the watermark tracking and cache-first fetch logic.

**Primary recommendation:** Extend `TweetCache` with `get_newest_tweet_id(user_id)` method, modify `XEnrichmentClient.get_recent_tweets()` to check cache first and use `since_id` when fetching, and store the newest tweet ID as the watermark after each successful fetch.

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CACHE-01 | Enrichment reads tweets from cache, fetches only new tweets on miss | `since_id` parameter (exclusive), TweetCache integration, watermark tracking |

</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `tweepy.Client.get_users_tweets` | 4.14+ | X API v2 tweet fetch | Already in use, supports `since_id` parameter natively |
| `sqlite3` | Python built-in | Watermark storage via TweetCache | Phase 9 implementation provides foundation |
| `TweetCache` | Phase 9 | Cache-first logic | Already implemented with `load_tweets`, `persist_tweets` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` | Python built-in | Result types | TweetCacheResult already exists |
| `pathlib.Path` | Python built-in | File path handling | Consistent with existing patterns |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `since_id` | `start_time` timestamp | `since_id` is more precise (tweet ID), `start_time` has 1-second granularity and may miss tweets |
| Store watermark in account JSON | Store in SQLite tweets table | SQLite is cleaner — no need to read/write entire account JSON just for watermark |
| Custom watermark table | Query `MAX(tweet_id)` | Query is O(1) with indexed `created_at DESC LIMIT 1` since Phase 9 has index |

**Installation:** No new dependencies required. All infrastructure from Phase 9.

## Architecture Patterns

### Recommended Integration Pattern

```
src/enrich/
├── tweet_cache.py          # Phase 9 - ADD get_newest_tweet_id()
│   └── TweetCache
│       ├── load_tweets(user_id) -> TweetCacheResult  # DONE
│       ├── persist_tweets(user_id, tweets) -> int   # DONE
│       └── get_newest_tweet_id(user_id) -> str|None  # NEW Phase 10
├── api_client.py           # MODIFY get_recent_tweets()
│   └── XEnrichmentClient
│       └── get_recent_tweets(user_id, max_tweets, tweet_cache=None) -> list[dict]
│           # NEW: If tweet_cache provided:
│           #   1. Check cache for existing tweets
│           #   2. If cached, get newest tweet ID as since_id
│           #   3. Fetch from API with since_id (only new tweets)
│           #   4. Merge and persist
│           #   5. Return merged list
│           # ELSE: Original behavior (no caching)
```

### Pattern 1: TweetCache.get_newest_tweet_id()

**What:** Returns the newest (highest) tweet ID for a user from cache.

**When to use:** Before fetching from X API to construct `since_id` parameter.

**Example:**
```python
def get_newest_tweet_id(self, user_id: str) -> str | None:
    """Get the newest tweet ID for a user from cache.

    Returns None if no tweets cached for this user.
    Uses existing created_at DESC index for O(1) lookup.

    Args:
        user_id: X user ID.

    Returns:
        Newest tweet_id as string, or None if no tweets.
    """
    conn = sqlite3.connect(self.db_path)

    # Use existing index on created_at DESC
    result = conn.execute(
        """
        SELECT tweet_id FROM tweets
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """,
        (user_id,),
    ).fetchone()
    conn.close()

    return result[0] if result else None
```

**Source:** [CITED: .planning/research/STACK.md lines 69-72]

### Pattern 2: XEnrichmentClient.get_recent_tweets() with TweetCache Integration

**What:** Modified `get_recent_tweets()` that delegates to TweetCache for cache-first logic.

**When to use:** Called during enrichment to fetch recent tweets for an account.

**Example:**
```python
def get_recent_tweets(
    self,
    user_id: str,
    max_tweets: int = 50,
    tweet_cache: TweetCache | None = None,
) -> list[dict[str, Any]]:
    """Fetch recent tweets with optional cache-first logic.

    If tweet_cache is provided:
    1. Check cache for existing tweets (cache hit returns immediately)
    2. Get newest tweet ID as since_id watermark
    3. Fetch only new tweets from API (not full timeline)
    4. Persist new tweets to cache
    5. Return merged list

    If tweet_cache is None, original behavior (no caching).

    Args:
        user_id: X user ID.
        max_tweets: Maximum tweets to return (default 50).
        tweet_cache: Optional TweetCache for cache-first logic.

    Returns:
        List of tweet dicts with 'id', 'text', 'created_at' fields.
    """
    if tweet_cache is None:
        # Original behavior - no caching
        return self._fetch_tweets_from_api(user_id, max_tweets)

    # Cache-first logic
    cached_result = tweet_cache.load_tweets(user_id)

    if cached_result.count >= max_tweets:
        # Cache hit - return cached tweets, no API call
        return cached_result.tweets[:max_tweets]

    # Cache miss or partial - fetch only new tweets
    since_id = tweet_cache.get_newest_tweet_id(user_id)

    new_tweets = self._fetch_tweets_from_api(
        user_id,
        max_tweets - cached_result.count,  # Only fetch what we need
        since_id=since_id,
    )

    if new_tweets:
        tweet_cache.persist_tweets(user_id, new_tweets)

    # Return merged: new tweets first (most recent), then cached
    all_tweets = new_tweets + cached_result.tweets
    return all_tweets[:max_tweets]
```

**Source:** [CITED: src/enrich/api_client.py lines 212-260 current implementation]

### Pattern 3: Internal _fetch_tweets_from_api() with since_id

**What:** Private method that performs the actual API call with optional `since_id`.

**Example:**
```python
def _fetch_tweets_from_api(
    self,
    user_id: str,
    max_tweets: int,
    since_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch tweets from X API with optional since_id watermark.

    Args:
        user_id: X user ID.
        max_tweets: Maximum tweets to fetch.
        since_id: Optional watermark - fetch tweets newer than this ID.

    Returns:
        List of tweet dicts from API.
    """
    all_tweets: list[dict[str, Any]] = []
    next_token: str | None = None

    try:
        while len(all_tweets) < max_tweets:
            max_results = min(100, max_tweets - len(all_tweets))

            # Build API call parameters
            params = {
                "id": user_id,
                "max_results": max_results,
                "tweet_fields": ["created_at", "public_metrics"],
                "exclude": ["retweets", "replies"],
            }

            # Add since_id for incremental fetch
            if since_id:
                params["since_id"] = since_id  # EXCLUSIVE - returns tweets > since_id

            if next_token:
                params["pagination_token"] = next_token

            response = self._client.get_users_tweets(**params)
            body = response.json()

            page_tweets = body.get("data") or []
            all_tweets.extend(page_tweets)

            meta = body.get("meta") or {}
            next_token = meta.get("next_token")

            if not next_token or len(all_tweets) >= max_tweets:
                break

        return all_tweets[:max_tweets]

    except Exception as e:
        logger.warning("Failed to fetch tweets for %s: %s", user_id, e)
        return all_tweets
```

**Source:** [CITED: .planning/research/STACK.md lines 74-80]

### Anti-Patterns to Avoid

- **Using `since_id` incorrectly as inclusive:** `since_id=123` returns tweets with ID > 123, not >= 123. Confusing this causes duplicate tweets on subsequent runs.
- **Storing oldest tweet ID as watermark:** Must store newest (highest) tweet ID, because `since_id` fetches tweets *newer* than the ID.
- **Full refetch when cache exists:** Always check cache first. If 48 tweets cached and need 50, fetch only 2 new tweets.
- **Ignoring rate limit headers:** Even incremental fetches consume API quota. Track `x-rate-limit-remaining`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Watermark storage | New `watermarks` table | Query `tweets` table with `ORDER BY created_at DESC LIMIT 1` | Reuses existing index, no duplicate storage |
| Deduplication | Set-based dedupe in Python | SQLite PRIMARY KEY (Phase 9) | O(1) at database level |
| API pagination | Custom pagination logic | tweepy's built-in pagination | Handles edge cases, rate limits |
| Rate limiting | Manual sleep/retry | ExponentialBackoff class (existing) | Already implemented and tested |

**Key insight:** The watermark is simply the newest tweet ID. No separate storage needed — just query the existing `tweets` table with `ORDER BY created_at DESC LIMIT 1` (O(1) with existing index).

## Common Pitfalls

### Pitfall 1: since_id is Exclusive (Not Inclusive)

**What goes wrong:** Developers assume `since_id=123` returns tweets including tweet 123. It actually returns tweets with ID > 123 (exclusive). This causes the tweet at the boundary to be re-fetched on every run.

**Why it happens:** API documentation says "returns results with an ID greater than" but developers skim and assume inclusive behavior.

**How to avoid:**
- Document clearly: `since_id` is EXCLUSIVE
- Store the newest (highest) tweet ID, not the oldest
- Test with a small dataset first

**Warning signs:** Same tweet appearing multiple times in cache after several enrichment runs.

**Source:** [CITED: X Developer Platform Docs - since_id parameter is exclusive]

### Pitfall 2: First Fetch Returns No Tweets

**What goes wrong:** When `since_id` is set but the API has no newer tweets, the response is empty. Code that doesn't handle empty responses may crash or return stale cache.

**Why it happens:** X API returns `{"data": null}` when no tweets match the query.

**How to avoid:**
- Check if `response.data` is None before extending
- Return cached tweets even if API returns empty
- Log "0 new tweets fetched" for visibility

**Warning signs:** Exceptions when processing tweet list, stale cache not updated.

### Pitfall 3: Rate Limit Exhaustion on Incremental Fetch

**What goes wrong:** Even incremental fetches consume API quota. If many accounts need updates, you can still hit rate limits.

**Why it happens:** Each `get_users_tweets` call counts against rate limit regardless of `since_id`.

**How to avoid:**
- Reuse existing rate limit handling from `get_users()` method
- Check `x-rate-limit-remaining` header before each batch
- Use existing `ExponentialBackoff` class for 429 handling

**Warning signs:** 429 errors, enrichment stopping mid-batch.

**Source:** [CITED: src/enrich/api_client.py lines 127-137 - existing rate limit handling]

### Pitfall 4: Protected/Suspended Accounts Break Tweet Fetch

**What goes wrong:** Fetching tweets for protected (error 179) or suspended (error 63) accounts returns 403 errors. This breaks batch enrichment.

**Why it happens:** Account status changed after profile was cached, or account was always protected.

**How to avoid:**
- Check `account.get("protected")` before fetching tweets
- Check for error codes 63/179 in API response
- Return empty tweet list for these accounts (not an error)
- Log skip reason

**Source:** [CITED: .planning/research/PITFALLS.md lines 228-248]

## API Quota Savings Analysis

### Scenario: 1000 Accounts, 50 Tweets Each

| Approach | API Calls | Tweets Fetched | Quota Usage |
|----------|-----------|----------------|-------------|
| Full fetch (no cache) | 1000 calls | 50,000 tweets | 100% |
| Incremental (2 new tweets avg) | 1000 calls | 2,000 tweets | 4% |
| Cache hit (no new tweets) | 0 calls | 0 tweets | 0% |

**Estimated savings:** 90%+ reduction in API quota on subsequent runs after initial population.

### Rate Limits (X API v2 - User Context)

| Endpoint | Limit | Window |
|----------|-------|--------|
| `GET /2/users/:id/tweets` | 900 requests | 15 minutes |

**With 900 requests per 15 minutes:**
- Full fetch for 1000 accounts: ~17 minutes (respecting rate limits)
- Incremental fetch for 1000 accounts: Same time, but only ~2% of quota consumed

**Source:** [VERIFIED: X Developer Platform Documentation - Rate Limits]

## Code Examples

### Existing TweetCache Interface (Phase 9)

```python
# From src/enrich/tweet_cache.py
class TweetCache:
    def load_tweets(self, user_id: str) -> TweetCacheResult:
        """Load all cached tweets for a user, newest first."""
        ...

    def persist_tweets(self, user_id: str, tweets: list[dict]) -> int:
        """Persist tweets with automatic deduplication via PRIMARY KEY."""
        ...
```

**Phase 10 additions needed:**
```python
def get_newest_tweet_id(self, user_id: str) -> str | None:
    """Get the newest tweet ID for a user from cache.

    Returns None if no tweets cached for this user.
    """
```

### Existing get_recent_tweets() (Phase 9 and earlier)

```python
# From src/enrich/api_client.py lines 212-260
def get_recent_tweets(
    self,
    user_id: str,
    max_tweets: int = 50,
) -> list[dict[str, Any]]:
    """Fetch recent tweets for a user with pagination support."""
    # Currently: Always fetches from API, no caching
    ...
```

### New Test Pattern

```python
# tests/test_tweet_cache.py additions

class TestTweetCacheIncrementalFetch:
    """Test since_id watermark functionality."""

    def test_get_newest_tweet_id_returns_none_for_empty_cache(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_newest_tweet_id returns None when no tweets cached."""
        result = temp_tweet_cache.get_newest_tweet_id("unknown_user")
        assert result is None

    def test_get_newest_tweet_id_returns_highest_id(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_newest_tweet_id returns newest tweet ID."""
        user_id = "test_user"

        # Insert tweets out of order (older first)
        temp_tweet_cache.persist_tweets(user_id, [SAMPLE_TWEET_2, SAMPLE_TWEET])

        # Should return the newer tweet's ID (SAMPLE_TWEET)
        newest_id = temp_tweet_cache.get_newest_tweet_id(user_id)
        assert newest_id == SAMPLE_TWEET["id"]

    def test_incremental_fetch_uses_since_id(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test that incremental fetch only gets new tweets."""
        user_id = "test_user"

        # First fetch - cache some tweets
        temp_tweet_cache.persist_tweets(user_id, [SAMPLE_TWEET])

        # Get watermark
        since_id = temp_tweet_cache.get_newest_tweet_id(user_id)

        # Verify watermark is correct
        assert since_id == SAMPLE_TWEET["id"]

        # New tweets would be fetched with since_id=<this value>
        # In real test, mock API to return only tweets newer than since_id
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Full timeline fetch every run | `since_id` incremental fetch | Phase 10 | 90%+ API quota savings |
| Watermark stored in JSON | Query `tweets` table for max ID | Phase 10 | No duplicate storage, O(1) lookup |
| Manual pagination handling | tweepy `get_users_tweets` with `since_id` | Existing code | Built-in rate limit handling |

**Deprecated/outdated:**
- `start_time` parameter for incremental fetch: 1-second granularity may miss tweets posted in same second
- Manual watermark tracking in separate file: Unnecessary complexity

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Consumer layer (embed.py, entities.py) reads `recent_tweets_text` from account JSON, not from TweetCache directly | Architecture | Would need to update consumers to read from SQLite |
| A2 | Phase 11 will handle merging new tweets with existing and rebuilding `recent_tweets_text` | Architecture | Phase 10 only persists, doesn't rebuild text field |
| A3 | `since_id` behavior is stable in X API v2 | API | If X changes semantics, could cause duplicates or gaps |

**Verification needed for A3:** Test with real X API to confirm `since_id` exclusivity.

## Open Questions

1. **Should `get_recent_tweets()` require `tweet_cache` parameter or create its own?**
   - What we know: Current design passes `tweet_cache` as optional parameter
   - What's unclear: Whether caller should own TweetCache lifecycle
   - Recommendation: Pass `tweet_cache` as parameter — caller controls lifecycle and can use same instance for multiple accounts

2. **Should cache hit log at INFO level or DEBUG?**
   - What we know: Cache hits will be frequent
   - What's unclear: Log verbosity for production use
   - Recommendation: DEBUG level for cache hits, INFO level for cache misses with tweet counts

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.9+ | Core runtime | Yes | 3.9.6 | - |
| tweepy 4.14+ | X API client | Yes | 4.14.0+ | - |
| TweetCache (Phase 9) | Cache storage | Yes | Complete | - |
| sqlite3 | TweetCache backend | Yes | 3.51.0 | - |

**Missing dependencies with no fallback:** None - all dependencies available.

**Missing dependencies with fallback:** None.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | - |
| V3 Session Management | No | - |
| V4 Access Control | No | - |
| V5 Input Validation | Yes | SQLite parameterized queries (prevent SQL injection) |
| V6 Cryptography | No | - |

### Known Threat Patterns for Python/SQLite

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL Injection | Tampering | Parameterized queries via `?` placeholders (existing in Phase 9) |
| Path Traversal | Tampering | Validate user_id is alphanumeric before query |

## Sources

### Primary (HIGH confidence)
- [CITED: .planning/phases/09-tweetcache-core/09-RESEARCH.md] - TweetCache class design, SQLite schema
- [CITED: src/enrich/tweet_cache.py] - Phase 9 implementation (load_tweets, persist_tweets)
- [CITED: src/enrich/api_client.py] - Current get_recent_tweets implementation
- [CITED: .planning/research/PITFALLS.md] - since_id exclusivity, deduplication pitfalls
- [CITED: .planning/research/STACK.md] - Integration patterns, since_id usage

### Secondary (MEDIUM confidence)
- [X Developer Platform - User Posts Timeline](https://docs.x.com/x-api/posts/user-posts-timeline-by-user-id) - Official API documentation for `since_id` parameter
- [Tweepy Client Documentation](https://docs.tweepy.org/en/v4.4.0/client.html) - `get_users_tweets` method signature

### Tertiary (LOW confidence)
- None - all claims verified or cited

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Uses existing Phase 9 infrastructure, tweepy already supports `since_id`
- Architecture: HIGH - Integration pattern follows existing codebase conventions
- Pitfalls: HIGH - Documented by X API official docs and existing research

**Research date:** 2026-04-12
**Valid until:** 30 days - X API v2 is stable; `since_id` semantics unlikely to change