---
phase: quick
plan: 260412-gnd
type: cleanup
tags: [refactor, simplification, test-driver]
files_modified: [src/enrich/test_enrich.py]
duration: ~5 minutes
completed_date: "2026-04-12"
---

# Quick Task 260412-gnd: Remove needs_scraping Concept from test_enrich.py

## Summary

Removed the "needs_scraping" two-tier priority system from test_enrich.py, simplifying the script to only enrich the first 5 uncached accounts.

## Changes Made

### src/enrich/test_enrich.py

**Removed:**
- `needs_scraping_ids` set and `needs_scraping_reasons` dict from Step 4 (cache scanning)
- Logic that parsed cached files to detect `needs_scraping` flag
- Output about "Need scraping" counts in Step 5
- Two-tier priority system in Step 6 (uncached -> needs_scraping)
- `sample_info` dict tracking status per account
- `needs_scraping` field from `print_enriched_profile()` function
- Unused `json` import

**Simplified:**
- Step 4: Now only collects `cached_ids`, no content parsing
- Step 5: Now only identifies uncached accounts
- Step 6: Now simply takes first 5 uncached accounts

## Verification

- Confirmed no `needs_scraping` references remain in the file
- Verified `print_enriched_profile()` no longer contains needs_scraping logic

## Commit

- `7de0dec`: refactor(260412-gnd): remove needs_scraping logic from test_enrich.py

## Deviations

None - plan executed exactly as written.

## Result

The test_enrich.py script is now simpler and focused solely on enriching uncached accounts. Lines reduced from 255 to 194 (61 lines removed).