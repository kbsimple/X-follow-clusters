# Phase 4: NLP Clustering - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-05
**Phase:** 04-nlp-clustering
**Areas discussed:** Input text, Seed anchoring, Cluster count, LLM naming
**Mode:** auto (--auto flag used)

---

## Input Text for Embeddings

| Option | Description | Selected |
|--------|-------------|----------|
| Bio only | Use raw X API bio field only | |
| Bio + scraped fields | Concatenate bio + location + professional_category + pinned_tweet_text | ✓ |

**[auto]** Q: "What text to embed for clustering?" → Selected: "Bio + scraped fields" (recommended default)
**Reasoning:** Maximizes signal. Phase 3 scraped fields add richness.

---

## Seed Category Anchoring

| Option | Description | Selected |
|--------|-------------|----------|
| Semi-supervised (constrained K-Means) | Seeds initialize centroids; algorithm assigns remaining | ✓ |
| Hard constraints (must-find) | Algorithm forced to find each seed category | |
| Unsupervised + post-hoc labeling | Pure unsupervised, map seeds to clusters after | |

**[auto]** Q: "Use seed categories as hard constraints, soft hints, or unsupervised with post-hoc labeling?" → Selected: "Semi-supervised (constrained K-Means)" (recommended default)

---

## Cluster Count

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-detect via silhouette | Let algorithm find optimal k | |
| Seed count + discovered | Start with seeds, add discovered clusters if silhouette < threshold | ✓ |

**[auto]** Q: "How should cluster count be determined?" → Selected: "Seed count + discovered" (recommended default)

---

## LLM Naming Prompt Content

| Option | Description | Selected |
|--------|-------------|----------|
| Top-5 central member bios | Most similar to centroid fed to LLM for naming | ✓ |
| Full cluster membership | All member bios fed to LLM | |
| Centroid only | Just the embedding centroid | |

**[auto]** Q: "What profile content feeds the LLM cluster-naming prompt?" → Selected: "Top-5 central member bios" (recommended default)

---

## Claude's Discretion

The following were left to Claude's discretion (planner/implementation decides):
- Exact embedding model (all-MiniLM-L6-v2 as default)
- Clustering algorithm: HDBSCAN vs K-Means (K-Means preferred for seed anchoring)
- How to split/merge clusters violating size constraints
- Batch size for embedding generation

---

## Deferred Ideas

None surfaced during auto discussion.
