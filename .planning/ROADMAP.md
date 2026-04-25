# ROADMAP: X Following Organizer

**Project:** X Following Organizer
**Granularity:** Coarse (3-5 phases, 1-3 plans each)
**YOLO Mode:** Enabled

---

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-04-06) — [v1.0-ROADMAP.md](./milestones/v1.0-ROADMAP.md)
- ✅ **v1.1** — OAuth 2.0 PKCE + Scrape Enhancement (Phase 7-8, shipped 2026-04-12)
- ✅ **v1.2** — Caching API Calls (Phase 9-11, shipped 2026-04-18) — [v1.2-ROADMAP.md](./milestones/v1.2-ROADMAP.md)
- ✅ **v1.3** — Embedding Cache Enhancement (Phase 12, shipped 2026-04-24)

---

## Phases

- [x] **Phase 12: SQLite Embedding Cache** — Incremental embedding updates with model version tracking (completed 2026-04-24)
- [x] **Phase 9: TweetCache Core** — SQLite schema and cache read/write foundation
- [x] **Phase 10: Incremental Fetch** — since_id watermarks for efficient API usage
- [x] **Phase 11: Accumulation & Integration** — Merge logic, persistence, and end-to-end validation (completed 2026-04-15)

---

## Phase Details

### Phase 9: TweetCache Core

**Goal:** Storage layer exists for tweet caching with O(1) deduplication

**Depends on:** Phase 8 (3scrape complete)

**Requirements:** CACHE-02 (partial - deduplication foundation)

**Success Criteria** (what must be TRUE):
1. SQLite database `data/tweets.db` created with proper schema (tweet_id TEXT PRIMARY KEY, user_id, created_at indexed)
2. TweetCache class can load all cached tweets for a user from SQLite
3. TweetCache class can persist tweets to SQLite with automatic deduplication via PRIMARY KEY
4. Tweet IDs stored as TEXT to prevent JavaScript precision loss (X snowflake IDs are 64-bit)

**Plans:** 1 plan

Plans:
- [x] 09-01-PLAN.md — Create TweetCache class with SQLite schema, load_tweets, persist_tweets methods

---

### Phase 10: Incremental Fetch

**Goal:** Enrichment pipeline fetches only NEW tweets, minimizing API quota usage

**Depends on:** Phase 9 (TweetCache Core)

**Requirements:** CACHE-01 (fetches only new tweets on miss)

**Success Criteria** (what must be TRUE):
1. `since_id` watermark tracked per user (stored as newest tweet ID after each fetch)
2. On cache hit (tweets exist), enrichment returns cached tweets without API call
3. On cache miss, only new tweets fetched via `since_id` parameter (not full timeline)
4. XEnrichmentClient.get_recent_tweets() delegates to TweetCache for cache-first logic

**Plans:** 2/2 plans executed

Plans:
- [x] 10-01-PLAN.md — Add get_newest_tweet_id method to TweetCache for watermark tracking
- [x] 10-02-PLAN.md — Modify get_recent_tweets with cache-first logic and since_id integration

---

### Phase 11: Accumulation & Integration

**Goal:** Tweets accumulate across runs with merge logic, unbounded storage, and validated end-to-end flow

**Depends on:** Phase 10 (Incremental Fetch)

**Requirements:** CACHE-02 (accumulation, dedupe by ID), CACHE-03 (no storage limit)

**Success Criteria** (what must be TRUE):
1. New tweets merge with existing cached tweets without duplicates (dict keyed by ID)
2. Tweet count grows across multiple enrichment runs (historical posts preserved)
3. Watermark updated atomically after successful merge and persist
4. Consumer layer (embed.py, entities.py) receives merged tweet list unchanged
5. Integration tests cover first fetch vs subsequent, deduplication, and embedding rebuild

**Plans:** 2/2 plans complete

Plans:
- [x] 11-01-PLAN.md — Integrate TweetCache in test_enrich.py with error handling
- [x] 11-02-PLAN.md — Add comprehensive integration tests for accumulation flow

---

### Phase 12: SQLite Embedding Cache

**Goal:** Embedding cache supports incremental updates, model version tracking, and text change detection

**Depends on:** Phase 11 (Accumulation & Integration)

**Requirements:** EMBED-01 (incremental updates), EMBED-02 (model version tracking), EMBED-03 (text hash invalidation)

**Success Criteria** (what must be TRUE):
1. SQLite database `data/embeddings.db` created with schema (account_id TEXT PRIMARY KEY, embedding BLOB, text_hash TEXT, model_version TEXT)
2. EmbeddingCache class provides load/save/query operations with WAL mode
3. embed_accounts() uses cache for incremental updates (only compute new/changed accounts)
4. Model version stored and checked — cache invalidated on model change
5. Text hash stored — re-compute embedding when bio/location changes
6. All embeddings loadable as numpy array for clustering operations

**Plans:** 2/2 plans complete

Plans:
- [x] 12-01-PLAN.md — Create EmbeddingCache class with SQLite schema, BLOB serialization, model version tracking
- [x] 12-02-PLAN.md — Integrate EmbeddingCache into embed_accounts() for incremental updates

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 12. SQLite Embedding Cache | 2/2 | Complete | 2026-04-24 |
| 9. TweetCache Core | 1/1 | Complete | 2026-04-12 |
| 10. Incremental Fetch | 2/2 | Complete | 2026-04-12 |
| 11. Accumulation & Integration | 2/2 | Complete | 2026-04-15 |

---

## Coverage Map

| Requirement | Phase | Description |
|-------------|-------|-------------|
| CACHE-01 | 10 | Enrichment reads tweets from cache, fetches only new tweets on miss |
| CACHE-02 | 9, 11 | Tweets cached with accumulation across runs (dedupe by ID) |
| CACHE-03 | 11 | No limit on stored posts — cache grows over multiple invocations |
| EMBED-01 | 12 | Embedding cache supports incremental updates (only compute new/changed accounts) |
| EMBED-02 | 12 | Model version tracked and cache invalidated on model change |
| EMBED-03 | 12 | Text hash stored for re-computation when bio/location changes |

**Coverage:** 6/6 requirements mapped

---
*Last updated: 2026-04-24 — Phase 12 complete: SQLite Embedding Cache*