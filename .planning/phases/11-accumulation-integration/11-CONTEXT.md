---
phase: 11-accumulation-integration
created: 2026-04-12
status: complete
---

# Phase 11 CONTEXT: Accumulation & Integration

**Domain:** Tweets accumulate across runs with merge logic, unbounded storage, and validated end-to-end flow

---

## Prior Context Applied

### From Phase 9 (TweetCache Core)
- SQLite storage with TEXT PRIMARY KEY for tweet_id
- `INSERT OR IGNORE` provides atomic O(1) deduplication
- WAL mode for concurrent reads during writes
- `load_tweets` returns tweets ordered by `created_at DESC`

### From Phase 10 (Incremental Fetch)
- `get_newest_tweet_id` provides watermark for `since_id`
- `get_recent_tweets` implements cache-first logic
- Merged result: `new_tweets + cached_result.tweets`
- Graceful degradation: cached tweets returned on API failure

### From Phase 8 (3scrape)
- `recent_tweets_text` field in account JSON for tweet embeddings
- `create_tweet_embedding` and `store_tweet_embedding` functions exist

---

## Decisions

### 1. Tweet Flow to Embedding Layer
**Decision:** Update account JSON on enrichment

After `get_recent_tweets` returns merged tweets, write merged tweet text to account JSON as `recent_tweets_text` field.

**Rationale:** `embed.py` already reads `recent_tweets_text` from account JSON. No changes needed to embedding layer.

**Implementation:**
- `XEnrichmentClient.get_recent_tweets` continues to return merged tweets
- Enrichment pipeline writes merged tweet text to `{account_id}.json` as `recent_tweets_text`
- `embed.py` reads `recent_tweets_text` unchanged

### 2. Error Handling Strategy
**Decision:** Log and continue

When embedding rebuild fails after tweet merge, log the error and continue. Account JSON keeps existing `recent_tweets_text`. Next enrichment run will retry.

**Rationale:** Batch processing should not fail on single account errors. Graceful degradation matches Phase 10 pattern.

**Implementation:**
- Wrap embedding rebuild in try/except
- Log error with account_id and exception
- Continue to next account
- Do NOT rollback account JSON update

### 3. Integration Test Scope
**Decision:** Core first vs subsequent fetch tests

Test cases:
1. **First fetch:** No cache exists → fetches from API → persists to cache → updates account JSON
2. **Subsequent fetch:** Cache exists → uses `since_id` → merges new + cached → updates account JSON
3. **Deduplication:** Same tweet fetched twice → stored once (PRIMARY KEY constraint)

**Rationale:** Core flow validation ensures accumulation works end-to-end. Error paths tested via unit tests.

---

## Deferred Ideas

None - scope is clear.

---

## Canonical Refs

- `src/enrich/tweet_cache.py` — TweetCache class with SQLite storage
- `src/enrich/api_client.py` — XEnrichmentClient with cache-first logic
- `src/cluster/embed.py` — Tweet embedding functions
- `tests/test_tweet_cache.py` — Existing TweetCache tests

---

## Next Steps

Run `/gsd-plan-phase 11` to create implementation plans.

---

*Last updated: 2026-04-12*