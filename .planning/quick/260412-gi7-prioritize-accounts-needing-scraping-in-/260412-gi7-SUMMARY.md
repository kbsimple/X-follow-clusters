---
phase: quick
plan: 01
subsystem: enrichment
tags: [scraping, prioritization, test-driver]
requires: []
provides: [scraping-prioritization-in-test-enrich]
affects: [src/enrich/test_enrich.py]
tech_stack:
  added: []
  patterns: [priority-queue, status-tracking]
key_files:
  created: []
  modified:
    - path: src/enrich/test_enrich.py
      changes: Added needs_scraping identification and prioritization logic
decisions:
  - Prioritize uncached accounts first, then needs_scraping accounts
  - Store reason for each needs_scraping account (missing bio, location, or both)
metrics:
  duration: 5 minutes
  completed_date: 2026-04-12
---

# Quick Task 260412-gi7: Prioritize Accounts Needing Scraping in test_enrich.py Summary

## One-liner

Enhanced test_enrich.py to identify and prioritize cached accounts with `needs_scraping=true` during sample selection.

## Changes Made

### Task 1: Add scraping-needs identification and prioritization

Modified `src/enrich/test_enrich.py` to:

1. **Step 4 (cache scanning):** Added `needs_scraping_ids` set and `needs_scraping_reasons` dict to track accounts that need scraping. For each cached JSON file, check the `needs_scraping` flag and determine the reason (missing bio, missing location, or both).

2. **Step 5 (identifying accounts):** Added output showing cached accounts needing scraping with their specific reasons.

3. **Step 6 (sample selection):** Changed sample selection logic to prioritize:
   - First: uncached accounts (have no cache file)
   - Second: cached accounts with `needs_scraping=true`
   - Third (defensive): other cached accounts

4. **Sample output:** Shows which accounts need scraping and the specific reason (e.g., "NEEDS SCRAPING (missing bio)").

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- Syntax check passed: `.venv/bin/python -m py_compile src/enrich/test_enrich.py`
- Commit created: `0b83abc`

## Files Changed

| File | Change |
|------|--------|
| `src/enrich/test_enrich.py` | +65 lines, -25 lines |

## Commit

- `0b83abc`: feat(260412-gi7): prioritize accounts needing scraping in test_enrich.py

## Self-Check: PASSED

- FOUND: src/enrich/test_enrich.py
- FOUND: 0b83abc