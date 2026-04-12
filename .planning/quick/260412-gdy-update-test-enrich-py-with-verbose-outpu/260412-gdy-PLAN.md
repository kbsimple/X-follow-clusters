---
phase: 260412-gdy
plan: 01
type: execute
wave: 1
depends_on: []
files_modified: [src/enrich/test_enrich.py]
autonomous: true
requirements: []
user_setup: []

must_haves:
  truths:
    - "User sees account IDs and their cache status before enrichment"
    - "User sees which API fields are being requested during enrichment"
    - "User sees full enriched profile data after each account is processed"
  artifacts:
    - path: "src/enrich/test_enrich.py"
      provides: "Verbose enrichment test driver"
      min_lines: 160
  key_links:
    - from: "src/enrich/test_enrich.py"
      to: "src/enrich/api_client.py"
      via: "USER_FIELDS import"
      pattern: "from src.enrich.api_client import.*USER_FIELDS"
---

<objective>
Update test_enrich.py with verbose output to show detailed progress during enrichment pipeline execution.

Purpose: Enable visibility into what data exists for each account, what fields are being requested from the API, and what enriched data is returned.
Output: Modified test_enrich.py with three-stage verbose output.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@src/enrich/test_enrich.py
@src/enrich/api_client.py

<interfaces>
From src/enrich/api_client.py:
```python
USER_FIELDS = [
    "description",      # bio text
    "location",         # user-defined location
    "public_metrics",    # followers_count, following_count, tweet_count, listed_count
    "verified",         # verified status
    "protected",         # protected status
    "pinned_tweet_id",  # pinned tweet ID (text requires separate call)
]
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add verbose output to test_enrich.py</name>
  <files>src/enrich/test_enrich.py</files>
  <action>
Modify src/enrich/test_enrich.py to add verbose output at three stages:

1. **Before enrichment (Step 6 area):** For each account ID in the sample, check if a cache file exists and print its current data. Show:
   - Account ID
   - Whether cached or not
   - If cached: show existing fields from the JSON file (username, name, has_bio, has_location, needs_scraping)

2. **During enrichment (Step 7 area):** Before calling get_users(), print the USER_FIELDS being requested:
   - Import USER_FIELDS from api_client
   - Print "Requesting fields: [list of fields]"

3. **After enrichment (inside the response processing loop):** For each enriched user, display the full profile data in a formatted block:
   - ID, Username, Name
   - Bio (description) - truncate to 100 chars if longer
   - Location
   - Metrics: followers_count, following_count, tweet_count, listed_count
   - Verified status
   - Protected status
   - needs_scraping flag

Add helper function `print_enriched_profile(user: dict)` to format the output nicely with indentation.
  </action>
  <verify>
    <automated>.venv/bin/python -c "from src.enrich.test_enrich import print_enriched_profile; print('import ok')"</automated>
  </verify>
  <done>
test_enrich.py includes:
- USER_FIELDS import from api_client
- print_enriched_profile() helper function
- Verbose output before enrichment showing cache status for each account
- Verbose output during enrichment showing requested fields
- Verbose output after enrichment showing full profile data
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Script execution | Local development tool, no external input |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | I | test_enrich.py | accept | Local dev script, no external input handling needed |
</threat_model>

<verification>
- Script runs without import errors
- Verbose output appears at all three stages
- Profile data is formatted and readable
</verification>

<success_criteria>
- USER_FIELDS imported and displayed before API call
- Each account shows cache status before enrichment
- Each enriched account displays full profile details after enrichment
- needs_scraping flag visible in output
</success_criteria>

<output>
After completion, create `.planning/quick/260412-gdy-update-test-enrich-py-with-verbose-outpu/260412-gdy-SUMMARY.md`
</output>