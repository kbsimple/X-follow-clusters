# Requirements: X Following Organizer

**Project:** X Following Organizer
**Scope:** v1 (MVP)
**Status:** Active

---

## Requirement IDs

Format: `[CATEGORY]-[NUMBER]` (e.g., PARSE-01, ENRICH-03)

---

## v1 Requirements

### PARSE — Archive Parsing

- [x] **PARSE-01**: Parse `following.js` from X data archive export, extracting account IDs (usernames resolved via X API)
- [x] **PARSE-02**: Handle edge cases (escaped Unicode, renamed/deleted accounts) with per-entry error handling and logging
- [x] **PARSE-03**: Validate JSON structure before processing; fail fast with clear error if format unexpected

### AUTH — API Authentication

- [x] **AUTH-01**: Environment variable storage for X API credentials (Bearer token, API key/secret, access token/secret)
- [x] **AUTH-02**: Verify credentials with a lightweight endpoint (`GET /2/users/me`) before batch operations
- [x] **AUTH-03**: Explore alternatives to paid X API (third-party services: Apify, Bright Data; document findings before committing to paid tier)

### ENRICH — Profile Enrichment (X API)

- [x] **ENRICH-01**: Batch profile enrichment via `GET /2/users` (up to 100 user IDs per call)
- [x] **ENRICH-02**: Track `x-rate-limit-remaining` and `x-rate-limit-reset` headers; implement exponential backoff with jitter
- [x] **ENRICH-03**: Detect and flag suspended accounts (error code 63) and protected accounts (error code 179)
- [x] **ENRICH-04**: Extract profile fields: bio, location, professional_category, pinned tweet text, follower/following counts, verified status
- [x] **ENRICH-05**: Cache all API responses to disk immediately (never re-request within session)

### SCRAPE — Profile Enrichment (Scraping)

- [x] **SCRAPE-01**: Supplemental profile page scraping for fields the API doesn't expose
- [x] **SCRAPE-02**: TLS impersonation via `curl_cffi` to avoid fingerprinting blocks
- [x] **SCRAPE-03**: Random delays (2–5s with jitter) between scraping requests
- [x] **SCRAPE-04**: Check `robots.txt` before scraping; document which fields are scraped and legal basis
- [x] **SCRAPE-05**: Graceful degradation when scraping is blocked (fall back to API data only)

### CLUSTER — NLP Clustering

- [x] **CLUSTER-01**: Generate bio text embeddings via `sentence-transformers` (`all-MiniLM-L6-v2` default model)
- [x] **CLUSTER-02**: Apply NLP clustering on embeddings with configurable algorithm (HDBSCAN or K-Means)
- [x] **CLUSTER-03**: Enforce cluster size constraints: minimum 5 people, maximum 50 people per cluster
- [x] **CLUSTER-04**: LLM-generated cluster names from member profiles (not just keyword extraction)
- [x] **CLUSTER-05**: Anchor clustering with seed categories: Geographic, Occupation, Political Action, Entertainment
- [x] **CLUSTER-06**: Discover additional categories beyond seed set based on profile content
- [x] **CLUSTER-07**: Report cluster size histogram; warn if >50% of clusters have fewer than 5 members
- [x] **CLUSTER-08**: Detect over-clustering and under-clustering via silhouette score; flag when score < 0.3

### REVIEW — Semi-Automated Review Flow

- [ ] **REVIEW-01**: Display suggested clusters grouped by category type with member previews
- [ ] **REVIEW-02**: Show confidence scores for cluster membership (per-member assignment confidence)
- [ ] **REVIEW-03**: Support per-cluster actions: approve, reject, rename, merge with another cluster, split
- [ ] **REVIEW-04**: Batch actions: approve all clusters with >N members and confident names
- [ ] **REVIEW-05**: Allow deferring a cluster without blocking others ("not sure yet")
- [x] **REVIEW-06**: Present cluster size distribution before review; warn if heavily skewed to small clusters
- [x] **REVIEW-07**: After N approved rounds (configurable), offer to enable full automation mode

### LIST — X API List Creation

- [ ] **LIST-01**: Create native X API lists for approved clusters (5–50 people per list)
- [ ] **LIST-02**: Use `POST /2/lists` for list creation; handle naming conflicts (HTTP 409) gracefully
- [ ] **LIST-03**: Bulk add members via `POST /2/lists/{id}/members/add_all` (up to 100 per request)
- [ ] **LIST-04**: Validate list sizes against X's 5,000 member cap and 1,000 lists/account limit
- [ ] **LIST-05**: Verify list creation is possible with a test call before full run

### EXPORT — Data Export

- [ ] **EXPORT-01**: Export follower records with enrichment data and cluster assignments to Parquet
- [ ] **EXPORT-02**: Export final approved clusters to CSV with list name, member handles, and cluster metadata

---

## v2 Requirements (Deferred)

- [ ] Bot/fake account detection (Botometer or ML-based)
- [ ] Account activity scoring (active vs inactive)
- [ ] Network-based clustering (follower overlap / who-follows-whom)
- [ ] Historical follower tracking (delta snapshots over time)
- [ ] Cross-platform identity linking (LinkedIn, websites)
- [ ] Smart/auto-updating lists (rule-based membership that auto-updates)

---

## Out of Scope

| Exclusion | Reason |
|-----------|--------|
| Real-time monitoring or notifications | One-time (or on-demand) run only |
| Posting or interacting with lists | Read/creation only |
| Integrating with other social platforms | X only |
| Auto-follow on list add | Creeps users out; violates trust |
| Scraping without TLS impersonation | Immediately blocked by X |
| TF-IDF-only clustering | Poor quality on short bios |
| Guaranteed demographic data | Overpromise; inference is estimation only |

---

## Traceability

| REQ-ID | Phase | Description |
|--------|-------|-------------|
| PARSE-01 | 1 | Archive Parsing |
| PARSE-02 | 1 | Archive Parsing |
| PARSE-03 | 1 | Archive Parsing |
| AUTH-01 | 1 | API Authentication |
| AUTH-02 | 1 | API Authentication |
| AUTH-03 | 1 | API Authentication |
| ENRICH-01 | 2 | Profile Enrichment (API) |
| ENRICH-02 | 2 | Profile Enrichment (API) |
| ENRICH-03 | 2 | Profile Enrichment (API) |
| ENRICH-04 | 2 | Profile Enrichment (API) |
| ENRICH-05 | 2 | Profile Enrichment (API) |
| SCRAPE-01 | 3 | Profile Enrichment (Scraping) |
| SCRAPE-02 | 3 | Profile Enrichment (Scraping) |
| SCRAPE-03 | 3 | Profile Enrichment (Scraping) |
| SCRAPE-04 | 3 | Profile Enrichment (Scraping) |
| SCRAPE-05 | 3 | Profile Enrichment (Scraping) |
| CLUSTER-01 | 4 | NLP Clustering |
| CLUSTER-02 | 4 | NLP Clustering |
| CLUSTER-03 | 4 | NLP Clustering |
| CLUSTER-04 | 4 | NLP Clustering |
| CLUSTER-05 | 4 | NLP Clustering |
| CLUSTER-06 | 4 | NLP Clustering |
| CLUSTER-07 | 4 | NLP Clustering |
| CLUSTER-08 | 4 | NLP Clustering |
| REVIEW-01 | 5 | Review Flow |
| REVIEW-02 | 5 | Review Flow |
| REVIEW-03 | 5 | Review Flow |
| REVIEW-04 | 5 | Review Flow |
| REVIEW-05 | 5 | Review Flow |
| REVIEW-06 | 5 | Review Flow |
| REVIEW-07 | 5 | Review Flow |
| LIST-01 | 6 | X API List Creation |
| LIST-02 | 6 | X API List Creation |
| LIST-03 | 6 | X API List Creation |
| LIST-04 | 6 | X API List Creation |
| LIST-05 | 6 | X API List Creation |
| EXPORT-01 | 6 | Data Export |
| EXPORT-02 | 6 | Data Export |

---
*Last updated: 2026-04-02 after requirements definition*
