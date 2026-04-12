# Project Research Summary

**Project:** X Following Organizer - Tweet Caching with Accumulation (v1.2)
**Domain:** Tweet caching for X API enrichment pipeline
**Researched:** 2026-04-12
**Confidence:** HIGH

## Executive Summary

This milestone adds tweet caching with accumulation to an existing X API enrichment pipeline. The system currently overwrites `recent_tweets` on each run; the goal is to accumulate tweets across runs while using incremental fetch (`since_id`) to minimize API calls. Research strongly recommends **SQLite as a separate tweet database** rather than embedding tweets in account JSON files — this enables O(1) deduplication via PRIMARY KEY, indexed queries for `since_id` watermarks, and efficient accumulation without file bloat.

The recommended approach introduces a new `TweetCache` component that orchestrates cache-first fetching: load existing cached tweets, determine the newest tweet ID, fetch only new tweets via `since_id`, merge and dedupe, then persist atomically. Key risks include tweet ID precision loss (must use TEXT storage), race conditions during writes (must use atomic `os.replace()` pattern), and unbounded growth (should implement practical size limits per user despite "no limit" spec).

## Key Findings

### Recommended Stack

The existing codebase uses synchronous Python with per-account JSON caching. This milestone adds **SQLite** for tweet storage — a zero-dependency, built-in solution that handles accumulation and deduplication efficiently.

**Core technologies:**
- **SQLite (`sqlite3`)** — Tweet cache database with WAL mode. Zero dependencies, PRIMARY KEY deduplication, indexed queries for `since_id` watermarks, handles 500K+ tweets easily.
- **Tweepy 4.14+** — Already in use; supports `since_id` parameter for incremental fetch.
- **Atomic file writes (`os.replace`)** — For JSON cache writes; prevents corruption during concurrent access.

**What NOT to add:**
- `aiosqlite` — 15x slower for sequential operations; no benefit for sync code
- SQLAlchemy — ORM overhead for simple key-value access
- Embedding tweets in account JSON — Inefficient deduplication (O(n)), file bloat, no indexing

### Expected Features

Research identified clear prioritization based on CACHE-01, CACHE-02, CACHE-03 requirements.

**Must have (table stakes - P1):**
- Cache hit path — If tweets exist in cache, skip API call; return cached data
- Deduplication by ID — Use tweet `id` as unique key; O(1) lookup via PRIMARY KEY
- Accumulation (no storage limit) — Merge new tweets with existing; keep historical posts

**Should have (competitive - P2):**
- Incremental fetch (`since_id` watermarks) — Fetch only NEW tweets since last run; saves API quota
- Freshness timestamp — Store `tweets_last_fetched_at` for visibility into cache age

**Defer (v2+):**
- Backfill (`until_id`) — Fetch older tweets beyond initial window
- Tweet pruning — Remove deleted tweets
- Compressed storage — Gzip for accounts with hundreds of tweets

### Architecture Approach

The current architecture fetches tweets via `XEnrichmentClient.get_recent_tweets()` and overwrites the `recent_tweets` array in each account's JSON file. The new architecture introduces a **TweetCache component** that intercepts tweet fetching and implements cache-first logic.

**Major components:**
1. **TweetCache (NEW)** — Orchestrates cache-first fetching with accumulation. Methods: `load_cached()`, `fetch_new()`, `merge_and_dedupe()`, `persist()`.
2. **SQLite tweets.db (NEW)** — Separate database at `data/tweets.db` with indexed `tweet_id` (PRIMARY KEY), `user_id`, and `created_at`.
3. **XEnrichmentClient (MODIFIED)** — `get_recent_tweets()` delegates to TweetCache; no longer fetches blindly.
4. **Consumer layer (UNCHANGED)** — `embed.py` and `entities.py` continue reading `recent_tweets_text`.

**Data flow:**
Load existing -> Extract newest tweet ID -> Fetch new tweets with `since_id` -> Merge and dedupe -> Persist atomically.

### Critical Pitfalls

1. **JSON precision loss with tweet IDs** — X snowflake IDs are 64-bit; JavaScript/JSON only support 53-bit. Store tweet IDs as TEXT, use `id_str` from API.
2. **Race condition during cache write** — JSON writes are not atomic. Use `tempfile.mkstemp()` + `os.replace()` pattern; add `fsync()` before replace.
3. **Unbounded cache growth** — CACHE-03 says "no limit" but practical bounds needed. Implement per-user max (e.g., 200 tweets) or age-based pruning.
4. **Incorrect `since_id` usage** — `since_id` is EXCLUSIVE (returns tweets > ID). Store the highest (newest) tweet ID after each fetch.
5. **Duplicate tweets in accumulation** — Naive `extend()` adds duplicates. Use dict keyed by ID: `{t['id']: t for t in existing + new}.values()`.

## Implications for Roadmap

Based on combined research, suggested phase structure:

### Phase 1: TweetCache Core with SQLite Schema
**Rationale:** Foundation layer; all other work depends on storage existing.
**Delivers:** SQLite database schema, TweetCache class with load/save methods.
**Addresses:** CACHE-01 (cache read/write path), CACHE-02 (deduplication via PRIMARY KEY).
**Avoids:** Pitfall 1 (ID precision loss — store as TEXT), Pitfall 2 (race conditions — SQLite handles locking).

### Phase 2: Incremental Fetch Integration
**Rationale:** API efficiency optimization; reduces quota usage by fetching only new tweets.
**Delivers:** `since_id` watermark tracking, modified `get_recent_tweets()` that delegates to TweetCache.
**Uses:** Tweepy `since_id` parameter, SQLite `created_at DESC` index.
**Implements:** TweetCache.fetch_new() method.

### Phase 3: Accumulation and Persistence
**Rationale:** Merges new with existing; implements "no limit" storage requirement.
**Delivers:** Merge-and-dedupe logic, atomic persistence, watermark updates.
**Addresses:** CACHE-02 (accumulation), CACHE-03 (no storage limit).
**Avoids:** Pitfall 4 (incorrect since_id), Pitfall 5 (duplicate accumulation).

### Phase 4: Integration Testing
**Rationale:** End-to-end validation of cache-first flow before shipping.
**Delivers:** Test suite covering first fetch vs subsequent, deduplication, embedding rebuild.
**Verifies:** All critical pitfalls have tests per pitfall-to-phase mapping.

### Phase Ordering Rationale

- **Phase 1 first:** Storage must exist before any fetch logic. SQLite schema with TEXT primary key prevents ID precision loss from day one.
- **Phase 2 next:** Once storage exists, optimize the fetch path. Incremental fetch reduces API quota usage by 90%+ on subsequent runs.
- **Phase 3 after fetch:** Accumulation depends on both storage (Phase 1) and incremental fetch (Phase 2) working correctly.
- **Phase 4 last:** Integration tests require all components working together.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Tweepy pagination edge cases — verify `since_id` behavior with actual API responses, test rate limit header parsing.
- **Phase 3:** Unbounded growth policy — "no limit" spec conflicts with practical concerns; may need product decision on soft limits.

Phases with standard patterns (skip research-phase):
- **Phase 1:** SQLite schema is well-documented; standard patterns for PRIMARY KEY, indexes, WAL mode.
- **Phase 4:** Integration testing patterns are standard; existing test suite provides templates.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | SQLite is battle-tested; official docs and benchmarks confirm recommendations. Schema design verified against `twitter-to-sqlite` reference. |
| Features | HIGH | Clear prioritization based on PROJECT.md requirements. P1/P2/P3 separation follows user value vs implementation cost. |
| Architecture | HIGH | Existing codebase analysis confirms integration points. TweetCache design follows existing patterns (XEnrichmentClient, per-account caching). |
| Pitfalls | HIGH | Official X API docs verified `since_id` semantics. Production bugs from GitHub issues provide real-world evidence. |

**Overall confidence:** HIGH

### Gaps to Address

- **Tweepy rate limit handling:** Research recommends parsing `x-rate-limit-remaining` headers. Verify Tweepy's built-in rate limit handling vs custom implementation during Phase 2 planning.
- **Unbounded growth decision:** CACHE-03 says "no limit" but Pitfall 3 warns of practical issues. During Phase 3, decide if soft limits (e.g., max 200 tweets per user) are acceptable or if true unbounded storage is required.

## Sources

### Primary (HIGH confidence)
- [Twitter Developer Docs — Working with Timelines](https://developer.x.com/en/docs/x-api/v1/tweets/timelines/guides/working-with-timelines) — Official `since_id`/`max_id` semantics
- [Twitter Developer Docs — Twitter IDs](https://developer.x.com/en/docs/twitter-ids) — 64-bit ID handling requirements
- [twitter-to-sqlite v0.22](https://pypi.org/project/twitter-to-sqlite/) — Production schema patterns for tweet storage
- [SQLite Performance Benchmarks 2025](https://toxigon.com/sqlite-performance-benchmarks-2025-edition) — WAL mode, batch inserts, indexing

### Secondary (MEDIUM confidence)
- [Fetching X Timelines with API v2 Pay-Per-Use](https://dev.to/ikka/fetching-x-timelines-with-api-v2-pay-per-use-cost-breakdown-caching-and-the-gotchas-1i2o) — Practical caching patterns
- [Incremental Web Scraping & Data Feeds](https://jamesjlaurieiii.com/resources/incremental-web-scraping-data-feeds.html) — Two watermarks pattern
- [botocore JSONFileCache Race Condition — GitHub Issue #3213](https://github.com/boto/botocore/issues/3213) — Verified production bug on atomic writes

### Tertiary (LOW confidence)
- [Designing a Distributed Cache Platform at Twitter Scale](https://medium.com/@shree6791/designing-a-distributed-cache-platform-at-twitter-scale-24428fa964fa) — General caching patterns (over-engineering for this use case)

---
*Research completed: 2026-04-12*
*Ready for roadmap: yes*