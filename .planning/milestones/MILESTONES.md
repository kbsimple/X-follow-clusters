# Milestones

## v1.2 Caching API Calls — 2026-04-18

**Status:** ✅ SHIPPED
**Phases:** 9-11 | **Plans:** 5 | **Tasks:** ~8

### Accomplishments

1. SQLite-backed TweetCache class with TEXT tweet_id PRIMARY KEY, WAL mode, and O(1) deduplication via INSERT OR IGNORE
2. TweetCache method for O(1) newest tweet ID lookup using existing created_at DESC index
3. XEnrichmentClient.get_recent_tweets with cache-first logic, since_id watermarks, and graceful degradation on API failure
4. TweetCache integrated into enrichment pipeline with graceful embedding failure handling
5. 6 integration tests for accumulation flow (first fetch, subsequent merge, deduplication, watermark tracking)

**Files changed:** ~15 | **Timeline:** 3 days (4/12-4/18)

**Tech debt:** None new

---

## v1.1 OAuth 2.0 PKCE + Scrape Enhancement — 2026-04-12

**Status:** ✅ SHIPPED
**Phases:** 7-8 | **Plans:** 12 | **Tasks:** ~12

### Accomplishments

1. OAuth 2.0 PKCE upgrade — XAuth dataclass migrated to OAuth 2.0 fields, interactive PKCE flow with browser auth, token persistence to data/tokens.json
2. verify_credentials() and XEnrichmentClient updated for OAuth 2.0 Bearer token
3. 3scrape pipeline — Link → Entity → Google for cold-start accounts
4. GLiNER entity extraction from bio + pinned_tweet + external_bio text
5. Link follower for accounts with websites but no/short bio
6. SerpApi Google search for accounts with no bio AND no website
7. get_text_for_embedding() updated with entity fields
8. 59 tests passing (Phase 7 + Phase 8 test coverage)

**Files changed:** ~20 | **Timeline:** 1 day (4/11)

**Tech debt:** 32 unpushed commits on master (git push pending)

---

## v1.0 MVP — 2026-04-06

**Status:** ✅ SHIPPED
**Phases:** 6 | **Plans:** 12 | **Tasks:** ~24

### Accomplishments

1. Archive Parsing + Auth — Built `follower.js` parser with per-entry error handling and X API auth via tweepy OAuth 1.0a
2. API Enrichment — Batch enrichment via `GET /2/users` (100/req) with exponential backoff, suspended/protected flagging, immediate disk caching
3. Profile Scraping — Supplemental scraping via curl_cffi with TLS impersonation, robots.txt compliance, graceful block fallback
4. NLP Clustering — Bio embeddings via `all-MiniLM-L6-v2`, semi-supervised K-Means with seed anchoring, LLM-generated cluster names
5. Review Flow — Interactive CLI with approve/reject/rename/merge/split/defer, batch approve, cluster histogram, automation offer after N rounds
6. List Creation + Export — Native X API lists (5-50 members), HTTP 409 conflict pre-check, Parquet + CSV data export, 15 unit tests

**Files changed:** 95 | **Lines:** ~16,540 | **Timeline:** 4 days

**Tech debt:** seed_accounts.yaml placeholders; no live API integration tests

**Audit:** ✅ 45/45 requirements satisfied (3 checkbox-maintenance gaps noted)

---
