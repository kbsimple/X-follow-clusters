# Phase 5: Review Flow - Research

**Researched:** 2026-04-05
**Domain:** Interactive CLI review interface, per-member clustering confidence, approval state management
**Confidence:** HIGH (library capabilities verified via web search; clustering math from sklearn docs)

## Summary

Phase 5 implements an interactive CLI where users review, approve, and refine NLP-generated clusters before they become X API lists. The phase reads cluster assignments from `data/enrichment/*.json` (Phase 4 output), presents clusters in a formatted table with per-member confidence scores, and produces an approval registry for Phase 6. Key technical decisions: (1) Rich + Questionary for the CLI layer, (2) existing `sklearn.metrics.silhouette_samples` for per-member confidence, (3) merge via re-clustering union of members, (4) JSON-based approval registry with round-tracking.

**Primary recommendation:** Use `rich` for table rendering and `questionary` for prompts; compute per-member silhouette scores from existing embeddings; implement merge/split via the existing `compute_clusters()` pipeline; track rounds in the approval registry JSON.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Interactive CLI prompts via Inquirer or Questionary library (colorized, tables, keyboard shortcuts)
- **D-02:** Table view with columns: Cluster Name | Members | Size | Silhouette | Status
- **D-03:** "See all, then act" -- all clusters shown in table first, user picks action by number
- **D-04:** Per-member silhouette/confidence displayed with username and bio snippet
- **D-05:** After 2 approved rounds, offer full automation mode (configurable via `REVIEW_AUTOMATION_ROUNDS`)
- **D-06:** Present cluster size histogram before review; warn if heavily skewed
- **D-07:** Batch approve for >10 members AND silhouette > 0.5 (configurable threshold)
- **D-08:** Deferred clusters do not block approval of others
- **D-09:** Merge combines two clusters (re-runs clustering on union, new LLM name); Split moves selected members to nearest neighbor or re-review

### Claude's Discretion

- CLI library choice: Context suggests Inquirer or Questionary -- research recommends `questionary` + `rich` (see Standard Stack)
- Specific merge implementation details
- Split implementation approach
- How to store and display per-member silhouette scores
- Review session round tracking mechanism

### Deferred Ideas (OUT OF SCOPE)

None -- discussion stayed within phase scope.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REVIEW-01 | Display suggested clusters grouped by category type with member previews | Rich `Table` class renders cluster rows; per-member previews via `central_member_usernames` field from Phase 4 |
| REVIEW-02 | Show confidence scores for cluster membership (per-member assignment confidence) | `sklearn.metrics.silhouette_samples` returns per-sample coefficients; maps directly to confidence score |
| REVIEW-03 | Support per-cluster actions: approve, reject, rename, merge with another cluster, split | Questionary `select` prompt for action choice; merge uses `compute_clusters()` on union; split reassigns members to nearest centroid |
| REVIEW-04 | Batch actions: approve all clusters with >N members and confident names | Rule-based check before prompt; Questionary `confirm` to confirm batch action |
| REVIEW-05 | Allow deferring a cluster without blocking others | Deferred clusters written to separate registry key; not blocking for Phase 6 |
| REVIEW-06 | Present cluster size distribution before review; warn if heavily skewed | `generate_size_histogram()` already exists in `embed.py`; print before table |
| REVIEW-07 | After N approved rounds (configurable), offer to enable full automation mode | Round counter tracked in approval registry JSON; threshold configurable via `REVIEW_AUTOMATION_ROUNDS` env var |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `rich` | 14.x | Terminal table rendering, colorized output | Best-in-class terminal formatting; used by many Python CLI tools |
| `questionary` | 2.x | Interactive prompts (select, confirm, checkbox, text) | Active maintenance (PyInquirer EOL); clean API; MIT licensed |
| `scikit-learn` | (already installed) | Per-member silhouette scores | Phase 4 already uses sklearn; `silhouette_samples()` is the standard approach |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pyyaml` | (already installed) | Config/env var loading | Load `REVIEW_AUTOMATION_ROUNDS` threshold |
| `jsonschema` | latest | Validate approval registry JSON | Ensure Phase 6 can read Phase 5 output |

**Installation:**
```bash
pip install rich questionary
```

## Architecture Patterns

### Recommended Project Structure

```
src/
├── review/
│   ├── __init__.py
│   ├── cli.py           # Main review CLI entry point
│   ├── table.py         # Rich table rendering for cluster display
│   ├── prompts.py       # Questionary prompt wrappers
│   ├── registry.py      # Approval registry read/write
│   ├── merge_split.py  # Merge and split cluster operations
│   └── metrics.py       # Per-member silhouette/confidence computation
data/
└── clusters/
    ├── approved.json    # Phase 5 output: approved clusters for Phase 6
    ├── deferred.json    # Phase 5 output: deferred clusters
    └── rejected.json    # Phase 5 output: rejected clusters
```

### Pattern 1: Rich Table with Pagination

**What:** Display cluster summary table with Rich `Table`, paginating if many clusters.
**When to use:** REVIEW-01 -- displaying all clusters before user acts on them.
**Example:**
```python
from rich.console import Console
from rich.table import Table

console = Console()
table = Table(title="Suggested Clusters")
table.add_column("Cluster Name", style="cyan bold")
table.add_column("Members", justify="right")
table.add_column("Size", justify="right")
table.add_column("Silhouette", justify="right")
table.add_column("Status", style="yellow")

for cluster in clusters:
    table.add_row(
        cluster["name"],
        ", ".join(cluster["central_members"][:3]),
        str(cluster["size"]),
        f"{cluster['silhouette']:.3f}",
        cluster["status"],
    )

console.print(table)
```

### Pattern 2: Questionary Select Prompt for Cluster Actions

**What:** Present action choices per cluster using `questionary.select()`.
**When to use:** REVIEW-03 -- per-cluster approve/reject/rename/merge/split/defer.
**Example:**
```python
import questionary

action = questionary.select(
    f"Action for '{cluster_name}' ({size} members, silhouette={sil:.3f}):",
    choices=["approve", "reject", "rename", "merge", "split", "defer", "see members"],
).ask()
```

### Pattern 3: Per-Member Silhouette Score

**What:** Use `sklearn.metrics.silhouette_samples()` to get per-account assignment confidence.
**When to use:** REVIEW-02 -- showing per-member silhouette/confidence scores.
**Implementation:** Load embeddings from `data/embeddings.npy` (cached by Phase 4), call `silhouette_samples()`, map back to usernames via the sidecar JSON.

```python
from sklearn.metrics import silhouette_samples
import numpy as np

def compute_member_silhouettes(
    embeddings: np.ndarray,
    labels: np.ndarray,
    usernames: list[str],
) -> dict[str, float]:
    """Compute per-member silhouette score from clustering result."""
    scores = silhouette_samples(embeddings, labels)
    return {uname: float(scores[i]) for i, uname in enumerate(usernames)}
```

### Pattern 4: Merge via Re-clustering

**What:** When merging cluster A and B, take all members from both, re-run clustering constrained to 1 cluster (or let algorithm decide if merge creates sub-clusters).
**When to use:** D-09 merge operation.
**Implementation:**
1. Collect all account dicts from both clusters
2. Extract their embeddings from the cached `embeddings.npy`
3. Re-run `compute_clusters()` with those members only
4. Call `name_cluster()` from `src/cluster/name.py` to get new LLM-generated name
5. Write updated cluster_id and cluster_name back to all affected cache files

### Pattern 5: Split via Nearest-Neighbor Reassignment

**What:** When splitting cluster A, move selected members to their nearest neighboring cluster centroid.
**When to use:** D-09 split operation.
**Implementation:**
1. User selects which members to move out of cluster A
2. For each selected member, compute distance to all cluster centroids (already in `final_centroids` from Phase 4)
3. Reassign each to the nearest centroid (excluding A's centroid)
4. Update cache files for moved members

### Pattern 6: Approval Registry JSON

**What:** Write approved/deferred/rejected cluster decisions to JSON for Phase 6 consumption.
**When to use:** Output of Phase 5 review session.
**Schema:**
```json
{
  "version": 1,
  "session_id": "uuid",
  "rounds_completed": 2,
  "automation_offered": true,
  "automation_enabled": false,
  "clusters": {
    "approved": [
      {
        "cluster_id": 0,
        "cluster_name": "Bay Area Tech",
        "size": 23,
        "silhouette": 0.72,
        "members": ["user1", "user2"],
        "round_approved": 1
      }
    ],
    "deferred": [...],
    "rejected": [...]
  },
  "batch_approved_count": 0,
  "timestamp": "2026-04-05T..."
}
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Terminal table formatting | Custom ASCII art or string padding | `rich.Table` | Handles alignment, color, borders, overflow automatically |
| Interactive prompts | `input()` with manual parsing | `questionary` | Handles arrow keys, autocomplete, validation, edge cases |
| Per-member confidence | Custom distance computation | `sklearn.metrics.silhouette_samples` | Standard, validated, handles edge cases (noise labels, single-cluster) |
| State persistence | Database or custom serializer | JSON files in `data/clusters/` | Matches existing project pattern (immediate caching); Phase 6 reads JSON |
| Cluster naming | Keyword extraction from merged bios | `name_cluster()` from `src/cluster/name.py` | Already uses LLM or rule-based fallback; consistent with Phase 4 |

## Common Pitfalls

### Pitfall 1: Embedding Cache Not Available at Review Time
**What goes wrong:** `data/embeddings.npy` may be missing or stale when Phase 5 runs standalone.
**Why it happens:** Embeddings are cached by Phase 4 but the sidecar JSON (username order) is needed to map back to accounts.
**How to avoid:** Check both `embeddings.npy` and `.sidecar.json` exist; if missing, log a clear error pointing to Phase 4.
**Warning signs:** `IndexError` when iterating silhouette scores, username list length mismatch.

### Pitfall 2: Silhouette Score Misleading for Small Clusters
**What goes wrong:** A cluster with 2 members always has a perfect silhouette of 1.0 for those members, which looks great but is meaningless.
**Why it happens:** `silhouette_samples` with 2 points in a cluster means the two are trivially similar.
**How to avoid:** Flag clusters below minimum size (5) separately; show "N/A" for silhouette if cluster is too small rather than a misleading high score.
**Warning signs:** Cluster size histogram showing clusters_under_5 > 0.

### Pitfall 3: Merge Produces No-Change When Members Are Too Similar
**What goes wrong:** Merging two clusters that are already close together produces the same clustering result, confusing the user.
**How to avoid:** Before merge, compute mean silhouette of the merged cluster; if it is not meaningfully different, warn the user that the merge may not change much.
**Warning signs:** Post-merge silhouette score is nearly identical to pre-merge scores.

### Pitfall 4: Round Counter Resets on Re-run
**What goes wrong:** If user runs Phase 5 twice, the rounds_completed counter may double-count or reset.
**How to avoid:** Track rounds in the approval registry (not in memory); load registry on startup; only increment when a NEW approval action occurs (not on re-review of already-approved clusters).

### Pitfall 5: Cluster Files Not Updated After Merge/Split
**What goes wrong:** Merge/split changes cluster assignments in memory but does not write back to cache files, causing Phase 6 to read stale data.
**How to avoid:** After any merge or split action, immediately write updated `cluster_id` and `cluster_name` fields to all affected `data/enrichment/{username}.json` files. Flush to disk before proceeding.

## Code Examples

### Per-Member Confidence Display (REVIEW-02)

```python
from sklearn.metrics import silhouette_samples
import numpy as np
import json

def get_member_confidence_scores(
    cache_dir: Path,
) -> dict[str, dict[str, float]]:
    """Return per-username silhouette scores keyed by cluster_id."""
    embeddings = np.load("data/embeddings.npy")
    with open("data/embeddings.sidecar.json") as f:
        usernames: list[str] = json.load(f)

    # Load cluster labels from any cache file to get the label ordering
    cluster_ids = []
    for fpath in sorted(cache_dir.glob("*.json")):
        if fpath.stem in ("suspended", "protected", "errors"):
            continue
        d = json.load(open(fpath))
        cluster_ids.append(d.get("cluster_id"))

    labels = np.array(cluster_ids)
    scores = silhouette_samples(embeddings, labels)

    # Group by cluster
    result: dict[str, dict[str, float]] = {}
    for i, uname in enumerate(usernames):
        cid = str(labels[i])
        if cid not in result:
            result[cid] = {}
        result[cid][uname] = float(scores[i])

    return result
```

### Rich Table with Per-Member Detail (REVIEW-01, REVIEW-02)

```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

def display_clusters_with_members(
    clusters: list[dict],
    member_scores: dict[str, dict[str, float]],
    cache_dir: Path,
):
    console = Console()

    for cluster in clusters:
        cid = str(cluster["cluster_id"])
        members = cluster["members"]  # list of usernames

        # Build member detail rows
        member_rows = []
        for uname in members[:10]:  # show top 10
            score = member_scores.get(cid, {}).get(uname, 0.0)
            acct = json.load(open(cache_dir / f"{uname}.json"))
            bio = acct.get("description", "")[:60]
            member_rows.append(f"[cyan]{uname}[/cyan] | score={score:.3f} | {bio}")

        table = Table(title=f"[bold]{cluster['cluster_name']}[/bold] ({cluster['size']} members)")
        table.add_column("Username", style="cyan")
        table.add_column("Confidence", justify="right")
        table.add_column("Bio snippet")

        for uname in members[:10]:
            score = member_scores.get(cid, {}).get(uname, 0.0)
            acct = json.load(open(cache_dir / f"{uname}.json"))
            bio = acct.get("description", "")[:60]
            table.add_row(uname, f"{score:.3f}", bio)

        console.print(table)
```

### Batch Approve Logic (REVIEW-04)

```python
BATCH_SIZE_THRESHOLD = 10
BATCH_SILHOUETTE_THRESHOLD = 0.5

def get_batch_approvable_clusters(clusters: list[dict]) -> list[dict]:
    """Return clusters that meet batch approval criteria."""
    return [
        c for c in clusters
        if c["status"] == "pending"
        and c["size"] >= BATCH_SIZE_THRESHOLD
        and c["silhouette"] >= BATCH_SILHOUETTE_THRESHOLD
    ]
```

### Merge Operation (REVIEW-03)

```python
from src.cluster.embed import compute_clusters, embed_accounts
from src.cluster.name import name_cluster

def merge_clusters(cluster_a_id: int, cluster_b_id: int, cache_dir: Path) -> int:
    """Merge two clusters; returns new cluster_id."""
    # Collect all accounts from both clusters
    members_a = load_members_of_cluster(cluster_a_id, cache_dir)
    members_b = load_members_of_cluster(cluster_b_id, cache_dir)
    all_members = members_a + members_b

    # Re-embed (use cached embeddings, filter to union members)
    embeddings = np.load("data/embeddings.npy")
    with open("data/embeddings.sidecar.json") as f:
        all_usernames: list[str] = json.load(f)

    username_set = {m["username"] for m in all_members}
    mask = np.array([u in username_set for u in all_usernames])
    union_embeddings = embeddings[mask]

    # Re-cluster with k=1 (force single cluster) or let algorithm decide
    # For simplicity, use k=1 to create one merged cluster
    seed_emb = {cat: np.mean(embeddings[np.array([True] * len(embeddings))], axis=0, keepdims=True)
                for cat in []}  # empty = no seed guidance
    labels, _, _, _ = compute_clusters(union_embeddings, seed_emb, algorithm="kmeans")

    new_cluster_id = int(labels[0])

    # Name the merged cluster via LLM
    bios = [m.get("description", "") for m in all_members[:10]]
    new_name = name_cluster(bios)

    # Write back to cache files
    for member in all_members:
        member["cluster_id"] = new_cluster_id
        member["cluster_name"] = new_name
        json.dump(member, open(cache_dir / f"{member['username']}.json", "w"))

    return new_cluster_id
```

### Split Operation (REVIEW-03)

```python
def split_cluster(
    source_cluster_id: int,
    members_to_move: list[str],
    cache_dir: Path,
    final_centroids: np.ndarray,
) -> None:
    """Move selected members from source cluster to nearest neighbor cluster."""
    members = load_members_of_cluster(source_cluster_id, cache_dir)
    member_embeddings = get_embeddings_for_usernames(members_to_move)

    for i, uname in enumerate(members_to_move):
        emb = member_embeddings[i]
        # Distance to all centroids; set source cluster distance to infinity
        dists = np.linalg.norm(final_centroids - emb, axis=1)
        dists[source_cluster_id] = np.inf
        nearest = int(np.argmin(dists))

        # Update cache file
        acct = json.load(open(cache_dir / f"{uname}.json"))
        acct["cluster_id"] = nearest
        # Recompute cluster_name is left to Phase 6 (or re-run name.py)
        json.dump(acct, open(cache_dir / f"{uname}.json", "w"))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| argparse + manual input() prompts | Rich (tables) + Questionary (prompts) | 2024-2025 Python CLI ecosystem shift | Better UX, keyboard navigation, color |
| Global silhouette score only | Per-member silhouette_samples | sklearn 1.x | Enables REVIEW-02 per-member confidence display |
| Single-pass approve-all | "See all, then act" per-cluster actions | Context decision D-03 | More thoughtful review; deferred clusters don't block |
| Manual cluster naming after merge | LLM re-naming via existing name_cluster() | Reuse Phase 4 pattern | Consistent naming quality |

**Deprecated/outdated:**
- `PyInquirer`: End-of-life since 2022; replaced by `InquirerPy` (maintained fork) or `questionary`. Do not use.
- `tabulate` alone for tables: Lacks color and pagination support; use `rich.Table` instead.

## Open Questions

1. **Should merge/split operations be reversible?**
   - What we know: The approval registry tracks approved state, but merge/split are intermediate operations.
   - What's unclear: Whether to track a full undo stack or just re-run Phase 4 clustering.
   - Recommendation: Implement as atomic operations that rewrite cache files immediately. No undo needed if user can re-run Phase 4 to regenerate clusters from scratch.

2. **How to handle clusters with no enrichment data (empty bios)?**
   - What we know: `silhouette_samples` can compute scores from embeddings alone.
   - What's unclear: Whether a cluster with all empty bios can still be meaningfully named via LLM.
   - Recommendation: Show silhouette score but display "No bio data" for bio snippet. Use rule-based naming fallback.

3. **Round tracking across multiple review sessions?**
   - What we know: The approval registry JSON stores `rounds_completed`.
   - What's unclear: Whether Phase 5 is run once per review session or can be iterated multiple times in one session.
   - Recommendation: Load existing registry on startup; increment `rounds_completed` only when NEW clusters are approved (not on re-review of already-approved ones).

## Environment Availability

Step 2.6: SKIPPED (no external dependencies beyond Python packages already used in project)

The phase uses existing project infrastructure:
- Python packages: already used in Phases 1-4 (`rich` new, `questionary` new, `scikit-learn` existing)
- File paths: `data/enrichment/*.json`, `data/embeddings.npy` (produced by Phase 4)
- CLI entry: `python -m src.review.cli` (similar pattern to Phase 1-3)

## Sources

### Primary (HIGH confidence)
- [sklearn.metrics.silhouette_samples documentation](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_samples.html) - per-sample silhouette coefficient, verified algorithm
- [Questionary GitHub - tmbo/questionary](https://github.com/tmbo/questionary) - active maintenance, 2.0.1, MIT license
- [Rich documentation - Introduction](https://rich.readthedocs.io/en/stable/introduction.html) - Table and Prompt classes for CLI output

### Secondary (MEDIUM confidence)
- [Real Python - The Python Rich Package](https://realpython.com/python-rich-package) - Rich usage patterns and examples
- [Questionary Quickstart documentation](https://questionary.readthedocs.io/en/stable/pages/quickstart.html) - prompt API examples
- [PyInquirer vs InquirerPy comparison - LibHunt](https://www.libhunt.com/compare-PyInquirer-vs-InquirerPy) - PyInquirer EOL status confirmed

### Tertiary (LOW confidence)
- [dedupe.io clustering.py - Union-Find for merge/split](https://github.com/dedupeio/dedupe/blob/master/dedupe/clustering.py) - general clustering pattern, not specific to this use case; marked for validation during implementation
- [python-statemachine SQLite-backed approval workflow](https://python-statemachine.readthedocs.io/en/develop/auto_examples/sqlite_persistent_model_machine.html) - overkill for JSON-based registry; reference only

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - library versions and capabilities verified via web search
- Architecture: HIGH - patterns directly from existing Phase 4 code + verified library docs
- Pitfalls: MEDIUM - some identified from general knowledge rather than project-specific history

**Research date:** 2026-04-05
**Valid until:** 2026-05-05 (30 days; CLI library ecosystem is stable)
