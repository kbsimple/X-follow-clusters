---
phase: quick-260418
plan: fbc
type: summary
created: 2026-04-18T18:14:33Z
tags: [clustering, embedding, topic-seeding, kmeans]
duration: 15m
---

# Phase quick-260418 Plan fbc: Topic-Only Seeding for Clustering

## One-Liner

Added topic-only seeding option for KMeans clustering, allowing users to specify semantic topic anchors (e.g., "AI Research", "Politics") without requiring sample accounts.

## Summary

Implemented topic embedding functions that use the same sentence-transformer model as account embeddings, enabling topic names to serve as cluster centroids. Topics can be specified in `config/seed_topics.yaml` and work alongside or independently from account-based seeds.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create topic embedding functions | 49cc61c | src/cluster/embed.py, tests/unit/test_embed_topic_seeding.py |
| 2 | Add topic config loading | 49cc61c | src/cluster/embed.py |
| 3 | Integrate topic seeds into cluster_all() | 4066353 | src/cluster/embed.py |
| 4 | Create example topic config and update test driver | 9585c23 | config/seed_topics.example.yaml, src/cluster/test_cluster.py |

## Key Changes

### New Functions in `src/cluster/embed.py`

- `create_topic_embedding(topic: str) -> list[float]`: Creates a normalized 384-dimensional embedding from a topic name
- `create_topic_embeddings(topics: list[str]) -> dict[str, np.ndarray]`: Batch embedding for multiple topics, returns shape (1, 384) per topic
- `load_topic_embeddings(config_path: Path | None = None) -> dict[str, np.ndarray]`: Loads topics from YAML config, supports list and dict formats

### Integration in `cluster_all()`

- Automatically discovers `config/seed_topics.yaml` if present
- Merges topic seeds with account seeds (topics take precedence on name conflict)
- Topic embeddings work as KMeans initial centroids
- HDBSCAN gracefully ignores topic seeds (unsupervised mode)

### Test Driver Update

- Added `--topic-seeds` flag to `src/cluster/test_cluster.py`
- Loads and displays topic seeds when flag is set

### Example Config

Created `config/seed_topics.example.yaml` with sample topics:
```yaml
topics:
  - AI Research
  - Machine Learning
  - Politics
  - Journalism
  - Startups & VC
  - Science
  - Technology
```

## YAML Formats Supported

1. **List format:**
   ```yaml
   topics:
     - AI Research
     - Politics
   ```

2. **Dict format with null values:**
   ```yaml
   AI Research: null
   Politics: null
   ```

3. **Dict format with descriptions:**
   ```yaml
   AI Research: "Topics related to artificial intelligence"
   Politics: "Political commentary and news"
   ```

## Test Coverage

All 18 unit tests pass:
- `test_returns_384_dimensional_list`: Embedding dimension verification
- `test_returns_normalized_embedding`: Unit length normalization
- `test_different_topics_have_different_embeddings`: Semantic uniqueness
- `test_uses_model_singleton`: Efficient model reuse
- `test_returns_dict_with_correct_keys`: Batch embedding structure
- `test_returns_arrays_with_correct_shape`: Shape (1, 384) per topic
- `test_empty_list_returns_empty_dict`: Edge case handling
- `test_loads_from_config_file`: Config file parsing
- `test_returns_empty_dict_when_file_missing`: Graceful degradation
- `test_handles_list_format`: List YAML format
- `test_handles_dict_format_with_null_values`: Dict with nulls
- `test_handles_dict_format_with_descriptions`: Dict with descriptions
- `test_default_path_is_config_seed_topics_yaml`: Default path
- `test_topics_merge_with_account_seeds`: Merge precedence
- `test_hdbscan_ignores_topic_seeds`: HDBSCAN compatibility

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None identified. Topic seeds are user-controlled config, not external input.

## Self-Check: PASSED

- All files exist: embed.py, seed_topics.example.yaml, test_embed_topic_seeding.py
- All commits found: 49cc61c, 4066353, 9585c23
- All 18 unit tests pass