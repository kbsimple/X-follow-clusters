# ROADMAP: X Following Organizer

**Project:** X Following Organizer
**Granularity:** Coarse (3-5 phases, 1-3 plans each)
**YOLO Mode:** Enabled

---

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-04-06) — [v1.0-ROADMAP.md](./milestones/v1.0-ROADMAP.md)
- ✅ **v1.1** — OAuth 2.0 PKCE + Scrape Enhancement (Phase 7-8, shipped 2026-04-12)
- 🚧 **v1.2** — Caching API Calls (Phase 9-11, in progress)

---

## Phases

- [ ] **Phase 9: TweetCache Core** — SQLite schema and cache read/write foundation
- [ ] **Phase 10: Incremental Fetch** — since_id watermarks for efficient API usage
- [ ] **Phase 11: Accumulation & Integration** — Merge logic, persistence, and end-to-end validation

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
- [ ] 09-01-PLAN.md — Create TweetCache class with SQLite schema, load_tweets, persist_tweets methods

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

**Plans:** TBD

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

**Plans:** TBD

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 9. TweetCache Core | 0/1 | Not started | - |
| 10. Incremental Fetch | 0/2 | Not started | - |
| 11. Accumulation & Integration | 0/3 | Not started | - |

---

## Coverage Map

| Requirement | Phase | Description |
|-------------|-------|-------------|
| CACHE-01 | 10 | Enrichment reads tweets from cache, fetches only new tweets on miss |
| CACHE-02 | 9, 11 | Tweets cached with accumulation across runs (dedupe by ID) |
| CACHE-03 | 11 | No limit on stored posts — cache grows over multiple invocations |

**Coverage:** 3/3 requirements mapped ✓

---

*Last updated: 2026-04-12 — Phase 9 planned*