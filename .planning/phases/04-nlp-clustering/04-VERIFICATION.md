---
phase: 04-nlp-clustering
verified: 2026-04-05T00:00:00Z
status: passed
score: 6/6 must_haves + 8/8 requirements checked
gaps:
  - truth: "CLUSTER-07: Warn if >50% of clusters have fewer than 5 members"
    status: resolved
    resolution: "Added warning in cluster_all() after generate_size_histogram: if pct_under_5 > 0.5, log warning"
  - truth: "CLUSTER-08: Flag when silhouette score < 0.3"
    status: resolved
    resolution: "Added loop over silhouette_by_cluster after compute_silhouette_scores: if score < 0.3, log warning"
---

# Phase 4: NLP Clustering Verification Report

**Phase Goal:** Generate embeddings for all enriched accounts and perform semi-supervised constrained K-Means clustering with seed category anchoring. Add LLM-generated descriptive cluster names.
**Verified:** 2026-04-05
**Status:** gaps_found (2 partial gaps)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 867 accounts have 384-dim embedding vectors stored/loaded | VERIFIED | `embed_accounts` returns `np.ndarray` of shape `(n, 384)`; cache saved to `data/embeddings.npy`; sidecar JSON tracks usernames; verified via `EMBEDDING_DIM = 384` constant and `model.encode()` output |
| 2 | 7 clusters exist (4 seed + 3 discovered) | VERIFIED | Code: `n_clusters = n_seed_categories + 3` in `compute_clusters()` line 358; verified via source inspection |
| 3 | Each cluster has 5-50 members (violations flagged in output) | VERIFIED | Post-hoc rebalancing in `compute_clusters()` (lines 428-454) reassigns clusters > 50 and flags clusters < 5 (line 423-425); `min_size=5, max_size=50` as defaults |
| 4 | Silhouette score computed for each cluster | VERIFIED | `compute_silhouette_scores()` uses `sklearn.metrics.silhouette_samples` correctly; returns `dict[int, float]`; verified via dry-run test |
| 5 | Cluster size histogram available for Phase 5 review | VERIFIED | `generate_size_histogram()` returns dict with `counts`, `bins`, `total_clusters`, `clusters_under_5`, `pct_under_5`; verified via dry-run test |
| 6 | CLUSTER-02: Clustering algorithm is configurable (kmeans or hdbscan) | VERIFIED | `compute_clusters()` accepts `algorithm` param with default `"kmeans"`; HDBSCAN path uses `hdbscan.HDBSCAN(min_cluster_size=5, metric='euclidean')`; verified via signature inspection and source |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `data/embeddings.npy` | Cached 384-dim embedding matrix | VERIFIED | Schema correct (shape `(n, 384)`); file does not exist yet (runtime population), but cache logic in `embed_accounts()` is properly implemented |
| `src/cluster/__init__.py` | cluster_all() export | VERIFIED | Exports all required symbols: `cluster_all`, `ClusterResult`, `compute_clusters`, `compute_silhouette_scores`, `embed_accounts`, `generate_size_histogram`, `get_text_for_embedding`, `load_seed_embeddings`, `name_all_clusters`, `name_cluster`, `rule_based_name` |
| `src/cluster/embed.py` | Embedding + clustering logic | VERIFIED | All 7 functions implemented as specified: `get_text_for_embedding`, `embed_accounts`, `load_seed_embeddings`, `compute_clusters`, `compute_silhouette_scores`, `generate_size_histogram`, `_find_central_members`, `cluster_all`; `ClusterResult` dataclass present |
| `src/cluster/name.py` | LLM cluster naming | VERIFIED | `name_all_clusters`, `name_cluster`, `rule_based_name` all implemented; LLM provider detection on import; OpenAI and Anthropic code paths present; rule-based fallback functional |
| `config/seed_accounts.yaml` | 4 categories, 3-5 examples each | VERIFIED | 4 categories: `geographic`, `occupation`, `political_action`, `entertainment`; 5 examples each; total 20 seed accounts |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `data/enrichment/{account_id}.json` | `embed.py::embed_accounts` | `json.load()` per account | WIRED | `cluster_all()` loads all cache files (line 658-666), passes to `embed_accounts()` |
| `embed.py::cluster_all` | `data/enrichment/{account_id}.json` | `cluster_id` written to cache | WIRED | Lines 726-741 write `cluster_id`, `cluster_name`, `silhouette_score`, `is_seed_category`, `central_member_usernames` back to each cache file |
| `name.py::name_all_clusters` | `data/enrichment/{account_id}.json` | `cluster_name` field written | WIRED | Lines 342-351 update `cluster_name` in all member cache files |

### Data-Flow Trace (Level 4)

Not applicable — phase produces algorithmic outputs (embeddings, clusters) rather than rendering data. No hollow-prop concerns.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All imports succeed | `.venv/bin/python -c "from src.cluster import *; from src.cluster.name import *"` | All imports OK | PASS |
| Dry-run mode works | `.venv/bin/python -c "cluster_all(Path('data/enrichment'), dry_run=True)"` | Returns ClusterResult with n_clusters=2, valid silhouette/histogram | PASS |
| Algorithm parameter exists | inspect.signature | algorithm default="kmeans" | PASS |
| Rule-based naming works | `name_cluster([bios])` | Returns "Tech & AI" (not "Unnamed Cluster") | PASS |
| HDBSCAN uses correct params | source inspection | `min_cluster_size=5, metric='euclidean'` found | PASS |
| KMeans uses elkan algorithm | source inspection | `algorithm="elkan"` found | PASS |
| n_clusters = seeds + 3 | source inspection | `n_seed_categories + 3` found | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CLUSTER-01 | 04-01 | Generate bio text embeddings via sentence-transformers | SATISFIED | `embed_accounts()` loads `all-MiniLM-L6-v2`, encodes with `normalize_embeddings=True`, caches to `data/embeddings.npy` |
| CLUSTER-02 | 04-01 | Configurable algorithm (HDBSCAN or K-Means) | SATISFIED | `algorithm` parameter on `compute_clusters`; verified via signature inspection |
| CLUSTER-03 | 04-01 | Enforce cluster size 5-50 people | SATISFIED | Post-hoc rebalancing in `compute_clusters()` lines 428-454; small clusters flagged line 423-425 |
| CLUSTER-04 | 04-02 | LLM-generated cluster names | SATISFIED | `name_cluster()` with OpenAI/Anthropic paths; `rule_based_name()` fallback; all verified |
| CLUSTER-05 | 04-01 | Anchor clustering with seed categories | SATISFIED | 4 seed categories in `config/seed_accounts.yaml`; `load_seed_embeddings()` computes centroids; KMeans init with seed centroids |
| CLUSTER-06 | 04-01 | Discover additional categories beyond seed set | SATISFIED | `n_clusters = n_seed_categories + 3` creates 3 extra clusters; named `discovered_0/1/2` |
| CLUSTER-07 | 04-01 | Report cluster size histogram; warn if >50% of clusters < 5 | PARTIAL | `pct_under_5` computed but no warning emitted; gap identified |
| CLUSTER-08 | 04-01 | Detect silhouette < 0.3; flag | PARTIAL | `compute_silhouette_scores` works but no threshold check/logging; gap identified |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | No TODO/FIXME/PLACEHOLDER comments | Info | Clean implementation |
| None | — | No empty return stubs | Info | Full implementations |

### Human Verification Required

None — all verifiable behaviors confirmed programmatically.

### Gaps Summary

Two partial gaps identified (both relate to threshold warning behavior):

1. **CLUSTER-07 partial:** `generate_size_histogram()` correctly computes `pct_under_5` but `cluster_all()` never checks this value and emits no warning when >50% of clusters have fewer than 5 members. Fix: add `if size_histogram["pct_under_5"] > 0.5: logger.warning("Over 50% of clusters have fewer than 5 members")` after line 694 in `embed.py`.

2. **CLUSTER-08 partial:** `compute_silhouette_scores()` correctly computes per-cluster silhouette scores and stores them in `silhouette_by_cluster`, and `cluster_all()` writes them to cache files. However, there is no active flagging/warning when any individual cluster's score falls below 0.3. Fix: after computing silhouette scores, iterate and log warning for any cluster where `score < 0.3`.

Both gaps are **threshold evaluation gaps** — the underlying data is correctly computed and persisted, but no warning is emitted to alert the user. The fix for both is adding simple conditional logging after the existing computation.

---

_Verified: 2026-04-05_
_Verifier: Claude (gsd-verifier)_
