---
phase: quick-260418
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/cluster/embed.py
  - config/seed_topics.example.yaml
autonomous: true
requirements: []
must_haves:
  truths:
    - "User can specify seed topics in a YAML config file"
    - "Topic names are embedded using the same sentence-transformer model"
    - "Topic embeddings work as KMeans initial centroids"
    - "cluster_all() discovers topics alongside accounts or independently"
  artifacts:
    - path: "src/cluster/embed.py"
      provides: "Topic embedding creation"
      exports: ["create_topic_embeddings", "load_topic_embeddings"]
    - path: "config/seed_topics.example.yaml"
      provides: "Example topic config"
  key_links:
    - from: "config/seed_topics.yaml"
      to: "load_topic_embeddings()"
      via: "YAML parsing"
    - from: "load_topic_embeddings()"
      to: "compute_clusters()"
      via: "seed_embeddings_by_category dict"
---

<objective>
Add topic-only seeding option for KMeans clustering, allowing users to specify seed topics (e.g., "AI Research", "Politics", "Journalism") without requiring sample accounts. The system embeds topic names and uses them as cluster centroids.

**Purpose:** Users may know the topics they want to cluster by but lack representative accounts. Topic seeding provides intuitive semantic anchors.

**Output:** Updated `embed.py` with topic embedding functions, example config file, and modified `cluster_all()` to discover and use topic seeds.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md

## Current Implementation (from codebase analysis)

From `src/cluster/embed.py`:
- `load_seed_embeddings(seed_accounts, cache_dir)` loads account-based seeds from `config/seed_accounts.yaml`
- Returns `dict[str, np.ndarray]` mapping category name to embedding array
- `compute_clusters()` expects `seed_embeddings_by_category` and computes mean per category for KMeans init

From `compute_clusters()` (lines 461-507):
```python
# KMeans seeding logic
seed_centroids = np.vstack([
    np.mean(seed_embs, axis=0) for seed_embs in seed_embeddings_by_category.values()
    if seed_embs.shape[0] > 0
])
n_clusters = n_seed_categories + 3  # seeds + 3 discovered
init_centroids = np.vstack([seed_centroids, random_centroids])
kmeans = KMeans(n_clusters=n_clusters, init=init_centroids, n_init=1, ...)
```

Key insight: `seed_embeddings_by_category` values are arrays of shape `(n_seeds, 384)`. For topic-only seeding, we create arrays of shape `(1, 384)` where the single row is the topic embedding.
</context>

<tasks>

<task type="auto" tdd="true">
<name>Task 1: Create topic embedding functions</name>
<files>src/cluster/embed.py</files>
<behavior>
- Test 1: `create_topic_embedding("AI Research")` returns a 384-dimensional list
- Test 2: `create_topic_embeddings(["AI", "Politics"])` returns dict with 2 keys, each with shape (1, 384)
- Test 3: Topic embeddings are normalized (unit length) matching account embeddings
</behavior>
<action>
Add two functions to `src/cluster/embed.py` after the existing embedding functions (around line 195):

1. `create_topic_embedding(topic: str) -> list[float]`:
   - Uses the same `SentenceTransformer(EMBEDDING_MODEL)` singleton from `_get_tweet_embedding_model()`
   - Encodes the topic string with `normalize_embeddings=True`
   - Returns the embedding as a list[float] (JSON-serializable)

2. `create_topic_embeddings(topics: list[str]) -> dict[str, np.ndarray]`:
   - Takes a list of topic names
   - Embeds all topics in a single batch call for efficiency
   - Returns `dict[topic_name, embedding_array]` where each value has shape `(1, EMBEDDING_DIM)`

Both functions should use the existing model singleton `_get_tweet_embedding_model()` to avoid re-loading the model.

Add appropriate docstrings explaining that topic embeddings are conceptually similar to account seed embeddings but derived directly from semantic topic names.
</action>
<verify>
<automated>.venv/bin/python -m pytest tests/unit/test_embed_topic_seeding.py -v</automated>
</verify>
<done>
- `create_topic_embedding()` returns normalized 384-dim embedding
- `create_topic_embeddings()` returns dict with correct shapes
- Unit tests pass
</done>
</task>

<task type="auto" tdd="true">
<name>Task 2: Add topic config loading</name>
<files>src/cluster/embed.py</files>
<behavior>
- Test 1: `load_topic_embeddings()` loads from `config/seed_topics.yaml` if it exists
- Test 2: Returns empty dict if file doesn't exist (graceful degradation)
- Test 3: Handles YAML format: `{"topics": ["AI Research", "Politics"]}` or `{"AI Research": null, "Politics": null}`
</behavior>
<action>
Add `load_topic_embeddings(config_path: Path | None = None) -> dict[str, np.ndarray]` to `src/cluster/embed.py`:

1. Default path is `config/seed_topics.yaml`
2. If file doesn't exist, return empty dict (not an error - topics are optional)
3. Parse YAML supporting two formats:
   - List format: `topics: ["AI Research", "Politics"]`
   - Dict format: `{"AI Research": null, "Politics": null}` or `{"AI Research": "description"}`
4. Extract topic names and call `create_topic_embeddings()`
5. Return the dict mapping topic name to embedding array

This mirrors the pattern used by `load_seed_embeddings()` for accounts but is simpler since we don't need to look up account files.
</action>
<verify>
<automated>.venv/bin/python -m pytest tests/unit/test_embed_topic_seeding.py::test_load_topic_embeddings -v</automated>
</verify>
<done>
- `load_topic_embeddings()` parses both YAML formats
- Returns empty dict gracefully when file missing
- Unit tests pass
</done>
</task>

<task type="auto" tdd="true">
<name>Task 3: Integrate topic seeds into cluster_all()</name>
<files>src/cluster/embed.py</files>
<behavior>
- Test 1: `cluster_all()` discovers topics from `config/seed_topics.yaml` automatically
- Test 2: Topics are merged with account seeds (both work together)
- Test 3: Topics work independently when no account seeds exist
- Test 4: HDBSCAN algorithm ignores topic seeds (unsupervised)
</behavior>
<action>
Modify `cluster_all()` function (starting line 707) to discover and use topic seeds:

1. After loading `seed_accounts` from `seed_accounts.yaml` (lines 759-774), also call `load_topic_embeddings()` to load topic seeds

2. Merge the two seed sources:
   ```python
   seed_embeddings = load_seed_embeddings(seed_accounts, cache_dir)
   topic_embeddings = load_topic_embeddings()
   # Merge: topics take precedence for same category name
   all_seeds = {**seed_embeddings, **topic_embeddings}
   ```

3. Pass `all_seeds` to `compute_clusters()` instead of just `seed_embeddings`

4. Update the cluster name mapping logic (lines 845-859) to include topic-derived cluster names

5. Add logging: "Loaded {n_topic} topic seeds from config/seed_topics.yaml" when topics are found

For HDBSCAN mode: The existing code already handles empty seed dict gracefully (lines 508-544). Topic seeds are simply added to the dict but HDBSCAN ignores them since it doesn't use seed centroids.

The integration is minimal - topic seeds become just another source of embedding anchors alongside account-based seeds.
</action>
<verify>
<automated>.venv/bin/python -m pytest tests/unit/test_embed_topic_seeding.py::test_cluster_all_with_topics -v</automated>
</verify>
<done>
- `cluster_all()` discovers `config/seed_topics.yaml` automatically
- Topics merge with account seeds (precedence to topics on conflict)
- Works in both KMeans and HDBSCAN modes
- Unit tests pass
</done>
</task>

<task type="auto">
<name>Task 4: Create example topic config and update test driver</name>
<files>config/seed_topics.example.yaml, src/cluster/test_cluster.py</files>
<action>
1. Create `config/seed_topics.example.yaml` with example topics:
```yaml
# Topic-only seeding for clustering
# These topics are embedded and used as cluster centroids
# Useful when you know the categories but don't have representative accounts

topics:
  - AI Research
  - Machine Learning
  - Politics
  - Journalism
  - Startups & VC
  - Science
  - Technology
```

2. Update `src/cluster/test_cluster.py` to show topic seeding:
   - Add `--topic-seeds` flag to enable topic-only mode
   - Modify `run_clustering_test()` to load topic seeds when flag is set
   - Print loaded topics in the step 2 output

3. Add comment in `test_cluster.py` showing how to run with topics:
   ```python
   # Usage:
   #   .venv/bin/python -m src.cluster.test_cluster --algorithm kmeans --topic-seeds
   ```
</action>
<verify>
<automated>.venv/bin/python -m src.cluster.test_cluster --help 2>&1 | grep -q "topic-seeds"</automated>
</verify>
<done>
- Example config created
- `--topic-seeds` flag added to test driver
- Help text shows the new option
</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Config file → Python | User-provided YAML config parsed safely |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | Tampering | seed_topics.yaml | accept | Config file is user-controlled, not external input |
| T-quick-02 | DoS | embed.py | mitigate | Batch embedding prevents memory exhaustion from many topics |
</threat_model>

<verification>
- Unit tests pass: `.venv/bin/python -m pytest tests/unit/test_embed_topic_seeding.py -v`
- Test driver shows option: `.venv/bin/python -m src.cluster.test_cluster --help`
- Example config exists: `config/seed_topics.example.yaml`
</verification>

<success_criteria>
- Users can create `config/seed_topics.yaml` with topic names
- Topic names are embedded using the same model as accounts
- Topics work as KMeans initial centroids
- Topics can be used alone or combined with account seeds
- HDBSCAN gracefully ignores topic seeds (unsupervised mode)
</success_criteria>

<output>
After completion, create `.planning/quick/260418-fbc-add-topic-only-seeding-option-for-cluste/260418-fbc-SUMMARY.md`
</output>