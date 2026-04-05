# Phase 03 Plan 01: Profile Scraping Summary

**Plan:** 03-01
**Phase:** 03-profile-scraping
**Status:** COMPLETE
**Completed:** 2026-04-05

## One-liner

curl_cffi-based X profile scraper with BeautifulSoup field extraction, robots.txt compliance, and graceful block handling for supplemental profile enrichment.

## Objective

Build the complete Phase 3 profile scraping system: curl_cffi-based scraper, BeautifulSoup field parser, robots.txt compliance, and graceful block handling. All five SCRAPE requirements are addressed.

## Tasks Executed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Create src/scrape/ module with XProfileScraper and field parser | 2560dcd | src/scrape/__init__.py, src/scrape/scraper.py, src/scrape/parser.py |
| 2 | Create CLI entry point and scrape_all() orchestrator + tests | 0f4afee | src/scrape/__main__.py, tests/scrape/__init__.py, tests/scrape/test_scraper.py |

## Key Decisions Made

| Decision | Rationale |
|----------|-----------|
| curl_cffi for all HTTP requests | Phase 2 research confirmed vanilla requests gets immediately blocked by TLS fingerprinting |
| Reuse ExponentialBackoff from Phase 2 | Already implemented; handles jitter correctly per Phase 3 research |
| Graceful degradation (return None) rather than raising | SCRAPE-05 requires continuing with API-only data when blocked |
| __NEXT_DATA__ JSON fallback for professional_category | Selector not publicly documented; JSON navigation is reliable when available |

## Requirements Addressed

| ID | Description | Status |
|----|-------------|--------|
| SCRAPE-01 | Supplemental profile page scraping for fields API doesn't expose | DONE — XProfileScraper with curl_cffi |
| SCRAPE-02 | TLS impersonation via curl_cffi to avoid fingerprinting blocks | DONE — `impersonate="chrome"` session |
| SCRAPE-03 | Random delays (2–5s with jitter) between scraping requests | DONE — `random.uniform` + jitter in `_apply_delay()` |
| SCRAPE-04 | Check robots.txt; document fields and legal basis | DONE — `RobotFileParser` in `__init__` + `ROBOTS_TXT_LEGAL` string |
| SCRAPE-05 | Graceful degradation when scraping blocked | DONE — `scrape_profile()` returns None on block/error |

## Architecture

```
src/scrape/
├── __init__.py      # scrape_all() orchestrator + ScrapeResult dataclass + ROBOTS_TXT_LEGAL
├── scraper.py       # XProfileScraper class, BlockDetectedError, ScrapeError
├── parser.py        # parse_profile_fields(), extract_*() functions
└── __main__.py      # CLI: python -m src.scrape

tests/scrape/
├── __init__.py
└── test_scraper.py  # 5 tests: init, parser, block detection
```

## Key Files

| Path | Purpose |
|------|---------|
| `src/scrape/scraper.py` | XProfileScraper: curl_cffi session, `is_blocked()`, `scrape_profile()`, `_cache_scraped_fields()`, `_apply_delay()` |
| `src/scrape/parser.py` | `parse_profile_fields()`: 7-field extraction; 3-strategy professional_category |
| `src/scrape/__init__.py` | `scrape_all()` orchestrator, `ScrapeResult`, `ROBOTS_TXT_LEGAL` |
| `src/scrape/__main__.py` | CLI with `--input`, `--output`, `--min-delay`, `--max-delay` |

## Extraction Fields (7 total)

1. **bio** — `div[data-testid="UserDescription"]`
2. **location** — `span[data-testid="UserLocation"]`
3. **website** — `a[data-testid="UserUrl"]` (href attribute)
4. **join_date** — `span[data-testid="UserJoinDate"]`
5. **professional_category** — 3 strategies: `data-testid`, `__NEXT_DATA__` JSON, span scan
6. **pinned_tweet_text** — first `article[data-testid="tweet"]` text
7. **profile_banner_url** — `img[alt="Profile banner"]` src attribute

## Block Detection Patterns

Response is considered blocked when:
- HTTP 429 (rate limited)
- HTTP 200 with empty body
- HTTP 200 with `challenges` in redirect URL
- HTTP 200 without `<title>` tag

## CLI Usage

```bash
python -m src.scrape --input data/enrichment --output data/enrichment --min-delay 2.0 --max-delay 5.0
```

## Integration Points

- **Input:** `data/enrichment/{account_id}.json` with `needs_scraping: True` (from Phase 2)
- **Output:** Same JSON files updated with scraped fields added
- **Reuse:** `ExponentialBackoff` from `src.enrich.rate_limiter`
- **Skips:** accounts with `needs_scraping: False` or already have `professional_category`

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

- [x] `src/scrape/scraper.py` exists with XProfileScraper class, is_blocked(), scrape_profile()
- [x] `src/scrape/parser.py` exists with parse_profile_fields(), extract_professional_category(), extract_pinned_tweet(), extract_banner()
- [x] `src/scrape/__init__.py` exports scrape_all() and ScrapeResult
- [x] `src/scrape/__main__.py` CLI works: `python -m src.scrape --help`
- [x] ROBOTS_TXT_LEGAL constant exists in __init__.py
- [x] tests/scrape/test_scraper.py exists with 5 tests
- [x] SCRAPE-01: `curl_cffi` grep finds matches
- [x] SCRAPE-02: `impersonate` grep finds `impersonate="chrome"`
- [x] SCRAPE-03: `random.uniform` grep finds 2 occurrences
- [x] SCRAPE-04: `RobotFileParser` grep finds match
- [x] SCRAPE-05: `return None` grep finds 4 occurrences (blocked/error paths)

## Metrics

| Metric | Value |
|--------|-------|
| Duration | ~2 minutes |
| Tasks completed | 2/2 |
| Files created | 6 |
| Commits | 2 |
| Python files | 4 (syntax verified) |
