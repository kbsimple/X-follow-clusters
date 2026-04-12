# Phase 8: 3scrape - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Scrape Enhancement — three post-processing capabilities on top of Phase 3 scraping:
1. **Entity extraction** (GLiNER) — extract ORG/LOC/JOB_TITLE from bio + pinned_tweet_text
2. **Google search fallback** — find external context for accounts with no bio AND no website
3. **Link extraction and following** — scrape about/biography pages from personal websites

Phase 8 operates as a post-processing step on existing `data/enrichment/{account_id}.json` cache files. It does not re-scrape X profile pages.

</domain>

<decisions>
## Implementation Decisions

### Entity Extraction (GLiNER)
- **D-01:** Entity types: **ORG (organization), LOC (location), JOB_TITLE (job title)**
- **D-02:** Run entity extraction on **both bio AND pinned_tweet_text**
- **D-03:** Run on **all bios regardless of length** (no minimum character threshold)
- **D-04:** Also run entity extraction on **external_bio** from link following (when available)
- **D-05:** Use `urchade/gliner_base-v2.1` — zero-shot NER model, CPU-friendly

### Google Search Fallback (SerpApi)
- **D-06:** Trigger only when account has **no bio AND no website** (coldest accounts only)
- **D-07:** Extract **title + snippet** from first Google result (not full result data)
- **D-08:** If `SERPAPI_KEY` env var is absent, skip Google search with a warning log (never block)
- **D-09:** Warn at 200 searches, fail gracefully at 250 (SerpApi free tier limit)

### Link Extraction and Following
- **D-10:** Trigger for accounts with **website set but bio empty** (or bio length < 10 chars)
- **D-11:** Fetch homepage **and** follow any "about" or "bio" links found on homepage
- **D-12:** Use **10s timeout** per external HTTP request, **30s max** per account
- **D-13:** **Skip LinkedIn links** — violates LinkedIn ToS and has aggressive anti-bot detection
- **D-14:** Store external bio in cache as **`external_bio`** field

### Execution Order
- **D-15:** Run in this order per account: **Link following → Entity extraction → Google search**
  - Link following produces `external_bio`
  - Entity extraction runs on bio + pinned_tweet + external_bio (if found)
  - Google search runs last, only for still-cold accounts (no bio, no website)

### Embedding Integration
- **D-16:** Entities added to embedding text as: `| Org: X | Loc: Y | Title: Z`
  - Format matches Phase 4 convention of ` | ` separated fields
  - Example: `AI researcher | Org: DeepMind | Loc: London | Title: Research Scientist`
- **D-17:** Entity extraction runs **before** `embed_accounts()` is called in Phase 4
- **D-18:** Entity fields cached in enrichment JSON alongside scraped fields

### Claude's Discretion
- Exact GLiNER threshold for entity confidence (default 0.5 — planner can tune)
- How to merge entity results when both bio and pinned_tweet produce entities
- Whether to cache GLiNER model in memory across accounts (performance optimization)
- Exact CSS selectors for finding "about" links on arbitrary websites

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 3-4 Artifacts
- `src/scrape/scraper.py` — XProfileScraper, existing TLS impersonation session (reused for link following)
- `src/scrape/parser.py` — parse_profile_fields(), existing field extraction patterns
- `src/scrape/__init__.py` — scrape_all(), ScrapeResult — Phase 8 follows same orchestrator pattern
- `src/cluster/embed.py` — get_text_for_embedding() — D-16 specifies entity format for embedding string
- `src/enrich/enrich.py` — EnrichmentResult pattern — Phase 8 should follow similar result dataclass

### Requirements
- `.planning/REQUIREMENTS.md` — SCRAPE-01 through SCRAPE-05 (Phase 3 requirements, for reference)

### Phase 8 Research
- `.planning/phases/08-3scrape/08-RESEARCH.md` — GLiNER, SerpApi, link extraction patterns

</canonical_refs>

<codebase_context>
## Existing Code Insights

### Reusable Assets
- `src/scrape/scraper.py`: `_session` (curl_cffi Session with impersonation) — reuse for external link following
- `src/scrape/scraper.py`: `_backoff` (ExponentialBackoff) — reuse for rate limiting
- `src/scrape/__init__.py`: `scrape_all()` — orchestrator pattern to replicate for Phase 8
- `src/scrape/parser.py`: `parse_profile_fields()` — field extraction patterns

### Established Patterns
- Immediate caching to disk after each operation
- Error collection and continuation (don't fail the whole batch on one account)
- Result dataclass with counts (ScrapeResult pattern)
- Graceful degradation when blocked (never fail hard on external dependencies)

### Integration Points
- Input: `data/enrichment/{account_id}.json` files (867 accounts, phases 2-3 data)
- Output: Same JSON files updated with entity fields, external_bio, google_search fields
- Next phase: Phase 4 `embed_accounts()` reads updated cache files with entity data in embedding string

</codebase_context>

<specifics>
## Specific Ideas

- 867 accounts in enrichment cache — Phase 8 adds entity extraction to all of them
- Execution order: Link following → Entity extraction → Google search (per account)
- SerpApi free tier (250 searches/month) is enough for one full run of 867 accounts
- GLiNER Base v2.1 (~110M params, CPU-friendly) — no GPU required

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 08-3scrape*
*Context gathered: 2026-04-11*