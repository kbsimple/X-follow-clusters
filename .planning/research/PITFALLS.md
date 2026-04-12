# Pitfalls Research: Tweet Caching with Accumulation

**Domain:** Tweet caching with accumulation for enrichment pipeline
**Researched:** 2026-04-12
**Confidence:** HIGH (official docs + multiple production issues verified)

## Executive Summary

This document covers pitfalls specific to **adding tweet caching with accumulation** to an existing X API enrichment pipeline. The system already has profile caching (one JSON file per account). The new milestone adds tweet caching with accumulation across runs.

**Key risk areas:**
1. Tweet ID precision loss during JSON serialization
2. Race conditions in file-based cache writes
3. Unbounded cache growth without eviction
4. Incremental fetch semantics (since_id is exclusive)
5. Retweet/quote tweet reference handling

---

## Critical Pitfalls

### Pitfall 1: JSON Precision Loss with Tweet IDs

**What goes wrong:**
Tweet IDs are 64-bit snowflake integers. When serialized to JSON and read by JavaScript or some JSON parsers, precision is lost because JavaScript only supports 53-bit integers. The result is corrupted IDs that no longer reference the original tweet.

**Why it happens:**
Twitter/X API returns both `id` (integer) and `id_str` (string). Developers often use the integer form for convenience, not realizing that JSON serialization will corrupt the value when crossing language boundaries or when read by JavaScript tools.

**How to avoid:**
- Always use `id_str` field from Twitter API responses
- Store tweet IDs as strings in JSON files, not integers
- When reading cached JSON, treat ID fields as strings from the start
- Use Python's native `int` for in-memory operations (Python handles arbitrary precision), but convert to `str()` before JSON serialization

**Warning signs:**
- Tweet IDs ending in unexpected digits (e.g., `...123456` becomes `...123457`)
- "Tweet not found" errors when fetching by ID from cache
- Duplicate detection failures because IDs no longer match

**Phase to address:**
CACHE-01 (cache read path) — must be prevented at the serialization layer

---

### Pitfall 2: Race Condition During Cache Write

**What goes wrong:**
When writing to JSON cache files, concurrent reads or writes can corrupt the file. The sequence of `truncate()` followed by `write()` creates a window where the file is empty or partially written.

**Why it happens:**
JSON file writes are not atomic. A process reading the file during a write will see either empty content (after truncate) or partial content (during write). This causes `JSONDecodeError` crashes on subsequent reads.

**How to avoid:**
- Use atomic write pattern: write to temp file, then `os.replace()` (atomic on POSIX)
- Add `f.flush()` and `os.fsync(f.fileno())` after write to ensure data reaches disk
- Consider file locking with `fcntl.flock()` for multi-process scenarios
- Handle read failures gracefully: treat unreadable cache as "not present"

```python
import os
import json
import tempfile

def atomic_write(path, data):
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)  # Atomic on POSIX
    except:
        os.unlink(tmp_path)
        raise
```

**Warning signs:**
- `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` when reading cache
- Intermittent cache misses that should be hits
- Corrupted JSON files (partial writes, extra characters)

**Phase to address:**
CACHE-01 (cache read/write operations) — must use atomic writes from the start

---

### Pitfall 3: Unbounded Cache Growth

**What goes wrong:**
CACHE-03 specifies "no limit on stored posts — cache grows over multiple invocations." Without size limits or eviction policies, the cache directory grows indefinitely, eventually consuming all available disk space or causing performance degradation.

**Why it happens:**
Developers implement accumulation (merge new tweets with existing) without implementing cleanup. The cache grows linearly with each run. For a user following 1,000 accounts with 50 tweets each, that's 50,000 tweets. After 10 runs with new tweets, this could balloon significantly.

**How to avoid:**
- Define a maximum cache size per user (e.g., most recent 200 tweets)
- Implement deduplication by tweet ID during accumulation
- Consider pruning older tweets beyond a threshold (e.g., tweets older than 1 year)
- Monitor cache directory size in logs
- Document expected growth rate and disk requirements

**Warning signs:**
- Cache directory growing faster than expected
- Disk space alerts on the system
- Slower file I/O as JSON files grow large
- Memory pressure when loading large cache files

**Phase to address:**
CACHE-02 (accumulation logic) — must implement bounds during merge

---

### Pitfall 4: Incorrect since_id Usage for Incremental Fetch

**What goes wrong:**
When fetching only new tweets, developers misunderstand how `since_id` works. It returns tweets *newer* than the given ID, not including that ID. Also, `max_id` is *inclusive*, so naive use causes duplicate tweets at pagination boundaries.

**Why it happens:**
- `since_id` is exclusive: `since_id=123` returns tweets with ID > 123
- `max_id` is inclusive: `max_id=123` returns tweets with ID <= 123
- When paginating backward, subtracting 1 from `max_id` is needed to avoid duplicates
- When fetching new tweets, storing the *highest* ID (most recent) is critical

**How to avoid:**
- Store the most recent (highest) tweet ID after each fetch
- Use `since_id=<highest_id>` to fetch only new tweets
- For backward pagination, use `max_id=<lowest_id - 1>`
- Verify with a small test case before scaling

```python
# Correct: fetch tweets newer than our most recent
new_tweets = client.get_users_tweets(
    id=user_id,
    since_id=last_highest_id,  # exclusive, returns > this ID
    max_results=100
)

# Track the new highest ID for next time
if new_tweets:
    new_highest = max(t['id'] for t in new_tweets)
```

**Warning signs:**
- Duplicate tweets appearing in cache after multiple runs
- Missing tweets that should have been fetched
- Inconsistent tweet counts between runs

**Phase to address:**
CACHE-01 (incremental fetch logic)

---

### Pitfall 5: Retweet/Quote Tweet Reference Handling

**What goes wrong:**
When caching tweets, retweets and quote tweets reference the original tweet. If only the reference is stored without the original tweet data, the cache is incomplete. When fetching with `exclude=["retweets"]`, developers may miss that quote tweets still need expansion.

**Why it happens:**
- Retweets return a reference to the original, not full content
- Quote tweets need `expansions=referenced_tweets.id` to get full original
- The API response splits data between `data` and `includes.tweets`

**How to avoid:**
- Use `expansions=referenced_tweets.id,referenced_tweets.id.author_id` when fetching
- Store both the tweet and any referenced tweets from `includes`
- Track `retweeted_tweet_id` and `quoted_tweet_id` fields for reference
- Consider excluding retweets entirely (as current code does) to simplify

**Warning signs:**
- Quote tweets missing the quoted content
- Retweet entries with no original tweet text
- Broken references when rendering or analyzing tweets

**Phase to address:**
CACHE-01 (tweet fetch and storage)

---

## Moderate Pitfalls

### Pitfall 6: Cache Miss Results in Full Refetch

**What goes wrong:**
When a cache file doesn't exist or is unreadable, the system fetches all 50 tweets instead of incrementally fetching only new ones. This wastes API quota.

**How to avoid:**
- Distinguish between "no cache exists" (fetch all) and "cache exists but incomplete" (fetch incrementally)
- Store metadata about last fetch time and highest ID
- If cache is corrupted, log a warning but still fetch incrementally if possible

---

### Pitfall 7: Duplicate Tweets in Accumulation

**What goes wrong:**
When merging new tweets with cached tweets, naive `extend()` adds duplicates if the same tweet appears in both sets. This happens when a previous fetch was interrupted and resumed.

**How to avoid:**
- Deduplicate by tweet ID during merge: `all_tweets = {t['id']: t for t in existing + new}.values()`
- Store tweets in a dict keyed by ID, not a list
- Verify no duplicates after merge with assertion

```python
def accumulate_tweets(existing: list, new: list) -> list:
    """Merge tweets, deduplicating by ID."""
    by_id = {t['id']: t for t in existing}
    by_id.update({t['id']: t for t in new})
    return list(by_id.values())
```

---

### Pitfall 8: Missing Rate Limit Header Handling

**What goes wrong:**
The system fetches tweets without checking rate limit headers, potentially hitting 429 errors. The user timeline endpoint has 10,000 requests/15min at app-level.

**How to avoid:**
- Parse `x-rate-limit-remaining` from each response
- Implement soft threshold: if remaining < 10%, slow down
- Track remaining quota across all operations, not just tweets

---

### Pitfall 9: Suspended/Protected Accounts Breaking Tweet Fetch

**What goes wrong:**
When fetching tweets for suspended (error 63) or protected (error 179) accounts, the API returns errors. If unhandled, these break the entire enrichment batch.

**Why it happens:**
- X API returns error code 63 ("User has been suspended") or 179 ("Protected tweets")
- These accounts may have been valid when cached profile data was saved
- The existing enrichment code already handles these at profile level

**How to avoid:**
- Reuse existing suspended/protected detection from profile enrichment
- Skip tweet fetch for accounts already flagged as suspended/protected
- Log skipped accounts with reason code
- Return empty tweet list for these accounts (not an error)

**Warning signs:**
- Batch enrichment failing on single account
- 403 errors when fetching tweets for known accounts
- Cache not being written for accounts after tweet fetch failure

**Phase to address:**
CACHE-01 (integration with existing enrichment)

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| X API tweets endpoint | Using `max_results=5` (minimum) instead of `100` (efficient) | Use 100 per call to minimize rate limit hits |
| X API pagination | Ignoring `next_token` field | Loop until `next_token` is None |
| X API error handling | Retrying 401/403/404 errors | These are permanent failures; don't retry |
| JSON serialization | Using default `json.dump(int_id)` | Convert IDs to strings first |
| File locking | Assuming Python's GIL prevents races | Use OS-level file locks for multi-process |
| Existing cache pattern | Writing to same directory as profiles | Consider separate `data/tweets/` directory |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Large JSON files | Slow reads/writes, memory pressure | Split by user, cap per-user tweet count | >10,000 tweets per user |
| No pagination limit | API timeouts, rate limit exhaustion | Fetch in batches, respect rate limits | >500 accounts per run |
| Inline processing | Buffer overflow, dropped tweets | Separate fetch thread from processing thread | High-volume streaming |
| Full refetch on error | Wasted API quota | Cache partial results, resume from last success | Network instability |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing OAuth tokens in cache files | Credential exposure | Never cache auth data; use separate secure storage |
| No input validation on cache path | Path traversal vulnerability | Validate user IDs are numeric strings |
| Logging tweet contents | Privacy exposure in logs | Log IDs only, not full tweet text |

---

## "Looks Done But Isn't" Checklist

- [ ] **Tweet cache read path:** Often missing error handling for corrupted JSON — verify JSONDecodeError is caught and treated as cache miss
- [ ] **Tweet accumulation:** Often missing deduplication — verify no duplicate IDs after merge
- [ ] **Incremental fetch:** Often using wrong since_id semantics — verify `since_id` is exclusive
- [ ] **Cache write atomicity:** Often using plain write instead of atomic replace — verify `os.replace()` pattern
- [ ] **Rate limit tracking:** Often checking only after error instead of proactively — verify soft threshold monitoring
- [ ] **ID precision:** Often storing IDs as integers — verify IDs are strings in JSON

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| JSON precision loss | HIGH | Re-fetch all tweets; existing cache unusable |
| Unbounded growth | MEDIUM | Implement pruning; truncate cache to size limit |
| Race condition corruption | LOW | Delete corrupted file, re-fetch |
| Duplicate tweets | LOW | Run deduplication pass on existing cache |
| Missing rate limit handling | MEDIUM | Add backoff; existing data intact |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| JSON precision loss | CACHE-01 | Unit test: write/read tweet with >53-bit ID |
| Race condition | CACHE-01 | Unit test: concurrent read/write |
| Unbounded growth | CACHE-02 | Integration test: run 10x, verify cache size bounded |
| since_id usage | CACHE-01 | Unit test: verify no duplicates after incremental fetch |
| Retweet handling | CACHE-01 | Integration test: fetch account with quote tweets |
| Duplicate accumulation | CACHE-02 | Unit test: merge overlapping tweet sets |
| Rate limit headers | CACHE-01 | Integration test: verify headers parsed, backoff triggered |
| Suspended/protected skip | CACHE-01 | Unit test: skip accounts flagged in profile cache |

---

## Sources

### Official Documentation (HIGH confidence)
- [Twitter Developer Docs — Working with Timelines](https://developer.x.com/en/docs/x-api/v1/tweets/timelines/guides/working-with-timelines) — Official docs on since_id/max_id semantics
- [Twitter Developer Docs — Twitter IDs](https://developer.x.com/en/docs/twitter-ids) — Official docs on 64-bit ID handling
- [Twitter API Rate Limits 2026 — Sorsa Blog](https://api.sorsa.io/blog/twitter-api-rate-limits-2026) — Current rate limit reference

### Verified Production Bugs (HIGH confidence)
- [botocore JSONFileCache Race Condition — GitHub Issue #3213](https://github.com/boto/botocore/issues/3213) — Race condition in JSON cache writes
- [python-diskcache Concurrent Read/Write — GitHub Issue #294](https://github.com/grantjenks/python-diskcache/issues/294) — EOF errors during concurrent access
- [InMemoryCache Unbounded Growth — LiteLLM PR #14869](https://github.com/BerriAI/litellm/pull/14869) — Memory leak with TTL but no size limit

### Developer Experience (MEDIUM confidence)
- [Fetching X Timelines with Pay-Per-Use — Dev.to](https://dev.to/ikka/fetching-x-timelines-with-api-v2-pay-per-use-cost-breakdown-caching-and-the-gotchas-1i2o) — Practical caching patterns
- [API Cost Optimization for Social Media Data — SociaVault](https://sociavault.com/blog/api-cost-optimization-social-media-data) — Industry analysis on caching ROI
- [Twitter/X Feed System Design — Intervu.dev](https://intervu.dev/blog/twitter-feed-system-design/) — Timeline architecture patterns

### Reference (HIGH confidence)
- [Snowflake ID — Wikipedia](https://en.wikipedia.org/wiki/Snowflake_ID) — Well-documented ID format

---
*Pitfalls research for: Tweet caching with accumulation*
*Researched: 2026-04-12*