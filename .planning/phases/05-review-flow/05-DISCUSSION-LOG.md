# Phase 5: Review Flow - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-05
**Phase:** 05-review-flow
**Areas discussed:** Interface style, Cluster presentation, Review flow, Confidence transparency, Automation threshold

---

## Interface Style

| Option | Description | Selected |
|--------|-------------|----------|
| Interactive CLI prompts | One prompt per cluster with colorized output, tables, and keyboard shortcuts. Fast iteration, low overhead. | ✓ |
| Local web UI (TUI) | Start a local web server (http://localhost:PORT), show clusters in browser. Richer display, more complexity. | |
| Line-by-line print + select | Print all clusters to terminal, let user pick actions by number. Simplest to build, least polished. | |

**User's choice:** Interactive CLI prompts
**Notes:** Fast iteration, low overhead — no browser dependency. Use Inquirer or click library.

---

## Cluster Presentation

| Option | Description | Selected |
|--------|-------------|----------|
| Table: clusters as rows | Grouped by cluster name, show top members + silhouette score. Most scannable — good for deciding approve/reject quickly. | ✓ |
| Collapsed list → expand | See cluster name first, hit Enter to see members. Good for dense clusters, less scrolling. | |
| One cluster per screen | Show one cluster at a time in full detail, arrow keys to navigate. Highest engagement, slowest to browse many clusters. | |

**User's choice:** Table: clusters as rows
**Notes:** Table with columns: Cluster Name | Members | Size | Silhouette | Status. Most scannable for quick approve/reject decisions.

---

## Review Flow

| Option | Description | Selected |
|--------|-------------|----------|
| See all, then act | Show all clusters in table, let user pick action by number. Fastest for power users, one action per cluster. | ✓ |
| Table → pick to review | Table shows all clusters; user picks a number to see detail, then approve/reject. Middle ground — can browse quickly. | |
| Sequential walkthrough | One cluster per screen with member preview. Maximum context per decision, slowest pacing. | |

**User's choice:** See all, then act
**Notes:** All clusters shown in table first, user picks action by number. Actions per cluster: approve, reject, rename, merge, split, defer.

---

## Confidence Transparency

| Option | Description | Selected |
|--------|-------------|----------|
| Show per-member scores | Show silhouette score per cluster + per-member confidence. Most transparency — user can see WHY a member was grouped. | ✓ |
| Cluster-level only | Show cluster silhouette only (overall quality metric). Simpler display, less data to parse. | |
| Hide all scores | No scores shown — just cluster name and members. Cleanest, but user has no quality signal. | |

**User's choice:** Show per-member scores
**Notes:** Each member row shows: username, bio snippet, confidence score. Silhouette per member derived from member's distance to centroid vs nearest other centroid.

---

## Automation Threshold

| Option | Description | Selected |
|--------|-------------|----------|
| 1 round (immediate) | After 1 approved round, offer full automation. Fastest path to auto, but less review data. | |
| 2 rounds (recommended) | After 2 rounds, enough data to trust. Balanced — gives user 2 chances to correct the system. | ✓ |
| 3 rounds (thorough) | After 3 rounds. Conservative — most review rounds before trusting auto. | |

**User's choice:** 2 rounds (recommended)
**Notes:** Configurable via `REVIEW_AUTOMATION_ROUNDS` env var or config file. After 2 approved rounds, prompt offers to enable full automation mode.

---

## Claude's Discretion

The following were left to the planner's judgment:
- Exact CLI library choice (Inquirer vs click vs rich)
- Per-member confidence score derivation (exact formula from distances)
- Merge: whether to re-run LLM naming or keep combined name
- Split: exact UI for selecting which members to move

---

*Phase: 05-review-flow*
*Discussion date: 2026-04-05*
