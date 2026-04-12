# X Following Organizer

## What This Is

A Python tool that reads the `following.js` file from an X data archive export, enriches each followed account with profile data from the X API and profile page scraping, clusters followers into semi-automated categorized lists, and creates those lists as native X API lists. The user reviews and approves clusters before they become lists, with an option to enable full automation after trust is established.

## Core Value

Transform a flat following list into organized, named X API lists that make it easy to reference and follow groups of similar people.

## Requirements

### Validated

- ✓ Parse `following.js` from X data archive export — Phase 1
- ✓ X API authentication setup (OAuth 2.0 PKCE via tweepy) — Phase 1, 7
- ✓ X API profile enrichment with caching, rate limiting, and error handling — Phase 2
- ✓ Profile page scraping for supplemental fields (curl_cffi + BeautifulSoup) — Phase 3
- ✓ Bio text embeddings via `sentence-transformers` (`all-MiniLM-L6-v2`) — Phase 4
- ✓ Semi-supervised K-Means clustering with seed anchoring — Phase 4
- ✓ HDBSCAN unsupervised clustering (no seeds required) — Phase 4
- ✓ LLM-generated cluster names (GPT-4o-mini / Claude Haiku / rule-based fallback) — Phase 4
- ✓ Interactive review CLI with approve/reject/rename/merge/split/defer — Phase 5
- ✓ Batch approve for high-quality clusters (size≥10, silhouette≥0.5) — Phase 5
- ✓ Automation mode offer after N approved rounds — Phase 5
- ✓ Native X API lists for approved clusters (5–50 members) — Phase 6
- ✓ Data export to Parquet (followers) and CSV (clusters) — Phase 6
- ✓ 3scrape pipeline (Link → Entity → Google) — Phase 8
- ✓ GLiNER entity extraction from bio + tweets — Phase 8
- ✓ Tweet embeddings for topical clustering (50 recent posts) — Phase 8

### Active

- [ ] **CACHE-01**: Enrichment reads tweets from cache, fetches only new tweets on miss
- [ ] **CACHE-02**: Tweets cached with accumulation across runs (dedupe by ID)
- [ ] **CACHE-03**: No limit on stored posts — cache grows over multiple invocations

### Out of Scope

- Real-time monitoring or notifications — one-time (or on-demand) run only
- Posting or interacting with lists — read/creation only
- Integrating with other social platforms — X only
- Auto-follow on list add — creeps users out; violates trust
- TF-IDF-only clustering — poor quality on short bios
- Bot/fake account detection — v2 candidate
- Account activity scoring — v2 candidate
- Network-based clustering — v2 candidate

## Context

- **Status:** v1.1 shipped (2026-04-12), v1.2 in progress
- **Tech stack:** Python, tweepy, sentence-transformers, scikit-learn, hdbscan, beautifulsoup4, curl_cffi, pandas, pyarrow, rich, questionary, gliner
- **Lines of code:** ~18,500 Python across ~105 files
- **X API credentials:** OAuth 2.0 PKCE configured
- **Input:** `data/following.js` from personal X data archive
- **Output:** Native X API lists (5–50 people), Parquet + CSV exports

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Semi-automated clustering | User wants review/approval before lists are created | ✅ Validated |
| NLP clustering (not keyword) | Transformer embeddings outperform TF-IDF on short bios | ✅ Validated |
| Rich profile data (API + scraping) | Maximize information for accurate clustering | ✅ Validated |
| X API lists as final output | User wants native X app lists, not a separate tool | ✅ Validated |
| 5-50 people per cluster/list | User-specified; X API hard limit is 5,000 but user prefers smaller lists | ✅ Validated |
| Private lists by default | User data is internal; public lists are noisy | ✅ Validated |
| OpenAI preferred over Anthropic | Checked first when both API keys present | ✅ Validated |
| Batch approve thresholds (size≥10, silhouette≥0.5) | High-quality clusters only for auto-approval | ✅ Validated |
| Exponential backoff base=1s, max=300s | Avoid hammering API on 429; 300s cap prevents runaway waits | ✅ Validated |
| OAuth 2.0 PKCE | Refresh tokens, higher rate limits, better security | ✅ Validated |
| 3scrape: Link → Entity → Google | Coldest accounts get external context first | ✅ Validated |
| HDBSCAN for clustering | Unsupervised, no seed accounts needed | ✅ Validated |
| Tweet cache accumulation | Fetch latest 50, merge with existing, dedupe by ID | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---

*Last updated: 2026-04-12 after v1.2 milestone started*