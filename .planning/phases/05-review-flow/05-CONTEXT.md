# Phase 5: Review Flow - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

User reviews, approves, and refines clusters before they become X API lists. Reads clustered data from `data/enrichment/*.json` (Phase 4 output: cluster_id, cluster_name, silhouette_score, central_member_usernames per account). Produces approved cluster registry for Phase 6 (list creation). Supports semi-automated iteration with full automation available after 2 approved rounds.

</domain>

<decisions>
## Implementation Decisions

### Interface Style
- **D-01:** Interactive CLI prompts — colorized output, tables, keyboard shortcuts
- **Rationale:** Fast iteration, low overhead, no browser dependency
- **Implementation:** Inquirer orQuestion library for rich CLI prompts; click or rich for formatted tables

### Cluster Presentation
- **D-02:** Table view (clusters as rows) — grouped by cluster name, shows top members + silhouette score per cluster
- **Rationale:** Most scannable — good for deciding approve/reject quickly at a glance
- **Layout:** Table with columns: Cluster Name | Members | Size | Silhouette | Status

### Review Flow
- **D-03:** "See all, then act" — all clusters shown in table first, user picks action by number
- **Rationale:** Fastest for power users — one action per cluster
- **Actions per cluster:** approve, reject, rename, merge, split, defer

### Per-Member Confidence
- **D-04:** Show silhouette/confidence per member (per-member assignment confidence), not just cluster-level
- **Rationale:** User can see WHY a member was grouped; transparency builds trust in the system
- **Display:** Each member row shows: username, bio snippet, confidence score

### Automation Threshold
- **D-05:** After 2 approved rounds, offer to enable full automation mode
- **Rationale:** Enough review data to trust the system without over-reviewing
- **Config:** Configurable N (default=2) via `REVIEW_AUTOMATION_ROUNDS` env var or config file

### Size Distribution Warning
- **D-06:** Present cluster size histogram before review begins; warn if heavily skewed to small clusters
- **Implementation:** Before table display, run `generate_size_histogram()` from Phase 4 and print summary

### Batch Approval
- **D-07:** Batch approve available for clusters with >N members and confident names (silhouette > threshold)
- **Threshold:** Configurable; default: 10+ members AND silhouette > 0.5

### Deferral
- **D-08:** Deferred clusters do not block approval of other clusters
- **Deferred clusters** are marked in the approval registry but excluded from Phase 6 list creation

### Merge/Split
- **D-09:** Merge combines two clusters into one (re-runs clustering on union); split moves selected members to a new cluster
- **Merge approach:** Re-assign all members of both clusters to a single new cluster using existing centroids
- **Split approach:** Move selected members out; they form a new cluster or join nearest existing

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 4 Artifacts
- `src/cluster/embed.py` — `cluster_all()`, `ClusterResult` dataclass (silhouette_by_cluster, size_histogram, central_members_by_cluster)
- `src/cluster/name.py` — `name_all_clusters()`, produces cluster names
- `config/seed_accounts.yaml` — seed categories (geographic, occupation, political_action, entertainment)
- `data/enrichment/{account_id}.json` — per-account cache with cluster_id, cluster_name, silhouette_score, is_seed_category, central_member_usernames

### Requirements
- `.planning/REQUIREMENTS.md` — REVIEW-01 through REVIEW-07

### Phase 5 ROADMAP Success Criteria
- Suggested clusters displayed grouped by category type with member previews and confidence scores
- User can approve, reject, rename, merge, split, or defer each cluster independently
- Batch approve available for clusters with >N members and confident names
- Cluster size distribution presented before review; warning if heavily skewed
- After 2 approved rounds, offer full automation mode
- Deferred clusters do not block others

</canonical_refs>

<codebase_context>
## Existing Code Insights

### Reusable Assets
- `ClusterResult` from `src/cluster/embed.py`: `total_accounts`, `n_clusters`, `labels`, `silhouette_by_cluster`, `size_histogram`, `central_members_by_cluster`
- `name_all_clusters()` from `src/cluster/name.py`: returns dict mapping cluster_id → cluster_name
- Enrichment cache schema: `data/enrichment/{account_id}.json` with cluster fields added by Phase 4

### Established Patterns
- Immediate caching to disk after each operation
- Error collection and continuation
- Result dataclass with counts returned to caller
- Dry-run mode for validation without live data
- Python CLI tool pattern (Phase 1-3 used argparse + module functions)

### Integration Points
- Input: `data/enrichment/*.json` files with cluster assignments (Phase 4 output)
- Output: Approval registry (approved clusters → Phase 6 list creation)
- Format: `data/clusters/approved.json` and `data/clusters/deferred.json`

</codebase_context>

<specifics>
## Specific Ideas

- 7 clusters expected (4 seed + 3 discovered)
- Silhouette score per member: derived from member's distance to cluster centroid vs distance to nearest other centroid
- Batch approve: skip individual review for clusters that are clearly good (large, high silhouette)
- Merge: union of two clusters re-clustered; new cluster gets new LLM-generated name
- Split: move selected members to nearest neighbor cluster or leave as "unclustered" for re-review

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 05-review-flow*
*Context gathered: 2026-04-05*
