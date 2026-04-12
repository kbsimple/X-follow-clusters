---
phase: 08-3scrape
plan: 03
subsystem: src/scrape/google_lookup.py
tags: [serpapi, google-search, cold-start, entity-extraction]

dependency_graph:
  requires: []
  provides:
    - GoogleLookupResult dataclass
    - google_lookup_account() function
    - _perform_google_search() helper
  affects:
    - src/scrape/google_lookup.py

tech_stack:
  added:
    - serpapi (SerpApi Google search client)
  patterns:
    - SerpApi-based external account lookup
    - Search count tracking with warning/fail thresholds

key_files:
  created:
    - path: src/scrape/google_lookup.py
      description: Google search lookup module for cold-start X accounts
  modified: []

patterns-established:
  - "Google search runs only when no bio AND no website (D-06)"
  - "SERPAPI_KEY absence causes warning log, not error (D-08)"
  - "Search count tracked; warn at 200, fail at 250 (D-09)"

requirements-completed: []

metrics:
  duration: "~5 min"
  completed: "2026-04-11"
---

# Phase 08-3scrape Plan 03 Summary

## One-Liner

SerpApi-based Google search lookup for coldest X accounts (no bio AND no website), extracting title + snippet only with free-tier quota tracking.

## Completed Tasks

| # | Task | Commit | Verification |
|---|------|--------|--------------|
| 1 | Create src/scrape/google_lookup.py | 0766bc2 | `python -c "from src.scrape.google_lookup import google_lookup_account, GoogleLookupResult"` |

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| SerpApi for Google search | Provides structured results without scraping Google directly |
| Trigger only when no bio AND no website | Targets coldest accounts where X profile provides zero signal |
| Extract title + snippet only | Minimal external data per D-07 |
| Warn at 200, fail at 250 | Free tier limit is 250 searches/month |
| SERPAPI_KEY absent = warning not error | Never blocks pipeline; degrades gracefully |

## GoogleLookupResult Dataclass

```python
@dataclass
class GoogleLookupResult:
    username: str
    result_title: str | None
    result_snippet: str | None
    search_count: int  # total searches in session
```

## Functions Added

| Function | Purpose |
|----------|---------|
| `google_lookup_account()` | Main entry point; checks D-06 gate, performs search, caches results |
| `_perform_google_search()` | SerpApi client call; extracts title+snippet from first organic result |

## Must-Have Truths Verified

| Truth | Status |
|-------|--------|
| Google search runs only when no bio AND no website | PASS (D-06 gate in google_lookup_account) |
| Google search extracts title + snippet only | PASS (_perform_google_search extracts only title+snippet) |
| SERPAPI_KEY absence causes graceful skip with warning | PASS (warning log, returns None) |
| Search count tracked; warns at 200, fails at 250 | PASS (_session_search_count + _WARN_AT/_FAIL_AT) |
| Results cached to data/enrichment/{username}.json | PASS (writes google_result_title, google_result_snippet) |

## Threat Flags

None — SERPAPI_KEY stays in env var only, not written to cache or logs.

## Deviations from Plan

None — plan executed exactly as written.

## Next Steps

- Plan 08-04 integrates this into the scrape_all() orchestrator
- Plan 08-05 updates get_text_for_embedding() to include entity fields
- Plan 08-06 adds tests
