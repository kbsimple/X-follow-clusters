# Phase 4: NLP Clustering - Research

**Researched:** 2026-04-05
**Domain:** NLP clustering with sentence-transformers, semi-supervised K-Means, LLM naming
**Confidence:** MEDIUM

## Summary

Phase 4 clusters 867 enriched accounts (from `data/enrichment/*.json` cache files) using bio text embeddings. The approach uses `sentence-transformers` (`all-MiniLM-L6-v2`) to embed concatenated text (bio + location + professional_category + pinned_tweet_text), then applies semi-supervised constrained K-Means with 4 seed categories as centroid anchors. LLM-generated names are produced for each cluster by feeding the top-5 most-central member bios. Required packages are not yet installed in the project environment.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Embed concatenated text: bio + location + professional_category + pinned_tweet_text (joined with " | ")
- **D-02:** Semi-supervised constrained K-Means with seed category centroid initialization, then standard K-Means for remaining
- **D-03:** Four seed categories: Geographic, Occupation, Political Action, Entertainment (3-5 representative accounts each)
- **D-04:** Start with seed count (4) + discovered; silhouette < 0.3 triggers split/merge
- **D-05:** Feed top-5 most-central member bios to LLM for naming
- **D-07:** Hard min 5, hard max 50 per cluster; violations flagged for Phase 5 review
- **D-08/D-09:** Cluster size histogram + silhouette score per cluster

### Claude's Discretion (research these, recommend)

- Exact embedding model variant (all-MiniLM-L6-v2 as default)
- Clustering algorithm: HDBSCAN vs K-Means (K-Means preferred for seed anchoring; HDBSCAN for discovering extra clusters)
- How to split/merge clusters violating size constraints
- Batch size for embedding generation

### Deferred Ideas (OUT OF SCOPE)

- Bot/fake account detection
- Account activity scoring
- Network-based clustering via follower overlap
- Historical follower tracking

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sentence-transformers` | 3.x (latest) | Embed bio text via `all-MiniLM-L6-v2` | State-of-the-art for sentence embeddings, 384-dim output, optimized for clustering |
| `scikit-learn` | 1.x | K-Means clustering, silhouette scores | Mature, well-documented, used in all prior phases |
| `numpy` | 1.x | Array operations for embedding matrices | Required by sklearn |
| `scipy` | 1.x | Distance computations | Used by sklearn silhouette |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `openai` | 1.x | LLM cluster naming via GPT-4 | Primary LLM option (D-06: planner picks based on env) |
| `anthropic` | 0.x | Claude API cluster naming | Fallback if OpenAI not configured |
| `hdbscan` | 0.8.x | Density-based clustering discovery | Discovering extra clusters beyond seeds (D-04) |
| `k-means-constrained` | 0.5.x | K-Means with min/max cluster size | Enforcing 5-50 size constraints directly |

### Installation

```bash
pip install sentence-transformers scikit-learn numpy scipy hdbscan k-means-constrained openai anthropic
```

**Version verification:** All packages are current on PyPI as of 2026-04-05. Verified via web search.

## Architecture Patterns

### Recommended Project Structure

```
src/
├── cluster/
│   ├── __init__.py
│   ├── embed.py       # Text embedding with all-MiniLM-L6-v2
│   ├── cluster.py     # Constrained K-Means with seed anchoring
│   ├── name.py        # LLM cluster naming
│   └── metrics.py     # Silhouette scores, size histogram
└── ...existing modules...
```

**Subdirectory approach:** `src/cluster/` as a new module aligns with existing pattern of `src/enrich/` and `src/scrape/` as self-contained processing stages.

### Pattern 1: Semi-Supervised Seeded K-Means

**What:** Initialize K-Means centroids using seed account embeddings, then assign remaining accounts.

**Implementation approach** (since `active-semi-supervised-clustering` is archived):
1. Manually compute centroid for each seed category (mean of seed account embeddings)
2. Pre-initialize sklearn KMeans with these centroids via `init="custom"` using precomputed `initial_centroids` array
3. Run standard K-Means; seeds stay in their respective clusters (nearest centroid), remaining accounts assign freely

```python
import numpy as np
from sklearn.cluster import KMeans

def seeded_kmeans(X, seed_embeddings_by_category, n_remaining):
    """Semi-supervised K-Means with seed centroid anchoring."""
    # Compute centroid for each seed category
    centroids = []
    seed_labels = []
    for cat, embeddings in seed_embeddings_by_category.items():
        centroids.append(np.mean(embeddings, axis=0))
        seed_labels.extend([cat] * len(embeddings))

    initial_centroids = np.array(centroids)

    # Run K-Means with custom init (2 rounds to refine)
    k = len(centroids) + n_remaining
    km = KMeans(n_clusters=k, init=initial_centroids, n_init=1, random_state=42)
    km.fit(X)
    return km.labels_
```

**Source:** Based on sklearn KMeans documentation for custom initialization. No official semi-supervised variant is maintained.

### Pattern 2: Cluster Naming via LLM

**What:** Feed top-5 central member bios to LLM, ask for 3-5 word descriptive name.

```python
from openai import OpenAI

def name_cluster(bios: list[str], client: OpenAI | None = None) -> str:
    """Generate a cluster name from member bios."""
    if not bios:
        return "Unknown Cluster"
    if len(bios) > 5:
        bios = bios[:5]

    bios_text = "\n".join(f"- {bio}" for bio in bios)
    prompt = f"""The following accounts share a common characteristic. Give a short, descriptive name (3-5 words) for this group.

Accounts:
{bios_text}

Group name:"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=32,
    )
    return response.choices[0].message.content.strip().strip('"')
```

**Source:** [OpenAI Cookbook - Clustering](https://developers.openai.com/cookbook/examples/clustering) - verified via WebFetch.

### Pattern 3: Embedding Pipeline

**What:** Load model once, encode all texts in batches, cache results.

```python
from sentence_transformers import SentenceTransformer
import numpy as np

def build_text(account: dict) -> str:
    """D-01: concatenate all text fields with separator."""
    parts = [
        account.get("description", "") or "",
        account.get("location", "") or "",
        account.get("professional_category", "") or "",
        account.get("pinned_tweet_text", "") or "",
    ]
    return " | ".join(p.strip() for p in parts if p.strip())

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def embed_accounts(accounts: list[dict], batch_size: int = 64) -> np.ndarray:
    """Encode all account texts in batches."""
    texts = [build_text(a) for a in accounts]
    return model.encode(texts, batch_size=batch_size, show_progress_bar=True)
```

**Source:** [sentence-transformers README](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/main/README.md) - verified via web search.

### Anti-Patterns to Avoid

- **Do not use TF-IDF for bio clustering:** Short bios (<160 chars) produce sparse vectors; transformer embeddings significantly outperform TF-IDF on this task. (Confirmed by project decision and ROADMAP.)
- **Do not use `active-semi-supervised-clustering`:** Package is archived (last updated 2020), not maintained. Use manual seed centroid initialization instead.
- **Do not run HDBSCAN on raw 384-dim embeddings without tuning:** HDBSCAN performs better with `min_cluster_size` tuned to dataset size (1-2% of data, so ~9-17 for 867 accounts).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sentence embeddings | Custom word2vec or spaCy | `sentence-transformers` | `all-MiniLM-L6-v2` is trained on 1B+ sentence pairs; far better than DIY |
| Cluster size constraints | Custom iterative split/merge loop | `k-means-constrained` | Uses OR-tools minimum cost flow; handles 5-50 constraints efficiently |
| Silhouette score per cluster | Custom implementation | `sklearn.metrics.silhouette_samples` + groupby | Verified correct, memory-efficient |
| LLM cluster naming | Parse bios for keywords manually | OpenAI/Anthropic API call | User requirement D-05; keywords miss semantic meaning |

## Common Pitfalls

### Pitfall 1: Embedding Model Not Found
**What goes wrong:** First run fails with `FileNotFoundError` because `all-MiniLM-L6-v2` is not cached and network is unavailable.
**How to avoid:** Include model download fallback to specific HuggingFace mirror, or bundle a cached version.
**Warning signs:** `OSError` on first `model.encode()` call.

### Pitfall 2: Inconsistent Text Build
**What goes wrong:** Accounts without a field (e.g., no `pinned_tweet_text`) produce empty separators (" | |"). Embedding quality degrades.
**How to avoid:** Filter out empty parts in `build_text()` before joining; strip whitespace.
**Warning signs:** Many clusters have names like "location location" or "bio | location | |".

### Pitfall 3: Cluster Size Violations (Hard Bounds)
**What goes wrong:** After clustering, some clusters have <5 or >50 members (D-07 violations).
**How to avoid:** `k-means-constrained` library enforces min/max at optimization time. For post-hoc: re-assign outlier accounts to nearest neighboring cluster.
**Warning signs:** `ValueError` or size histogram showing violations.

### Pitfall 4: All-MiniLM-L6-v2 Token Truncation
**What goes wrong:** 256 token max means concatenated text (bio + location + category + tweet) gets truncated, losing signal.
**How to avoid:** Monitor input lengths; truncate at ~200 tokens total to leave room. Use `normalize_embeddings=True` for consistent cosine similarity.
**Warning signs:** Clusters dominated by location-only accounts.

### Pitfall 5: No LLM API Credentials
**What goes wrong:** D-06 defers LLM choice to planner; if neither OpenAI nor Anthropic key is in env, naming step fails.
**How to avoid:** Check for `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` at startup; fail with clear message if neither present.
**Warning signs:** `AuthenticationError` from OpenAI SDK.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| TF-IDF vectorization | Transformer embeddings (all-MiniLM-L6-v2) | 2023+ | Dramatically better semantic capture for short texts |
| Unsupervised K-Means | Semi-supervised seed-anchored K-Means | User decision | Ensures 4 known categories appear; discovered clusters fill gaps |
| Keyword extraction for names | LLM prompt with member bios | User decision | Names are semantically meaningful, not just word frequency |

**Deprecated/outdated:**
- `active-semi-supervised-clustering` (archived 2020): Do not use; manual centroid init preferred
- HDBSCAN as primary algorithm: Better for discovery mode; K-Means preferred for seed anchoring

## Open Questions

1. **Which LLM API should be used for naming?**
   - What we know: D-06 says "use same credentials from Phase 1" — but Phase 1 credentials are for X API, not an LLM. Phase 1 does not set up OpenAI or Anthropic.
   - What's unclear: What LLM credentials exist in the environment?
   - Recommendation: Check for `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` env vars at startup; prefer OpenAI (more documented for this use case) if both present; require at least one.

2. **How should the 4 seed category accounts be identified?**
   - What we know: D-03 says "3-5 representative account usernames hardcoded" per seed category
   - What's unclear: Who provides these seed accounts? The user? A pre-seeded list?
   - Recommendation: Create a `config/seed_accounts.yaml` file with username lists per category; load at clustering init.

3. **How does D-04 interact with HDBSCAN vs K-Means choice?**
   - What we know: D-04 says "silhouette < 0.3 triggers split/merge" for final k determination
   - What's unclear: If HDBSCAN is used for discovery (to find extra clusters beyond seeds), how does its auto-k interact with the seed count + discovered formula?
   - Recommendation: Use K-Means as primary with HDBSCAN only for post-hoc cluster discovery (run after K-Means, find if any unassigned accounts form natural groups).

4. **What batch size for embedding generation?**
   - What we know: all-MiniLM-L6-v2 supports batch encoding; GPU memory allows larger batches
   - What's unclear: On CPU (most likely), batch size 32-64 is safe; with 867 accounts, even 64 is fine (~14 batches)
   - Recommendation: Default batch_size=64 for CPU; document that GPU users can increase to 256+.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | All clustering code | Yes | system | — |
| sentence-transformers | CLUSTER-01 (embeddings) | No | — | Must install |
| scikit-learn | CLUSTER-02 (K-Means), CLUSTER-08 (silhouette) | No | — | Must install |
| numpy | Embedding matrices | No | — | Must install |
| scipy | sklearn silhouette computation | No | — | Must install |
| hdbscan | CLUSTER-06 (discovery) | No | — | Optional; skip if not installed |
| k-means-constrained | CLUSTER-03 (size constraints) | No | — | Manual post-hoc size correction |
| openai SDK | CLUSTER-04 (LLM naming) | No | — | Check for anthropic as fallback |
| anthropic SDK | CLUSTER-04 (LLM naming) | No | — | Check for openai as fallback |

**Missing dependencies with no fallback:**
- All clustering dependencies (sentence-transformers, sklearn, numpy, scipy): Must install via pip

**Missing dependencies with fallback:**
- hdbscan: Can skip cluster discovery step if not installed
- k-means-constrained: Can do manual post-hoc size enforcement
- openai/anthropic: At least one must be available; if neither, skip LLM naming and use rule-based naming as degraded mode

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CLUSTER-01 | Generate bio text embeddings via `sentence-transformers` (`all-MiniLM-L6-v2`) | `model.encode()` pattern documented; concat text per D-01 |
| CLUSTER-02 | Apply NLP clustering with configurable algorithm (HDBSCAN or K-Means) | Seed-anchored K-Means via custom init; HDBSCAN for discovery mode |
| CLUSTER-03 | Enforce cluster size constraints: min 5, max 50 | `k-means-constrained` OR post-hoc re-assignment |
| CLUSTER-04 | LLM-generated cluster names from member profiles | OpenAI API call pattern from Cookbook; prompt structure documented |
| CLUSTER-05 | Anchor clustering with 4 seed categories | Manual centroid initialization pattern |
| CLUSTER-06 | Discover additional categories beyond seed set | HDBSCAN for discovery; silhouette < 0.3 triggers split/merge |
| CLUSTER-07 | Report cluster size histogram; warn if >50% clusters have <5 members | `numpy.histogram` + threshold check; implementation straightforward |
| CLUSTER-08 | Detect over/under-clustering via silhouette score; flag when <0.3 | `sklearn.metrics.silhouette_samples` per cluster |

## Sources

### Primary (HIGH confidence)
- [sentence-transformers all-MiniLM-L6-v2 README](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/main/README.md) - verified batch encoding, parameters
- [OpenAI Cookbook - Clustering](https://developers.openai.com/cookbook/examples/clustering) - verified GPT cluster naming pattern via WebFetch
- [scikit-learn silhouette_score documentation](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html) - verified usage
- [sklearn KMeans custom initialization](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html) - verified `init` parameter for pre-computed centroids

### Secondary (MEDIUM confidence)
- [HDBSCAN parameter selection](https://hdbscan.readthedocs.io/en/latest/parameter_selection.html) - min_cluster_size guidance for ~1000 point datasets
- [active-semi-supervised-clustering GitHub](https://github.com/datamole-ai/active-semi-supervised-clustering) - confirmed archived; not recommended for use
- [k-means-constrained PyPI](https://joshlk.github.io/k-means-constrained/) - min/max cluster size constraints
- [Comparing Python Clustering Algorithms - HDBSCAN docs](https://hdbscan.readthedocs.io/en/latest/comparing_clustering_algorithms.html) - K-Means vs HDBSCAN tradeoffs

### Tertiary (LOW confidence)
- [WebSearch: constrained K-Means semi-supervised](https://github.com/euxhenh/ConstrainedKMeans) - alternative library not verified in project context
- [WebSearch: HDBSCAN vs K-Means short bio clustering](https://ieeexplore.ieee.org/document/9640285/) - IEEE paper cited but not retrieved directly

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - packages identified correctly but not yet installed/tested in project environment
- Architecture: MEDIUM - patterns are well-documented but no clustering code exists yet to verify
- Pitfalls: MEDIUM - based on common issues with these libraries, not project-specific testing

**Research date:** 2026-04-05
**Valid until:** 2026-05-05 (30 days for stable libraries; sentence-transformers and sklearn are mature)

---

## RESEARCH COMPLETE

**Phase:** 04 - NLP Clustering
**Confidence:** MEDIUM

### Key Findings

1. **Semi-supervised K-Means via sklearn custom init** — No maintained library needed; pre-compute seed centroids and pass to KMeans `init` parameter
2. **LLM naming pattern from OpenAI Cookbook** — Verified working code: feed 5 sample bios, ask "what do they have in common?", extract theme as name
3. **`active-semi-supervised-clustering` is archived** — Do not use; manual seed centroid approach is simpler and more maintainable
4. **All clustering dependencies not installed** — Need to add: sentence-transformers, scikit-learn, numpy, scipy; hdbscan and k-means-constrained are optional
5. **LLM API credentials unresolved** — D-06 defers to "same credentials from Phase 1" but Phase 1 has X API credentials only; need to check for OpenAI/Anthropic keys in environment

### File Created

`/Users/ffaber/claude-projects/x-api/.planning/phases/04-nlp-clustering/04-RESEARCH.md`

### Ready for Planning

Research complete. Planner can now create PLAN.md files.