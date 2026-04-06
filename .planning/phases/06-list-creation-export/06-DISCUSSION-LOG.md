# Phase 6: List Creation + Export - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-06
**Phase:** 06-list-creation-export
**Areas discussed:** Dry-run strategy, Conflict handling, Export format, Export scope

---

## Dry-run Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Dry-run first, then real | Simulate without API calls; show what WOULD happen | ✓ |
| Real only (small test first) | Go straight to live, start with one cluster | |
| Limited real-run first | Start real but cap at 1-2 lists | |

**User's choice:** Dry-run first, then real
**Notes:** User wants to see names + member counts only in dry-run. No full mock API simulation needed.

---

## Conflict Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-rename with numeric suffix | Append -1, -2, etc. automatically | |
| Skip and continue | Silently skip conflicting list, move on | |
| Prompt user | Ask: rename, skip, or abort | ✓ |

**User's choice:** Prompt user
**Notes:** User wants control over naming conflicts rather than silent auto-resolution.

---

## Export Format (Follower Records)

| Option | Description | Selected |
|--------|-------------|----------|
| Parquet (Recommended) | Apache Parquet — columnar, fast analytics with pandas/duckdb | ✓ |
| CSV only | Simple universal format | |

**User's choice:** Parquet (Recommended)
**Notes:** Better for downstream analysis.

---

## Dry-run Output Verbosity

| Option | Description | Selected |
|--------|-------------|----------|
| Show names + counts only | Fast, scannable summary | ✓ |
| Full mock API simulation | Simulate every API call with mock responses | |

**User's choice:** Show names + counts only
**Notes:** Simpler is better for dry-run. Mock API simulation is overkill.

---

## Export Scope (Deferred Clusters)

| Option | Description | Selected |
|--------|-------------|----------|
| Export deferred clusters too | Preserve data for later even without X API list | ✓ |
| Approved only | Only clusters with X API lists | |

**User's choice:** Export deferred clusters too
**Notes:** Deferred decisions are worth preserving in export.

---

## Deferred Ideas

None — discussion stayed within phase scope.
