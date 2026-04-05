---
phase: 04-nlp-clustering
plan: "02"
subsystem: clustering
tags: [openai, anthropic, llm, cluster-naming, gpt-4o-mini, claude-haiku]

# Dependency graph
requires:
  - phase: "04-01"
    provides: "Cluster assignments (cluster_id) and central_member_usernames per account in data/enrichment/*.json"
provides:
  - "src/cluster/name.py — LLM cluster naming with OpenAI/Anthropic/fallback"
  - "cluster_name field written to all enrichment cache files"
affects:
  - "05-create-lists (reads cluster_name from cache for list creation)"

# Tech tracking
tech-stack:
  added:
    - openai>=1.50.0
    - anthropic>=0.40.0
  patterns:
    - "LLM provider auto-detection on module import (OPENAI_API_KEY vs ANTHROPIC_API_KEY)"
    - "Keyword-group fallback naming when no API credentials available"
    - "dry_run mode for pipeline validation without live data"

key-files:
  created:
    - "src/cluster/name.py"
  modified:
    - "src/cluster/__init__.py"

key-decisions:
  - "Provider preference: OPENAI_API_KEY checked first, then ANTHROPIC_API_KEY, then rule_based"
  - "Rule-based fallback detects 8 keyword groups: Tech & AI, Venture & Finance, Science & Research, Politics & Policy, Media & Journalism, Arts & Entertainment, Sports & Fitness, Health & Medicine"
  - "Location detection for Bay Area, NYC, London, LA, DC with Interest Group suffix"

patterns-established:
  - "Cache-first bio loading with graceful missing-file handling"
  - "Cluster naming via central_member_usernames (top 5 by silhouette closeness)"

requirements-completed: [CLUSTER-04]

# Metrics
duration: 3min
completed: 2026-04-05
---

# Phase 04 Plan 02: LLM-Generated Cluster Naming

**LLM cluster naming with OpenAI GPT-4o-mini or Anthropic Claude Haiku, with keyword-based fallback when no API credentials are present**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-05T22:05:00Z
- **Completed:** 2026-04-05T22:08:44Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Created src/cluster/name.py with name_cluster, rule_based_name, name_all_clusters
- name_cluster auto-selects OpenAI GPT-4o-mini or Anthropic Claude Haiku based on env vars
- Falls back to rule_based_name (8 keyword groups + location detection) when no API keys set
- name_all_clusters handles missing data/enrichment gracefully via dry_run mode
- Updated src/cluster/__init__.py to export all name functions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create name.py with LLM cluster naming** - `7d49663` (feat)
2. **Task 2: Verify naming functions and dry_run** - `7d49663` (test, same commit as Task 1)

## Files Created/Modified
- `src/cluster/name.py` - LLM naming with OpenAI/Anthropic + rule-based fallback (~250 lines)
- `src/cluster/__init__.py` - Added exports for name_all_clusters, name_cluster, rule_based_name

## Decisions Made
- OpenAI preferred over Anthropic when both API keys present (checked first)
- GPT-4o-mini (temperature=0.3, max_tokens=32) and Claude Haiku (max_tokens=32) for cost efficiency
- Rule-based fallback requires 2+ keyword matches before using a named group

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- data/enrichment/ does not exist yet (runtime data from enrichment phase) — handled via dry_run=True mode in name_all_clusters which returns {} and logs warning gracefully

## User Setup Required

None - no external service configuration required for this plan.

## Next Phase Readiness
- Phase 05 (create-lists) can read cluster_name from data/enrichment/*.json once enrichment and clustering phases complete
- OpenAI or Anthropic API key can be added to .env when ready for LLM naming

---
*Phase: 04-nlp-clustering*
*Completed: 2026-04-05*
