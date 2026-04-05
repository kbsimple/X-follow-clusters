# Phase 4: NLP Clustering - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Cluster followers into meaningful groups using bio text embeddings. Reads enriched account data from `data/enrichment/{account_id}.json` (Phase 2 API data + Phase 3 scraped data). Produces cluster assignments stored alongside enrichment data. Review flow (Phase 5) handles user approval before list creation.

</domain>

<decisions>
## Implementation Decisions

### Input Text for Embeddings
- **D-01:** Embed the concatenation of all available text fields: bio + location + professional_category + pinned_tweet_text (if available), joined with " | " separator
- **Rationale:** Maximizes signal for clustering. Scraped fields from Phase 3 add richness beyond just the bio.

### Seed Category Anchoring
- **D-02:** Seeds as semi-supervised anchors (constrained K-Means): run K-Means with k = len(seed_categories), initialize cluster centroids using seed category member embeddings, then run standard K-Means for remaining members
- **Rationale:** Ensures seed categories appear in results while allowing algorithm to discover structure. Hard enough to enforce seeds, flexible enough to handle members that don't fit seeds.

### Seed Categories
- **D-03:** Four seed categories: Geographic (Bay Area, NYC, etc.), Occupation (VC, Engineer, Financier), Political Action (campaigns, evangelism), Entertainment (sports, humor)
- **Implementation:** Each seed category starts with 3-5 representative account usernames hardcoded; embeddings for those accounts are fetched from Phase 2 cache and used to initialize centroids
- **Rationale:** User-specified in requirements; gives initial structure without dictating all results

### Cluster Count
- **D-04:** Start with seed count (4) + discovered count. After initial clustering, compute silhouette scores. If overall score < 0.3, allow algorithm to split/merge clusters. Final k is seed_k + discovered_k.
- **Rationale:** Balances user seeds with data-driven discovery. Silhouette guard prevents meaningless splits.

### LLM Naming
- **D-05:** Feed top-5 most-central member bios (by cosine similarity to centroid) to the naming LLM. Include the centroid embedding's nearest neighbors as context. Ask for a short descriptive name (3-5 words).
- **D-06:** Use the same X API credentials/environment from Phase 1 for LLM calls (Anthropic or OpenAI — planner picks based on what's configured)

### Cluster Size Constraints
- **D-07:** Hard minimum 5, hard maximum 50. Clusters outside bounds flagged for manual review in Phase 5.
- **Rationale:** User-specified in requirements; X API lists have 5,000 max but user prefers 5-50

### Metrics Reporting
- **D-08:** Report cluster size histogram before Phase 5 review. Flag if >50% of clusters have fewer than 5 members.
- **D-09:** Compute silhouette score per cluster. Flag clusters with score < 0.3.

### Claude's Discretion
- Exact embedding model (all-MiniLM-L6-v2 as default — can upgrade if quality issues)
- Clustering algorithm: HDBSCAN vs K-Means (K-Means preferred for seed anchoring; HDBSCAN for discovering extra clusters)
- How to split/merge clusters that violate size constraints
- Batch size for embedding generation (account for rate limits with local model)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 2-3 Artifacts
- `src/enrich/enrich.py` — reads enrichment cache, pattern for orchestrating batch processing
- `src/enrich/api_client.py` — cache file structure (`data/enrichment/{account_id}.json`)
- `src/scrape/__init__.py` — `scrape_all()`, ScrapeResult (Phase 3 integration)

### Requirements
- `.planning/REQUIREMENTS.md` — CLUSTER-01 through CLUSTER-08

### Phase 4 Success Criteria (from ROADMAP)
- `sentence-transformers` (`all-MiniLM-L6-v2`) for embeddings
- HDBSCAN or K-Means (configurable)
- 5-50 members per cluster; violations flagged for manual review
- LLM-generated cluster names from member profiles
- Seed categories: Geographic, Occupation, Political Action, Entertainment + discover more
- Cluster size histogram; warning if >50% clusters have <5 members
- Silhouette score; flag if <0.3

</canonical_refs>

<codebase_context>
## Existing Code Insights

### Reusable Assets
- `src/enrich/enrich.py`: `EnrichmentProcessor.enrich_all()` — pattern for batch orchestration with progress reporting
- `src/enrich/rate_limiter.py`: `ExponentialBackoff` class — available for any rate-limited calls (LLM API)
- `data/enrichment/{account_id}.json`: Per-account cache files containing all enriched + scraped fields

### Established Patterns
- Immediate caching to disk after each operation
- Error collection and continuation (from Phase 2)
- Result dataclass with counts returned to caller (ScrapeResult pattern)

### Integration Points
- Input: `data/enrichment/{account_id}.json` files (867 accounts, all phases 2-3 data)
- Output: Updated same JSON files with `cluster_id`, `cluster_name`, `cluster_category` fields added
- Next phase: Phase 5 reads clustered data for review workflow

</codebase_context>

<specifics>
## Specific Ideas

- 867 accounts to cluster
- Cluster names should be descriptive: not just "Tech" but "Bay Area Tech Founders" or "NYC Finance"
- Phase 5 review needs to see WHY a cluster was named what it was (central members, key terms)
- Phase 3 scraped fields (professional_category, pinned_tweet_text) add signal beyond raw bio

</specifics>

<deferred>
## Deferred Ideas

- Bot/fake account detection (CLUSTER in v2)
- Account activity scoring (CLUSTER in v2)
- Network-based clustering via follower overlap (CLUSTER in v2)
- Historical follower tracking (CLUSTER in v2)

</deferred>

---

*Phase: 04-nlp-clustering*
*Context gathered: 2026-04-05 (via --auto discuss-phase)*
