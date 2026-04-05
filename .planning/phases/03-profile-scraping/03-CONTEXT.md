# Phase 3: Profile Scraping - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Supplemental profile page scraping for fields the X API does not provide. Scrape professional_category, pinned tweet text, and any additional available fields for accounts flagged with `needs_scraping: true` from Phase 2.

</domain>

<decisions>
## Implementation Decisions

### Scraping Library
- **D-01:** Use `curl_cffi` for TLS impersonation (JA3 fingerprint evasion)
- **Rationale:** Most reliable approach for X — avoids fingerprinting blocks

### robots.txt Policy
- **D-02:** Honor rate-limiting rules (Crawl-delay) only; ignore per-path disallows for user profiles
- **Rationale:** User profiles are public; rate-limiting is sufficient

### Target Fields
- **D-03:** Scrape all available fields beyond what Phase 2 API provided
- **Priority targets:** professional_category, pinned tweet text, profile banner, website URL, any other accessible fields
- **Rationale:** Comprehensive enrichment improves clustering quality

### Integration
- **D-04:** Read `needs_scraping: true` accounts from Phase 2 enrichment cache
- **D-05:** Update existing `data/enrichment/{account_id}.json` files with scraped fields
- **D-06:** Skip accounts already cached with all fields populated

### Claude's Discretion
- Specific X profile page URL structure and CSS selectors
- Exact delay timing (2-5s with jitter — specific values TBD by planner)
- How to detect scraping blocks and fallback gracefully

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 2 Artifacts
- `src/enrich/enrich.py` — enrich_all(), reads needs_scraping flags
- `src/enrich/api_client.py` — XEnrichmentClient, cache structure
- `data/enrichment/{account_id}.json` — per-account enrichment cache

### Requirements
- `.planning/REQUIREMENTS.md` — SCRAPE-01 through SCRAPE-05

</canonical_refs>

<codebase_context>
## Existing Code Insights

### Reusable Assets
- `src/enrich/enrich.py`: Phase 2 orchestrator — reads `needs_scraping` flags from cache
- `data/enrichment/`: Per-account JSON files from Phase 2

### Established Patterns
- Immediate caching to disk after each operation
- Error collection and continuation (from Phase 2)
- Exponential backoff with jitter (Phase 2 rate limiter available for reuse)

### Integration Points
- Input: `data/enrichment/{account_id}.json` files with `needs_scraping: true`
- Output: Updated `data/enrichment/{account_id}.json` with scraped fields added

</codebase_context>

<specifics>
## Specific Ideas

- Phase 2 flagged accounts with `needs_scraping: true` in enrichment cache
- 867 total accounts, subset need scraping
- TLS impersonation via curl_cffi required (Phase 2 research confirmed standard requests会被block)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-profile-scraping*
*Context gathered: 2026-04-05*
