# Phase 11: Accumulation & Integration - Research

**Researched:** 2026-04-12
**Domain:** Tweet accumulation, JSON update integration, embedding rebuild
**Confidence:** HIGH

## Summary

Phase 11 completes the caching pipeline by integrating tweet accumulation with the enrichment workflow. The core infrastructure from Phase 9 (TweetCache) and Phase 10 (Incremental Fetch) is already complete. Phase 11 focuses on:

1. **Integration glue**: Connecting `get_recent_tweets(tweet_cache=...)` to account JSON updates
2. **Embedding rebuild**: Triggering tweet embedding after accumulation
3. **End-to-end validation**: Integration tests for first fetch vs subsequent scenarios

**Primary recommendation:** Modify `test_enrich.py` to pass `TweetCache` instance to `get_recent_tweets()`, then update account JSON with merged `recent_tweets_text`. Embedding rebuild uses existing `store_tweet_embedding()` function.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Update account JSON on enrichment:** After `get_recent_tweets`, write merged tweets to account JSON as `recent_tweets_text` field
- **Error handling:** Log and continue on embedding failure
- **Test scope:** Core first vs subsequent fetch tests

### Claude's Discretion
(None specified)

### Deferred Ideas (OUT OF SCOPE)
(None specified)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CACHE-02 | Tweets cached with accumulation across runs (dedupe by ID) | Phase 9: `INSERT OR IGNORE` provides atomic O(1) deduplication |
| CACHE-03 | No limit on stored posts - cache grows over multiple invocations | SQLite schema has no max_rows limit; accumulation is unbounded |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlite3 | built-in | Tweet caching database | Python standard library, Phase 9 established |
| json | built-in | Account JSON read/write | Python standard library |
| sentence-transformers | installed | Tweet embeddings | Phase 8 established for topical clustering |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|------------|
| logging | built-in | Error logging | Embedding rebuild failures |

### Alternatives Considered
None - using existing infrastructure from Phase 9/10.

**Installation:**
No new dependencies required.

## Architecture Patterns

### Current Flow (Phase 10)
```
XEnrichmentClient.get_recent_tweets(user_id, tweet_cache=cache)
    ↓
1. load_tweets(user_id) → cached_result
2. if cached_result.count >= max_tweets: return cached
3. get_newest_tweet_id(user_id) → since_id
4. _fetch_tweets_from_api(user_id, remaining, since_id) → new_tweets
5. persist_tweets(user_id, new_tweets) → inserted count
6. return new_tweets + cached_result.tweets (merged)
```

### Integration Point (test_enrich.py Step 9)
```python
# Current implementation (lines 256-296):
tweets = client.get_recent_tweets(account_id, max_tweets=50)
# ↓ Manual update of account JSON
cache_path = cache_dir / f"{account_id}.json"
account = json.load(cache_path)
account["recent_tweets"] = tweets
account["recent_tweets_text"] = " ".join(t.get("text", "") for t in tweets)
json.dump(account, cache_path)
# ↓ Embedding rebuild
store_tweet_embedding(account_id, cache_dir=cache_dir)
```

### Recommended Pattern for Phase 11

**Pattern: Tweet Accumulation with Account JSON Update**
```python
# After get_recent_tweets returns merged tweets
from src.enrich.tweet_cache import TweetCache
from src.cluster.embed import store_tweet_embedding

tweet_cache = TweetCache()  # data/tweets.db
tweets = client.get_recent_tweets(
    user_id,
    max_tweets=50,
    tweet_cache=tweet_cache  # Enable cache-first logic
)

# Update account JSON with merged tweet text
cache_path = cache_dir / f"{account_id}.json"
with open(cache_path, encoding="utf-8") as f:
    account = json.load(f)

account["recent_tweets"] = tweets
account["recent_tweets_text"] = " ".join(t.get("text", "") for t in tweets)

with open(cache_path, "w", encoding="utf-8") as f:
    json.dump(account, f, indent=2)

# Rebuild tweet embedding (with error handling per CONTEXT.md)
try:
    embedding = store_tweet_embedding(account_id, cache_dir=cache_dir)
except Exception as e:
    logger.warning("Embedding rebuild failed for %s: %s", account_id, e)
    # Continue to next account (log and continue per CONTEXT.md)
```

### Anti-Patterns to Avoid
- **Rollback account JSON on embedding failure**: CONTEXT.md explicitly says "Do NOT rollback account JSON update"
- **Fetch full timeline on subsequent runs**: Must use `since_id` watermark for incremental fetch
- **Deduplicate in Python**: Use SQLite `INSERT OR IGNORE` (Phase 9 pattern)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tweet deduplication | Python dict/set dedupe | SQLite `INSERT OR IGNORE` | Atomic O(1), handles concurrency |
| Watermark tracking | Custom file/JSON | `TweetCache.get_newest_tweet_id()` | Phase 10 established pattern |
| Tweet text extraction | Manual string concat | `" ".join(t.get("text", "") for t in tweets)` | Existing pattern in test_enrich.py |
| Embedding storage | Custom numpy save | `store_tweet_embedding()` | Phase 8 function, handles JSON update |

## Runtime State Inventory

> Not applicable - this phase is code-only changes (no renames, migrations, or OS-registered state).

## Common Pitfalls

### Pitfall 1: Tweet ID Key Mismatch
**What goes wrong:** Cached tweets have `tweet_id` key, API tweets have `id` key.
**Why it happens:** SQLite schema uses `tweet_id` as column name; API uses `id`.
**How to avoid:** When building `recent_tweets_text`, use `.get("text", "")` which works for both.
**Warning signs:** KeyError when iterating tweets for text extraction.

### Pitfall 2: Embedding Rebuild Blocking Pipeline
**What goes wrong:** Embedding rebuild failure stops all subsequent accounts.
**Why it happens:** Unhandled exception in `store_tweet_embedding()`.
**How to avoid:** Wrap in try/except, log warning, continue (per CONTEXT.md decision).
**Warning signs:** Pipeline stops after first embedding error.

### Pitfall 3: Empty Cache First Fetch
**What goes wrong:** First fetch returns empty list if API has no tweets.
**Why it happens:** User has no recent tweets or API returns empty data.
**How to avoid:** Check `if tweets:` before updating account JSON; handle empty gracefully.
**Warning signs:** `recent_tweets_text` set to empty string on first fetch.

### Pitfall 4: Duplicate Tweet Count Growth
**What goes wrong:** Tweet count doesn't grow because duplicates aren't being persisted.
**Why it happens:** `persist_tweets` uses `INSERT OR IGNORE` which skips duplicates.
**How to avoid:** This is correct behavior - verify via `load_tweets().count` after persist.
**Warning signs:** None - this is the expected deduplication behavior.

## Code Examples

### Account JSON Update Pattern
```python
# Source: test_enrich.py lines 274-282 (existing pattern)
cache_path = cache_dir / f"{account_id}.json"
if cache_path.exists():
    with open(cache_path, encoding="utf-8") as f:
        account = json.load(f)
    account["recent_tweets"] = tweets
    account["recent_tweets_text"] = " ".join(t.get("text", "") for t in tweets)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(account, f, indent=2)
```

### Embedding Rebuild with Error Handling
```python
# Source: CONTEXT.md Decision 2 - Log and continue
try:
    embedding = store_tweet_embedding(account_id, cache_dir=cache_dir)
    if embedding:
        logger.info("Tweet embedding created for %s: %d dimensions", account_id, len(embedding))
except Exception as e:
    logger.warning("Embedding rebuild failed for %s: %s", account_id, e)
    # Continue to next account - do NOT rollback account JSON update
```

### TweetCache Integration
```python
# Source: api_client.py get_recent_tweets signature
from src.enrich.tweet_cache import TweetCache

tweet_cache = TweetCache()  # Creates data/tweets.db
tweets = client.get_recent_tweets(
    user_id,
    max_tweets=50,
    tweet_cache=tweet_cache  # Enable accumulation
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Full timeline fetch | Incremental fetch with since_id | Phase 10 | 90%+ API quota savings |
| Python dict dedupe | SQLite INSERT OR IGNORE | Phase 9 | Atomic O(1) deduplication |
| No watermark | get_newest_tweet_id() | Phase 10 | Efficient incremental tracking |

**Deprecated/outdated:**
- Manual tweet deduplication in Python: Use SQLite PRIMARY KEY constraint
- Fetching all tweets on each run: Use `since_id` watermark

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `test_enrich.py` is the canonical enrichment entry point | Architecture | Low - it's the documented test driver |
| A2 | `store_tweet_embedding()` handles JSON update internally | Code Examples | Low - verified in embed.py lines 157-196 |
| A3 | Account JSON files always exist after `get_users()` | Integration Point | Low - `_cache_user()` creates them |

**All core claims verified - no user confirmation needed.**

## Open Questions

None - scope is clear from CONTEXT.md decisions.

## Environment Availability

> Step 2.6: SKIPPED (no external dependencies identified)

All dependencies are Python built-in or already installed in `.venv`:
- `sqlite3`: built-in
- `json`: built-in
- `sentence-transformers`: installed (Phase 8)
- `src.enrich.tweet_cache.TweetCache`: Phase 9
- `src.cluster.embed.store_tweet_embedding`: Phase 8

## Validation Architecture

> **nyquist_validation: false** (from `.planning/config.json`) - Section skipped per workflow config.

### Existing Test Infrastructure
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 |
| Config file | pytest.ini |
| Quick run command | `.venv/bin/python -m pytest tests/test_tweet_cache.py -v -x` |
| Full suite command | `.venv/bin/python -m pytest tests/` |

### Required Integration Tests (per CONTEXT.md)
| Scenario | Test File | Purpose |
|----------|-----------|---------|
| First fetch | `tests/test_tweet_cache.py::TestIntegrationAccumulation` | No cache → API fetch → persist → account JSON update |
| Subsequent fetch | `tests/test_tweet_cache.py::TestIntegrationAccumulation` | Cache exists → since_id → merge → account JSON update |
| Deduplication | `tests/test_tweet_cache.py::TestIntegrationAccumulation` | Same tweet twice → stored once |

### Wave 0 Gaps
- [ ] `TestIntegrationAccumulation` class with first/subsequent fetch tests
- [ ] Account JSON update verification in tests
- [ ] Embedding rebuild error handling test

## Security Domain

> Security enforcement not explicitly disabled, but this phase has minimal security exposure.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A - no auth changes |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A |
| V5 Input Validation | yes | Existing tweet_id TEXT validation (Phase 9) |
| V6 Cryptography | no | N/A |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection | Tampering | Parameterized queries (Phase 9 pattern) |
| JSON injection | Tampering | json.dump() sanitization |

**No new security concerns** - using existing validated patterns from Phase 9/10.

## Sources

### Primary (HIGH confidence)
- `src/enrich/tweet_cache.py` - TweetCache implementation [VERIFIED: codebase]
- `src/enrich/api_client.py` - get_recent_tweets with cache-first logic [VERIFIED: codebase]
- `src/cluster/embed.py` - store_tweet_embedding function [VERIFIED: codebase]
- `src/enrich/test_enrich.py` - Current integration point [VERIFIED: codebase]

### Secondary (MEDIUM confidence)
- `tests/test_tweet_cache.py` - 29 existing tests for cache infrastructure [VERIFIED: codebase]
- `tests/conftest.py` - temp_tweet_cache fixture [VERIFIED: codebase]
- `11-CONTEXT.md` - User decisions [VERIFIED: planning artifacts]

### Tertiary (LOW confidence)
None - all findings verified from codebase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - using existing Phase 9/10 infrastructure
- Architecture: HIGH - integration point clearly identified in test_enrich.py
- Pitfalls: HIGH - key mismatches already handled in Phase 10 tests

**Research date:** 2026-04-12
**Valid until:** 30 days (stable infrastructure, no external API changes expected)

---

*Phase 11 research complete. Ready for planning.*