# Feature Research: Tweet Caching with Accumulation

**Domain:** Tweet caching for social media enrichment pipeline
**Researched:** 2026-04-12
**Confidence:** HIGH (existing codebase analysis + established patterns)

---

## Context

This is a **subsequent milestone** adding tweet caching to an existing app. The project already has:
- X API profile enrichment with disk caching (per-account JSON files in `data/enrichment/`)
- Recent tweets fetch (50 tweets per account, currently overwrites on each run)
- Tweet embeddings for topical clustering (uses `recent_tweets_text` field)

**Focus:** Only the NEW caching feature requirements (CACHE-01, CACHE-02, CACHE-03 from PROJECT.md).

---

## Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Cache hit path** | Fetching tweets is slow/expensive; second run should be instant | LOW | Read from `{account_id}.json` if tweets exist; no API call needed |
| **Deduplication by ID** | Same tweet fetched multiple times = corrupted data | LOW | Use tweet ID as unique key; store as dict keyed by ID for O(1) lookup |
| **Accumulation across runs** | Data should grow, not replace; user wants more signal over time | MEDIUM | Merge new tweets into existing; keep all historical posts |
| **Graceful degradation on API errors** | Partial data better than no data | LOW | Return cached tweets on fetch failure; log warning |

---

## Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Incremental fetch (watermarks)** | Only fetch NEW tweets since last run; saves API quota | MEDIUM | Track `newest_tweet_id` watermark; use X API `since_id` parameter |
| **Backfill support** | Fetch older tweets beyond initial 50 on subsequent runs | MEDIUM | Track `oldest_tweet_id` watermark; use `until_id` parameter for pagination |
| **No storage limit** | Cache grows unbounded; 50 tweets per run accumulates to hundreds | LOW | Remove the `max_tweets` cap on storage; keep all accumulated tweets |
| **Freshness watermark** | Know when cache was last updated without opening file | LOW | Store `tweets_last_fetched_at` timestamp in account JSON |

---

## Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Real-time tweet polling** | "Always have latest tweets" | Adds complexity; violates "one-time run" constraint; burns API quota | On-demand refresh via explicit command |
| **TTL-based cache invalidation** | "Keep data fresh" | Tweets are immutable; no benefit to re-fetching same IDs | Watermark-based incremental fetch |
| **Separate tweet cache file** | "Cleaner separation" | Account JSON is already the cache unit; adds file I/O overhead | Store `recent_tweets` array within account JSON |
| **Fetch all historical tweets** | "Complete history" | X API pagination limit (~3200 tweets); burns massive quota; rarely needed | Accumulate 50 per run; user can run multiple times |

---

## Feature Dependencies

```
[Incremental Fetch (since_id)]
    └──requires──> [newest_tweet_id watermark stored in cache]
    └──requires──> [Cache hit path: read before write]

[Deduplication by ID]
    └──requires──> [Tweet objects have 'id' field from API]

[Accumulation]
    └──requires──> [Deduplication by ID]
    └──requires──> [Cache hit path: merge with existing]

[No storage limit]
    └──requires──> [Accumulation]
    └──conflicts──> [max_tweets parameter on fetch] (remove from storage, keep on API pagination)
```

### Dependency Notes

- **Incremental Fetch requires newest_tweet_id watermark:** The X API `since_id` parameter returns tweets newer than the given ID. Without storing the newest ID from the previous run, we cannot skip already-fetched tweets.
- **Accumulation requires Deduplication:** If we merge without deduping, the same tweet appears multiple times when re-fetched, corrupting embeddings and entity extraction.
- **No storage limit conflicts with max_tweets parameter:** Currently `max_tweets=50` is both the API pagination limit AND the storage cap. These must be separated: keep 50 for API batching, remove storage cap.

---

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept.

- [ ] **Cache hit path** — If `recent_tweets` exists in account JSON, skip API call; return cached data
- [ ] **Deduplication by ID** — Merge new tweets into existing array; drop duplicates by tweet ID
- [ ] **Accumulation** — Remove storage cap; keep all tweets across runs (API still fetches 50 per call)

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] **Incremental fetch (watermarks)** — Store `newest_tweet_id` and use `since_id` parameter to fetch only new tweets
- [ ] **Freshness timestamp** — Store `tweets_last_fetched_at` for visibility into cache age

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] **Backfill (oldest_tweet_id)** — Use `until_id` to fetch older tweets beyond initial window
- [ ] **Tweet pruning** — Remove deleted tweets (requires tweet existence check)
- [ ] **Compressed storage** — Gzip compress tweet array for accounts with hundreds of tweets

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Cache hit path | HIGH | LOW | P1 |
| Deduplication by ID | HIGH | LOW | P1 |
| Accumulation (no storage limit) | HIGH | LOW | P1 |
| Incremental fetch (since_id) | MEDIUM | MEDIUM | P2 |
| Freshness timestamp | LOW | LOW | P3 |
| Backfill (oldest_tweet_id) | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch (CACHE-01, CACHE-02, CACHE-03 requirements)
- P2: Should have, add when possible (optimization for API quota)
- P3: Nice to have, future consideration

---

## Implementation Notes

### Current State (from codebase analysis)

The existing implementation in `src/enrich/api_client.py`:

```python
def get_recent_tweets(self, user_id: str, max_tweets: int = 50) -> list[dict]:
    # Fetches up to 50 tweets via pagination
    # Returns list; does NOT cache internally
```

The test harness in `src/enrich/test_enrich.py` (lines 277-282):

```python
account["recent_tweets"] = tweets  # OVERWRITES existing!
account["recent_tweets_text"] = " ".join(t.get("text", "") for t in tweets)
```

**Problem:** Current implementation OVERWRITES `recent_tweets` on each run. This violates CACHE-02 accumulation requirement.

### Recommended Implementation Pattern

```python
def get_tweets_with_cache(
    self,
    user_id: str,
    cache_path: Path,
    fetch_limit: int = 50,  # API pagination limit (not storage limit)
) -> tuple[list[dict], bool]:
    """
    Fetch tweets with cache accumulation.

    Returns:
        (tweets_list, was_cache_hit)
    """
    # 1. Load existing cache
    if cache_path.exists():
        account = json.loads(cache_path.read_text())
        existing_tweets = account.get("recent_tweets", [])
        existing_ids = {t["id"] for t in existing_tweets}
        newest_id = max((t["id"] for t in existing_tweets), default=None)
    else:
        existing_tweets = []
        existing_ids = set()
        newest_id = None

    # 2. Fetch new tweets (since_id if watermark exists)
    new_tweets = self._fetch_tweets_paginated(
        user_id,
        max_tweets=fetch_limit,
        since_id=newest_id,  # Only fetch newer than cached
    )

    # 3. Dedupe and merge
    merged_tweets = existing_tweets.copy()
    for tweet in new_tweets:
        if tweet["id"] not in existing_ids:
            merged_tweets.append(tweet)

    # 4. Sort by created_at descending (newest first)
    merged_tweets.sort(key=lambda t: t["created_at"], reverse=True)

    # 5. Update watermarks and timestamp
    if merged_tweets:
        account["newest_tweet_id"] = merged_tweets[0]["id"]
        account["oldest_tweet_id"] = merged_tweets[-1]["id"]
        account["tweets_last_fetched_at"] = datetime.utcnow().isoformat()

    account["recent_tweets"] = merged_tweets
    account["recent_tweets_text"] = " ".join(t.get("text", "") for t in merged_tweets)

    # 6. Write back to cache
    cache_path.write_text(json.dumps(account, indent=2))

    return merged_tweets, len(new_tweets) == 0  # cache_hit if no new tweets
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Store tweets in account JSON | Existing cache pattern; no new file I/O overhead |
| Use `since_id` for incremental fetch | X API native parameter; returns only newer tweets |
| Keep tweets sorted newest-first | Embeddings use most recent content; consistent ordering |
| No TTL on cache | Tweets are immutable; no benefit to invalidation |
| Keep API limit separate from storage limit | API pagination is 50/request; storage is unbounded |

---

## Sources

- [Designing a Distributed Cache Platform at Twitter Scale](https://medium.com/@shree6791/designing-a-distributed-cache-platform-at-twitter-scale-24428fa964fa) (March 2026)
- [Fetching X Timelines with API v2 Pay-Per-Use: Cost Breakdown, Caching, and the Gotchas](https://dev.to/ikka/fetching-x-timelines-with-api-v2-pay-per-use-cost-breakdown-caching-and-the-gotchas-1i2o) (March 2026)
- [Affordable Storage for Real-Time Twitter Data](https://twitterapi.io/articles/affordable-storage-for-real-time-twitter-data) (2026)
- [Incremental Web Scraping & Data Feeds](https://jamesjlaurieiii.com/resources/incremental-web-scraping-data-feeds.html) (two watermarks pattern)
- [Stale-While-Revalidate: The Caching Pattern That Balances Speed and Freshness](https://www.paulserban.eu/blog/post/stale-while-revalidate-the-caching-pattern-that-balances-speed-and-freshness/) (SWR pattern)
- Existing codebase: `src/enrich/api_client.py` (get_recent_tweets method)
- Existing codebase: `src/enrich/test_enrich.py` (tweet storage pattern)
- Existing codebase: `src/cluster/embed.py` (tweet embedding usage)

---
*Feature research for: Tweet caching with accumulation*
*Researched: 2026-04-12*