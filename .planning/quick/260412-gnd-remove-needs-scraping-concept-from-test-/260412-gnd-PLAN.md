---
phase: quick
plan: 01
type: execute
wave: 1
depends_on: []
files_modified: [src/enrich/test_enrich.py]
autonomous: true
must_haves:
  truths:
    - "Script enriches first 5 uncached accounts"
    - "No needs_scraping logic in the codebase for this file"
    - "Output is simplified without scraping status"
  artifacts:
    - path: "src/enrich/test_enrich.py"
      provides: "Simplified enrichment test driver"
  key_links: []
---

<objective>
Remove the "needs_scraping" concept from test_enrich.py and simplify to just enrich the first 5 uncached accounts.

Purpose: Simplify the test driver by removing complexity that's no longer needed.
Output: Cleaner test_enrich.py that only handles uncached accounts.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/STATE.md

## Current State of test_enrich.py

The script currently has a two-tier priority system:
1. Uncached accounts (highest priority)
2. Cached accounts that "need scraping" (missing bio or location)

This needs_scraping concept adds complexity:
- Scans cached files to find incomplete data
- Tracks needs_scraping_ids and needs_scraping_reasons
- Prioritizes these in sample selection
- Displays "Needs Scraping" status in output

The simplification removes all of this and just enriches uncached accounts.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Remove needs_scraping logic and simplify to first 5 uncached</name>
  <files>src/enrich/test_enrich.py</files>
  <action>
Simplify the test_enrich.py script by removing all "needs_scraping" related logic:

1. **Remove from Step 4 (cache scanning):**
   - Delete the `needs_scaping_ids` set and `needs_scraping_reasons` dict
   - Delete the logic that checks cached files for `needs_scraping` flag
   - Keep only the logic that collects `cached_ids`

2. **Simplify Step 5 (account identification):**
   - Remove all output about "Need scraping" counts
   - Remove the "Cached accounts needing scraping" list
   - Simplify the "nothing to process" check to just check uncached_list

3. **Simplify Step 6 (sample selection):**
   - Remove the two-tier priority system
   - Just take the first 5 (or fewer) accounts from `uncached_list`
   - Remove `sample_info` dict since all samples are now just "UNCACHED"
   - Simplify the output to just list the selected account IDs

4. **Simplify print_enriched_profile function:**
   - Remove the `needs_scraping = user.get("needs_scraping", False)` line
   - Remove the "Needs Scraping:" output line from the formatted block

5. **Update docstring:**
   - Update the description to reflect simpler behavior (just enriches first 5 uncached)

Keep all other functionality intact: .env loading, OAuth 2.0 PKCE auth, following.js parsing, enrichment, error handling, and summary output.
  </action>
  <verify>
    <automated>.venv/bin/python -c "from src.enrich.test_enrich import print_enriched_profile, main; import inspect; src = inspect.getsource(print_enriched_profile); assert 'needs_scraping' not in src.lower(), 'needs_scraping still in print_enriched_profile'"</automated>
  </verify>
  <done>
    - test_enrich.py no longer contains any needs_scraping logic
    - Script simply enriches first 5 uncached accounts
    - Output is simplified without scraping status
    - Script still runs correctly for its intended purpose
  </done>
</task>

</tasks>

<verification>
- All needs_scraping references removed from code
- Script logic simplified to single priority tier
- print_enriched_profile() no longer displays Needs Scraping status
- Docstring updated to reflect simpler behavior
</verification>

<success_criteria>
Script enriched exactly 5 uncached accounts (or fewer if less than 5 uncached) with no needs_scraping prioritization logic remaining in the code.
</success_criteria>

<output>
After completion, create `.planning/quick/260412-gnd-remove-needs-scraping-concept-from-test-/260412-gnd-SUMMARY.md`
</output>