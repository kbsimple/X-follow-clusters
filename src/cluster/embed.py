"""Embedding and semi-supervised clustering for X accounts.

Pipeline:
1. Load enriched account data from data/enrichment/*.json
2. Build text representation from bio/location/category/pinned_tweet
3. Embed all accounts using sentence-transformers/all-MiniLM-L6-v2
4. Run constrained K-Means (or HDBSCAN) seeded with category anchors
5. Compute silhouette scores and size histogram
6. Write cluster assignments back to cache files
"""

from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml

try:
    import hdbscan
    _HDBSCAN_AVAILABLE = True
except ImportError:
    _HDBSCAN_AVAILABLE = False

from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_samples

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output dimension
MIN_TEXT_ACCOUNTS = 10  # minimum accounts with non-empty text to proceed

# Module-level model singleton for tweet embeddings
_tweet_embedding_model: SentenceTransformer | None = None


def _get_tweet_embedding_model() -> SentenceTransformer:
    """Get or create the SentenceTransformer model singleton for tweet embeddings."""
    global _tweet_embedding_model
    if _tweet_embedding_model is None:
        _tweet_embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _tweet_embedding_model


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ClusterResult:
    """Return type for cluster_all()."""

    total_accounts: int
    n_clusters: int
    labels: np.ndarray
    silhouette_by_cluster: dict[int, float]
    size_histogram: dict[str, Any]
    central_members_by_cluster: dict[int, list[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def get_text_for_embedding(account: dict) -> str:
    """Build a text string from an account dict for embedding.

    Joins description + location + professional_category + pinned_tweet_text
    with " | " separator. Empty fields are skipped.

    Per D-16: entity fields are appended in format:
        | Org: X | Loc: Y | Title: Z
    Example: "AI researcher | San Francisco | Engineering | Pinned tweet | Org: DeepMind | Loc: London | Title: Research Scientist"

    Entity fields (entity_orgs, entity_locs, entity_titles) are added from
    Phase 8 entity extraction. Empty entity lists produce no segments.

    Parameters
    ----------
    account : dict
        Account dict loaded from data/enrichment/{account_id}.json.
        Expected keys: description, location, professional_category, pinned_tweet_text
        Optional: entity_orgs, entity_locs, entity_titles (from Phase 8 extraction)

    Returns
    -------
    str
        Concatenated text, e.g. "AI researcher | San Francisco | Engineering | Hello world | Org: DeepMind | Loc: London | Title: Research Scientist"
        Returns "" if all fields are empty/missing.
    """
    parts = [
        account.get("description", ""),
        account.get("location", ""),
        account.get("professional_category", ""),
        account.get("pinned_tweet_text", ""),
    ]

    # Per D-16: append entity fields as | Org: X | Loc: Y | Title: Z
    entity_orgs = account.get("entity_orgs", [])
    entity_locs = account.get("entity_locs", [])
    entity_titles = account.get("entity_titles", [])

    if entity_orgs:
        parts.append("Org: " + ", ".join(entity_orgs))
    if entity_locs:
        parts.append("Loc: " + ", ".join(entity_locs))
    if entity_titles:
        parts.append("Title: " + ", ".join(entity_titles))

    # Include recent tweets text for embedding
    recent_tweets_text = account.get("recent_tweets_text", "")
    if recent_tweets_text:
        parts.append(recent_tweets_text)

    cleaned = [p.strip() for p in parts if p and p.strip()]
    return " | ".join(cleaned)


# ---------------------------------------------------------------------------
# Tweet Embedding (Topical Dimension)
# ---------------------------------------------------------------------------

def create_tweet_embedding(account: dict) -> list[float] | None:
    """Create a dedicated embedding from recent tweets for topical clustering.

    This is a separate embedding dimension from the main account embedding.
    It captures what the account posts about (topical similarity) rather than
    who they are (identity similarity from bio/location).

    Parameters
    ----------
    account : dict
        Account dict with 'recent_tweets_text' field.

    Returns
    -------
    list[float] | None
        384-dimensional embedding as a list (JSON-serializable), or None if
        no tweet text available.
    """
    tweet_text = account.get("recent_tweets_text", "")
    if not tweet_text or not tweet_text.strip():
        return None

    model = _get_tweet_embedding_model()
    embedding = model.encode(tweet_text, normalize_embeddings=True)
    return embedding.tolist()


def store_tweet_embedding(
    account_id: str,
    cache_dir: Path | str = Path("data/enrichment"),
) -> list[float] | None:
    """Create and store a tweet embedding for an account.

    Loads the account cache file, creates the tweet embedding, and stores
    it back to the cache with key 'tweet_embedding'.

    Parameters
    ----------
    account_id : str
        Account ID (cache file stem).
    cache_dir : Path | str
        Directory containing enrichment cache files.

    Returns
    -------
    list[float] | None
        The stored embedding, or None if no tweet text available.
    """
    cache_dir = Path(cache_dir)
    cache_path = cache_dir / f"{account_id}.json"

    if not cache_path.exists():
        return None

    with open(cache_path, encoding="utf-8") as f:
        account = json.load(f)

    embedding = create_tweet_embedding(account)
    if embedding is None:
        return None

    account["tweet_embedding"] = embedding

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(account, f, indent=2)

    return embedding


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_accounts(
    accounts: list[dict],
    model_name: str = EMBEDDING_MODEL,
    batch_size: int = 64,
    cache_path: Path | None = None,
) -> tuple[np.ndarray, list[dict]]:
    """Embed account text fields using a sentence-transformer model.

    Embeddings are cached to ``cache_path`` (data/embeddings.npy) on first run.
    On subsequent runs the cache is loaded if it exists and the count matches.

    Parameters
    ----------
    accounts : list[dict]
        List of account dicts with text fields.
    model_name : str
        HuggingFace model name for SentenceTransformer.
    batch_size : int
        Encoding batch size.
    cache_path : Path | None
        Path to cache file. Defaults to data/embeddings.npy.

    Returns
    -------
    tuple[np.ndarray, list[dict]]
        embedding matrix of shape (n_accounts, 384), and the filtered
        accounts list (accounts with non-empty text).

    Raises
    ------
    ValueError
        If fewer than MIN_TEXT_ACCOUNTS accounts have non-empty text.
    """
    if cache_path is None:
        cache_path = Path("data/embeddings.npy")

    # Build (text, account) pairs, filtering empty texts
    texts = []
    valid_accounts = []
    for acct in accounts:
        txt = get_text_for_embedding(acct)
        if txt:
            texts.append(txt)
            valid_accounts.append(acct)

    if len(valid_accounts) < MIN_TEXT_ACCOUNTS:
        raise ValueError(
            f"Only {len(valid_accounts)} accounts have non-empty text for embedding. "
            f"Need at least {MIN_TEXT_ACCOUNTS}. "
            "Ensure data/enrichment/*.json files exist and contain bio/location data."
        )

    # Check cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    usernames = [a["username"] for a in valid_accounts]

    if cache_path.exists():
        sidecar_path = cache_path.with_suffix(".sidecar.json")
        if sidecar_path.exists():
            cached_usernames: list[str] = json.load(open(sidecar_path))
            cached_emb: np.ndarray = np.load(cache_path)
            if len(cached_usernames) == len(usernames) and cached_usernames == usernames:
                logger.info("Loaded embeddings from cache: %s", cache_path)
                return cached_emb, valid_accounts

    # Compute fresh
    logger.info("Loading model %s …", model_name)
    model = SentenceTransformer(model_name)
    logger.info("Encoding %d accounts in batches of %d …", len(valid_accounts), batch_size)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    # Save cache
    np.save(cache_path, embeddings)
    json.dump(usernames, open(cache_path.with_suffix(".sidecar.json"), "w"))
    logger.info("Saved embeddings to cache: %s", cache_path)

    return embeddings, valid_accounts


# ---------------------------------------------------------------------------
# Seed embedding loading
# ---------------------------------------------------------------------------

def load_seed_embeddings(
    seed_accounts: dict[str, list[str]],
    cache_dir: Path,
    embedding_cache: Path | None = None,
) -> dict[str, np.ndarray]:
    """Load embedding vectors for seed accounts by username.

    Uses the embedding cache (data/embeddings.npy) if available;
    otherwise loads each account's enrichment JSON and re-embeds just
    that account's text.

    Parameters
    ----------
    seed_accounts : dict[str, list[str]]
        Mapping from category name to list of usernames.
    cache_dir : Path
        Path to enrichment cache (data/enrichment).
    embedding_cache : Path | None
        Path to embeddings.npy cache.

    Returns
    -------
    dict[str, np.ndarray]
        Mapping from category name to ndarray of shape (n_seeds_in_category, 384).
    """
    if embedding_cache is None:
        embedding_cache = Path("data/embeddings.npy")

    usernames_to_embed: list[tuple[str, str, dict]] = []  # (category, username, account_dict)
    all_accounts: list[dict] = []
    category_indices: dict[str, list[int]] = {cat: [] for cat in seed_accounts}

    # Try to load from enrichment cache + embedding cache first
    if embedding_cache.exists():
        sidecar_path = embedding_cache.with_suffix(".sidecar.json")
        if sidecar_path.exists():
            cached_usernames: list[str] = json.load(open(sidecar_path))
            cached_emb: np.ndarray = np.load(embedding_cache)
            username_to_idx = {u: i for i, u in enumerate(cached_usernames)}

            for cat, usernames in seed_accounts.items():
                for uname in usernames:
                    if uname in username_to_idx:
                        idx = username_to_idx[uname]
                        category_indices[cat].append(idx)
                    else:
                        # Not in embedding cache — load from enrichment JSON
                        acct_file = cache_dir / f"{uname}.json"
                        if not acct_file.exists():
                            acct_file = cache_dir / f"{uname}.json"
                        # Search by username in cache
                        found = False
                        for f in cache_dir.glob("*.json"):
                            if f.stem in ("suspended", "protected", "errors"):
                                continue
                            try:
                                d = json.load(open(f))
                                if d.get("username") == uname:
                                    usernames_to_embed.append((cat, uname, d))
                                    found = True
                                    break
                            except Exception:
                                continue
                        if not found:
                            warnings.warn(f"Seed username '{uname}' not found in enrichment cache. It will be skipped.")
            # Rebuild embeddings using cached array
            result: dict[str, np.ndarray] = {}
            for cat in seed_accounts:
                indices = category_indices.get(cat, [])
                if indices:
                    result[cat] = cached_emb[indices]
                else:
                    result[cat] = np.empty((0, EMBEDDING_DIM))
            # Embed any missing seeds
            if usernames_to_embed:
                texts = [get_text_for_embedding(d) for _, _, d in usernames_to_embed]
                model = SentenceTransformer(EMBEDDING_MODEL)
                new_embs = model.encode(texts, normalize_embeddings=True)
                for i, (cat, _, _) in enumerate(usernames_to_embed):
                    # Append to result[cat]
                    if result[cat].shape[0] == 0:
                        result[cat] = new_embs[i : i + 1]
                    else:
                        result[cat] = np.vstack([result[cat], new_embs[i : i + 1]])
            return result

    # No cache — load from enrichment JSONs directly
    result = {}
    for cat, usernames in seed_accounts.items():
        vecs = []
        for uname in usernames:
            acct_file = cache_dir / f"{uname}.json"
            if not acct_file.exists():
                # Search by username
                found = False
                for f in cache_dir.glob("*.json"):
                    if f.stem in ("suspended", "protected", "errors"):
                        continue
                    try:
                        d = json.load(open(f))
                        if d.get("username") == uname:
                            acct_file = f
                            found = True
                            break
                    except Exception:
                        continue
                if not found:
                    warnings.warn(f"Seed username '{uname}' not found in enrichment cache.")
                    continue
            try:
                d = json.load(open(acct_file))
            except Exception as e:
                warnings.warn(f"Could not load {acct_file}: {e}")
                continue
            txt = get_text_for_embedding(d)
            if not txt:
                continue
            vecs.append(txt)

        if vecs:
            model = SentenceTransformer(EMBEDDING_MODEL)
            vecs = model.encode(vecs, normalize_embeddings=True)
            result[cat] = vecs
        else:
            result[cat] = np.empty((0, EMBEDDING_DIM))

    return result


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def compute_clusters(
    embeddings: np.ndarray,
    seed_embeddings_by_category: dict[str, np.ndarray],
    min_size: int = 5,
    max_size: int = 50,
    algorithm: str = "kmeans",
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Run constrained clustering on account embeddings.

    CLUSTER-02: algorithm parameter supports "kmeans" (default, semi-supervised
    with seed centroids) or "hdbscan" (discovery mode).

    Parameters
    ----------
    embeddings : np.ndarray
        Array of shape (n_accounts, 384).
    seed_embeddings_by_category : dict[str, np.ndarray]
        Seed centroid embeddings keyed by category name.
    min_size : int
        Minimum cluster size (default 5). Clusters below this are flagged.
    max_size : int
        Maximum cluster size (default 50). Clusters above this are rebalanced.
    algorithm : str
        "kmeans" (default) or "hdbscan".

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]
        (labels, seed_centroids, final_centroids, category_names)

    Raises
    ------
    ImportError
        If algorithm="hdbscan" but hdbscan is not installed.
    ValueError
        If algorithm is unknown.
    """
    if algorithm == "kmeans":
        categories = list(seed_embeddings_by_category.keys())
        seed_centroids = np.vstack(
            np.mean(seed_embs, axis=0) for seed_embs in seed_embeddings_by_category.values()
            if seed_embs.shape[0] > 0
        )
        n_seed_categories = len(seed_centroids)
        n_clusters = n_seed_categories + 3  # seeds + 3 discovered

        if embeddings.shape[0] < n_clusters:
            n_clusters = embeddings.shape[0]
            warnings.warn(
                f"Fewer accounts ({embeddings.shape[0]}) than clusters ({n_clusters}). "
                "Reducing cluster count."
            )

        logger.info(
            "Running KMeans with n_clusters=%d (seed_centroids + 3 discovered), "
            "init=seed_centroids, n_init=1, random_state=42",
            n_clusters,
        )
        kmeans = KMeans(
            n_clusters=n_clusters,
            init=seed_centroids,
            n_init=1,
            random_state=42,
            algorithm="elkan",
        )
        labels = kmeans.labels_
        final_centroids = kmeans.cluster_centers_

        # Category names: seed categories first, then discovered
        category_names = categories + [f"discovered_{i}" for i in range(n_clusters - n_seed_categories)]

    elif algorithm == "hdbscan":
        if not _HDBSCAN_AVAILABLE:
            raise ImportError(
                "hdbscan is not installed. Install it with: pip install hdbscan>=0.8.0 "
                "(optional dependency for discovery mode)"
            )
        logger.info("Running HDBSCAN (min_cluster_size=5, metric='euclidean') …")
        clusterer = hdbscan.HDBSCAN(min_cluster_size=min_size, metric="euclidean", prediction_data=True)
        labels = clusterer.labels_

        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        categories = list(seed_embeddings_by_category.keys())
        category_names = categories + [f"discovered_{i}" for i in range(n_clusters - len(categories))]

        # Compute centroids from member embeddings
        final_centroids = np.zeros((n_clusters, EMBEDDING_DIM))
        seed_centroids = np.zeros((len(categories), EMBEDDING_DIM))
        for cid in range(n_clusters):
            member_mask = labels == cid
            if member_mask.sum() > 0:
                final_centroids[cid] = np.mean(embeddings[member_mask], axis=0)

        # Seed centroids still computed for silhouette comparison
        for i, cat in enumerate(categories):
            if seed_embeddings_by_category[cat].shape[0] > 0:
                seed_centroids[i] = np.mean(seed_embeddings_by_category[cat], axis=0)

    else:
        raise ValueError(f"Unknown algorithm '{algorithm}'. Use 'kmeans' or 'hdbscan'.")

    # Post-hoc size enforcement
    label_counts: dict[int, int] = {}
    for lbl in labels:
        label_counts[lbl] = label_counts.get(lbl, 0) + 1

    logger.info("Initial cluster sizes: %s", dict(sorted(label_counts.items())))

    # Flag clusters under min_size
    small_clusters = [lbl for lbl, cnt in label_counts.items() if cnt < min_size]
    if small_clusters:
        logger.warning("Clusters with fewer than %d members (flagged): %s", min_size, small_clusters)

    # Rebalance clusters over max_size
    for lbl in list(label_counts.keys()):
        if label_counts[lbl] > max_size:
            excess = label_counts[lbl] - max_size
            member_mask = labels == lbl
            member_indices = np.where(member_mask)[0]
            member_embeddings = embeddings[member_mask]

            # Find farthest members from centroid
            centroid = final_centroids[lbl]
            distances = np.linalg.norm(member_embeddings - centroid, axis=1)
            farthest = np.argsort(distances)[-excess:]

            # Reassign to nearest neighbour cluster
            for idx in farthest:
                acct_idx = member_indices[idx]
                dists_to_others = np.linalg.norm(
                    embeddings[acct_idx] - final_centroids, axis=1
                )
                dists_to_others[lbl] = np.inf
                nearest = np.argmin(dists_to_others)
                labels[acct_idx] = nearest
                label_counts[lbl] -= 1
                label_counts[nearest] = label_counts.get(nearest, 0) + 1
                final_centroids[nearest] = (
                    final_centroids[nearest] * (label_counts[nearest] - 1)
                    + embeddings[acct_idx]
                ) / label_counts[nearest]

    logger.info("Final cluster sizes after rebalancing: %s", dict(sorted(label_counts.items())))

    return labels, seed_centroids, final_centroids, category_names


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def compute_silhouette_scores(
    embeddings: np.ndarray,
    labels: np.ndarray,
) -> dict[int, float]:
    """Compute mean silhouette score per cluster.

    Uses sklearn.metrics.silhouette_samples for per-sample scores,
    then averages within each cluster.

    Parameters
    ----------
    embeddings : np.ndarray
        Array of shape (n_accounts, 384).
    labels : np.ndarray
        Cluster label for each embedding.

    Returns
    -------
    dict[int, float]
        Mapping from cluster_id -> mean silhouette score for that cluster.
    """
    if len(set(labels)) < 2:
        # Cannot compute silhouette with <2 clusters
        return {lbl: 1.0 for lbl in labels}

    scores = silhouette_samples(embeddings, labels)
    result: dict[int, float] = {}
    for lbl in set(labels):
        mask = labels == lbl
        if mask.sum() > 0:
            result[lbl] = float(np.mean(scores[mask]))
    return result


def generate_size_histogram(labels: np.ndarray) -> dict[str, Any]:
    """Generate a cluster size histogram summary.

    Parameters
    ----------
    labels : np.ndarray
        Cluster label for each account.

    Returns
    -------
    dict[str, Any]
        Histogram summary with keys:
        - counts: list of per-cluster member counts
        - bins: list of cluster IDs
        - total_clusters: number of clusters
        - clusters_under_5: count of clusters with < 5 members
        - pct_under_5: percentage of clusters under 5 members
    """
    from collections import Counter

    counts = Counter(labels)
    sorted_counts = sorted(counts.items())

    count_values = [c for _, c in sorted_counts]
    bin_labels = [l for l, _ in sorted_counts]

    clusters_under_5 = sum(1 for c in count_values if c < 5)
    total = len(count_values)
    pct_under_5 = clusters_under_5 / total if total > 0 else 0.0

    return {
        "counts": count_values,
        "bins": bin_labels,
        "total_clusters": total,
        "clusters_under_5": clusters_under_5,
        "pct_under_5": pct_under_5,
    }


# ---------------------------------------------------------------------------
# Central members
# ---------------------------------------------------------------------------

def _find_central_members(
    embeddings: np.ndarray,
    labels: np.ndarray,
    final_centroids: np.ndarray,
    top_n: int = 5,
) -> dict[int, list[str]]:
    """Find the top-N most-central members (lowest distance to centroid) per cluster."""
    from collections import defaultdict

    cluster_to_members: dict[int, list[int]] = defaultdict(list)
    for idx, lbl in enumerate(labels):
        cluster_to_members[lbl].append(idx)

    result: dict[int, list[str]] = {}
    for lbl, member_indices in cluster_to_members.items():
        if not member_indices:
            result[lbl] = []
            continue
        member_embeddings = embeddings[member_indices]
        centroid = final_centroids[lbl]
        distances = np.linalg.norm(member_embeddings - centroid, axis=1)
        closest = np.argsort(distances)[:top_n]
        # Return original account indices — caller maps to usernames
        result[lbl] = [member_indices[i] for i in closest]

    return result


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def cluster_all(
    cache_dir: str | Path = Path("data/enrichment"),
    output_dir: str | Path | None = None,
    algorithm: str = "kmeans",
    dry_run: bool = False,
) -> ClusterResult:
    """Run the full embedding + clustering pipeline.

    Parameters
    ----------
    cache_dir : str | Path
        Directory containing data/enrichment/{account_id}.json files.
    output_dir : str | Path | None
        Directory to write updated cache files. Defaults to cache_dir (in-place).
    algorithm : str
        "kmeans" (default, semi-supervised) or "hdbscan" (discovery).
    dry_run : bool
        If True, validate pipeline runs without requiring live data files.
        Useful for verifying the implementation before enrichment data exists.

    Returns
    -------
    ClusterResult

    Raises
    ------
    ValueError
        If data/enrichment/ does not exist or is empty (and dry_run is False).
    """
    cache_dir = Path(cache_dir)
    if output_dir is None:
        output_dir = cache_dir
    else:
        output_dir = Path(output_dir)

    # Validate data directory exists (unless dry_run)
    if not dry_run:
        if not cache_dir.exists():
            raise ValueError(
                f"Cache directory {cache_dir} does not exist. "
                "Run enrichment first to produce data/enrichment/*.json files."
            )
        enrichment_files = [
            f for f in cache_dir.glob("*.json")
            if f.stem not in ("suspended", "protected", "errors")
        ]
        if not enrichment_files:
            raise ValueError(
                f"No enrichment files found in {cache_dir}. "
                "Run enrichment first to produce data/enrichment/*.json files."
            )

    # Load seed accounts config
    seed_config_path = Path("config/seed_accounts.yaml")
    if not seed_config_path.exists():
        raise ValueError(
            f"Seed accounts config not found: {seed_config_path}. "
            "Create config/seed_accounts.yaml with seed category usernames."
        )
    with open(seed_config_path) as f:
        seed_config = yaml.safe_load(f)

    seed_accounts: dict[str, list[str]] = {}
    for cat, cat_data in seed_config.items():
        if isinstance(cat_data, dict) and "examples" in cat_data:
            seed_accounts[cat] = cat_data["examples"]
        elif isinstance(cat_data, list):
            seed_accounts[cat] = cat_data

    # Load all account cache files
    if dry_run:
        logger.info("dry_run=True — skipping live data loading")
        # Return a minimal result to validate the pipeline structure
        dummy_emb = np.zeros((2, EMBEDDING_DIM))
        dummy_labels = np.array([0, 1])
        return ClusterResult(
            total_accounts=2,
            n_clusters=2,
            labels=dummy_labels,
            silhouette_by_cluster={0: 1.0, 1: 1.0},
            size_histogram={"counts": [1, 1], "bins": [0, 1], "total_clusters": 2, "clusters_under_5": 0, "pct_under_5": 0.0},
            central_members_by_cluster={0: [0], 1: [1]},
        )

    accounts: list[dict] = []
    for fpath in sorted(cache_dir.glob("*.json")):
        if fpath.stem in ("suspended", "protected", "errors"):
            continue
        try:
            d = json.load(open(fpath))
            accounts.append(d)
        except Exception as e:
            logger.warning("Could not load %s: %s", fpath, e)

    if not accounts:
        raise ValueError(f"No valid account cache files found in {cache_dir}.")

    logger.info("Loaded %d account cache files", len(accounts))

    # Embed accounts
    embeddings, valid_accounts = embed_accounts(accounts)
    logger.info("Embedded %d accounts with valid text", len(valid_accounts))

    # Map valid_accounts index back to original accounts list for username lookups
    valid_username_to_idx = {a["username"]: i for i, a in enumerate(valid_accounts)}

    # Load seed embeddings
    seed_embeddings = load_seed_embeddings(seed_accounts, cache_dir)

    # Compute clusters
    labels, seed_centroids, final_centroids, category_names = compute_clusters(
        embeddings,
        seed_embeddings,
        algorithm=algorithm,
    )

    # Silhouette scores
    silhouette_by_cluster = compute_silhouette_scores(embeddings, labels)
    for cid, score in silhouette_by_cluster.items():
        if score < 0.3:
            logger.warning(f"Cluster {cid} has low silhouette score {score:.3f} — cluster may be poorly defined")

    # Size histogram
    size_histogram = generate_size_histogram(labels)
    if size_histogram["pct_under_5"] > 0.5:
        logger.warning(f"Over 50% of clusters have fewer than 5 members — clustering may be too fragmented")

    # Central members per cluster
    central_idx_by_cluster = _find_central_members(embeddings, labels, final_centroids, top_n=5)
    # Map indices back to usernames
    central_members_by_cluster: dict[int, list[str]] = {}
    for lbl, idx_list in central_idx_by_cluster.items():
        central_members_by_cluster[lbl] = [
            valid_accounts[idx]["username"] for idx in idx_list if idx < len(valid_accounts)
        ]

    # Build cluster_id -> name mapping (category name for seed clusters, "discovered_N" for others)
    n_seed_cats = len(seed_accounts)
    cluster_name_by_id: dict[int, str] = {}
    for i, cat in enumerate(seed_accounts.keys()):
        if i < len(labels):
            # Find which cluster ID corresponds to seed category i (by centroid proximity)
            if seed_embeddings[cat].shape[0] > 0:
                seed_cent = np.mean(seed_embeddings[cat], axis=0)
                dists = np.linalg.norm(final_centroids - seed_cent, axis=1)
                closest = np.argmin(dists)
                cluster_name_by_id[closest] = cat
    # Fill in discovered clusters
    discovered_count = 0
    for cid in range(len(final_centroids)):
        if cid not in cluster_name_by_id:
            cluster_name_by_id[cid] = f"discovered_{discovered_count}"
            discovered_count += 1

    # Write cluster assignments back to cache files
    account_idx_by_username: dict[str, int] = {a["username"]: i for i, a in enumerate(valid_accounts)}

    for acct in accounts:
        uname = acct.get("username")
        if uname not in account_idx_by_username:
            continue
        idx = account_idx_by_username[uname]
        lbl = int(labels[idx])
        acct["cluster_id"] = lbl
        acct["cluster_name"] = cluster_name_by_id.get(lbl, f"cluster_{lbl}")
        acct["silhouette_score"] = silhouette_by_cluster.get(lbl, 0.0)
        acct["is_seed_category"] = lbl in [
            i for i, name in cluster_name_by_id.items() if name in seed_accounts
        ]
        acct["central_member_usernames"] = central_members_by_cluster.get(lbl, [])

        out_path = output_dir / f"{uname}.json"
        json.dump(acct, open(out_path, "w"), indent=2)

    return ClusterResult(
        total_accounts=len(valid_accounts),
        n_clusters=len(final_centroids),
        labels=labels,
        silhouette_by_cluster=silhouette_by_cluster,
        size_histogram=size_histogram,
        central_members_by_cluster=central_members_by_cluster,
    )
