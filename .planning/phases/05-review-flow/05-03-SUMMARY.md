---
phase: 05-review-flow
plan: '03'
subsystem: review
tags: [actions, merge, split, automation, questionary, review-loop]

# Dependency graph
requires:
  - phase: '04'
    provides: "Cluster assignments in data/enrichment/*.json with cluster_id, cluster_name, silhouette_score; compute_clusters(), generate_size_histogram()"
  - phase: '05'
    provides: "src/review/registry.py ApprovalRegistry, load_registry(), save_registry(), AUTOMATION_ROUNDS; src/review/metrics.py compute_member_confidences(), get_cluster_member_details(); src/review/table.py display_cluster_table(), display_member_details(); src/review/batch.py get_batch_approvable_clusters(), confirm_batch_approve(), apply_batch_approve()"
provides:
  - "Per-cluster action handlers: approve, reject, rename, merge, split, defer"
  - "Merge/split cluster operations with cache file updates"
  - "Automation mode offer after AUTOMATION_ROUNDS completed"
  - "Complete review CLI loop end-to-end"
affects:
  - "06-list-creation"

# Tech tracking
tech-stack:
  added: [questionary]
  patterns:
    - "Per-cluster action dispatch via questionary.select()"
    - "Merge via re-clustering union with k=1"
    - "Split via nearest-neighbor centroid reassignment"
    - "Automation offer wired into main review loop"

key-files:
  created:
    - "src/review/actions.py"
    - "src/review/merge_split.py"
    - "src/review/automation.py"
  modified:
    - "src/review/cli.py"

key-decisions:
  - "questionary 2.x checkbox used for multi-select split operation"
  - "Merge re-clusters with empty seed (k=1) forcing single cluster outcome"
  - "Split moves members to nearest neighbor centroid (excluding source cluster)"
  - "Automation offer presented once per session via automation_offered flag"

patterns-established:
  - "Pattern: Action handler returning (updated_registry, cluster_changed) tuple"
  - "Pattern: Merge updates all member cache files with new cluster_id/cluster_name atomically"
  - "Pattern: Split refreshes cluster data in main loop after cache file changes"

requirements-completed: [REVIEW-03, REVIEW-05, REVIEW-07]

# Metrics
duration: <1min
completed: 2026-04-06
---

# Phase 05 Plan 03: Per-Cluster Actions, Merge/Split, and Automation Offer Summary

**Per-cluster action handlers, merge/split operations, and full automation mode offer wired into the review CLI loop**

## Performance

- **Duration:** < 1 min
- **Started:** 2026-04-06T00:40:52Z
- **Completed:** 2026-04-06T00:41:xxZ
- **Tasks:** 3 (3 tasks)
- **Files created/modified:** 4

## Accomplishments

- Per-cluster actions: approve, reject, rename, merge, split, defer, see members
- Merge: union of two clusters re-clustered with k=1, LLM naming, all cache files updated
- Split: multi-select members via questionary checkbox, nearest-neighbor reassignment
- Automation offer presented after AUTOMATION_ROUNDS (default=2) completed
- Full CLI review loop: histogram -> batch approve -> automation offer -> per-cluster review -> summary

## Task Commits

Each task was committed atomically:

1. **Task 1: Per-cluster action handlers** - `02f581f` (feat)
2. **Task 2: Merge and split cluster operations** - `8ec58d9` (feat)
3. **Task 3: Automation mode offer and review loop** - `38ce23c` (feat)

## Files Created/Modified

- `src/review/actions.py` - handle_cluster_action() dispatching to 6 actions, registry saved after each
- `src/review/merge_split.py` - merge_clusters() with k=1 re-clustering, split_cluster() with nearest-neighbor
- `src/review/automation.py` - should_offer_automation(), offer_automation_mode(), is_automation_enabled()
- `src/review/cli.py` - main() fully wired with all review flow components

## Decisions Made

- questionary 2.x checkbox for multi-select split operation
- Merge re-clusters union with k=1 (empty seed dict = no anchor guidance)
- Split moves to nearest centroid excluding source cluster
- Automation_offered flag ensures offer appears once per session

## Deviations from Plan

**None** - plan executed exactly as written.

## Issues Encountered

- No enrichment data exists yet (Phase 4 not run) - modules are implemented correctly but will raise RuntimeError at runtime when data is missing

## Next Phase Readiness

- Phase 06: list creation reads automation_enabled from registry to potentially skip review
- Phase 06: reads approved clusters from data/clusters/approved.json

## Self-Check: PASSED

All 3 commits verified in git history. All 4 key files exist on disk:
- src/review/actions.py, src/review/merge_split.py, src/review/automation.py, src/review/cli.py
- Automation logic verified: should_offer_automation() returns False when rounds < 2 and when already offered

---
*Phase: 05-review-flow*
*Completed: 2026-04-06*