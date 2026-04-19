"""Geographic clustering module — clusters accounts by location only.

This is a separate pass from topical clustering. Accounts get BOTH:
- A topical cluster (tech, health, politics, etc.)
- A geographic cluster (if they have a location signal)

X API lists allow multiple membership, so an account can be in:
- "Tech Founders" list (topical)
- "San Francisco" list (geographic)

Usage:
    from src.cluster.geo_cluster import geo_cluster_all
    result = geo_cluster_all()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans

from src.cluster.geo_preprocess import preprocess_location_for_embedding

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
GEO_CONFIDENCE_THRESHOLD = 0.55  # Minimum similarity to assign geographic cluster
GEO_MULTI_THRESHOLD = 0.70  # Threshold for additional geo cluster assignments


@dataclass
class GeoClusterResult:
    """Result of geographic clustering."""
    total_accounts: int
    geo_assigned: int  # Accounts with location strong enough to assign
    n_clusters: int
    assignments: dict[str, list[str]]  # username -> list of geo_cluster_names (multiple allowed)
    confidence_by_user: dict[str, list[float]]  # parallel to assignments


def load_geo_topics(config_path: Path | None = None) -> dict[str, np.ndarray]:
    """Load geographic topic seeds from YAML config.

    Returns dict mapping topic name to embedding array.
    """
    if config_path is None:
        config_path = Path("config/seed_geographies.yaml")

    if not config_path.exists():
        logger.warning("Geographic topics config not found: %s", config_path)
        return {}

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config or "topics" not in config:
        return {}

    topics = config["topics"]
    if not topics:
        return {}

    logger.info("Loading embeddings for %d geographic topics", len(topics))
    model = SentenceTransformer(EMBEDDING_MODEL)
    embeddings = model.encode(topics, normalize_embeddings=True)

    result = {}
    for i, topic in enumerate(topics):
        # Extract short name (first word or two before space)
        short_name = topic.split()[0] if " " not in topic else " ".join(topic.split()[:2])
        result[short_name] = embeddings[i : i + 1]

    return result


def extract_location_text(account: dict) -> str:
    """Extract and preprocess location text for embedding.

    Uses ONLY the location field (not entity_locs) because:
    - entity_locs contains places mentioned in bio text, not where the account is located
    - Including entity_locs dilutes the geographic signal with unrelated locations

    Preprocessing:
    - Expands airport codes (PVD → Providence Rhode Island)
    - Expands state abbreviations (RI → Rhode Island)
    - Expands city aliases (NYC → New York City)
    - Strips noise words

    Returns empty string if no location signal.
    """
    location = account.get("location", "")
    # Deliberately NOT using entity_locs - those are places mentioned in bio,
    # not where the account is located

    return preprocess_location_for_embedding(location, None)


def geo_cluster_all(
    cache_dir: str | Path = Path("data/enrichment"),
    output_dir: str | Path | None = None,
    min_confidence: float = GEO_CONFIDENCE_THRESHOLD,
) -> GeoClusterResult:
    """Run geographic clustering on all accounts.

    This is a separate pass from topical clustering. It assigns
    geographic cluster names based on location similarity to geo topics.

    Parameters
    ----------
    cache_dir : Path
        Directory with enrichment cache files.
    output_dir : Path | None
        Where to write updated cache files. Defaults to cache_dir.
    min_confidence : float
        Minimum cosine similarity to assign a geo cluster.

    Returns
    -------
    GeoClusterResult
    """
    cache_dir = Path(cache_dir)
    if output_dir is None:
        output_dir = cache_dir
    else:
        output_dir = Path(output_dir)

    # Load geographic topic embeddings
    geo_topics = load_geo_topics()
    if not geo_topics:
        raise ValueError("No geographic topics loaded. Check config/seed_geographies.yaml")

    topic_names = list(geo_topics.keys())
    topic_centroids = np.vstack([geo_topics[name] for name in topic_names])

    logger.info("Loaded %d geographic topics: %s", len(topic_names), topic_names)

    # Load all accounts (track source file for writing back)
    accounts = []  # List of (account_data, source_path)
    for fpath in sorted(cache_dir.glob("*.json")):
        if fpath.stem in ("suspended", "protected", "errors"):
            continue
        try:
            data = json.load(open(fpath))
            accounts.append((data, fpath))
        except Exception as e:
            logger.warning("Could not load %s: %s", fpath, e)

    if not accounts:
        raise ValueError("No account cache files found")

    logger.info("Loaded %d accounts", len(accounts))

    # Extract location texts and embed
    model = SentenceTransformer(EMBEDDING_MODEL)

    location_texts = []
    valid_accounts = []  # List of (account_data, source_path)
    for acct, src_path in accounts:
        loc_text = extract_location_text(acct)
        if loc_text:
            location_texts.append(loc_text)
            valid_accounts.append((acct, src_path))

    if not location_texts:
        logger.warning("No accounts have location data")
        return GeoClusterResult(
            total_accounts=len(accounts),
            geo_assigned=0,
            n_clusters=0,
            assignments={},
            confidence_by_user={},
        )

    logger.info("Embedding %d location strings", len(location_texts))
    loc_embeddings = model.encode(location_texts, normalize_embeddings=True)

    # Compute similarity to each geo topic centroid
    # similarity shape: (n_accounts, n_topics)
    similarities = loc_embeddings @ topic_centroids.T

    # Assign each account to ALL matching geo topics above threshold
    # This allows accounts to be in multiple geographic lists
    assignments: dict[str, list[str]] = {}
    confidence_by_user: dict[str, list[float]] = {}

    for i, (acct, src_path) in enumerate(valid_accounts):
        username = acct.get("username", f"acct_{i}")

        # Find all topics above threshold
        assigned_topics = []
        assigned_scores = []
        for topic_idx, sim in enumerate(similarities[i]):
            sim_val = float(sim)
            if sim_val >= min_confidence:
                assigned_topics.append(topic_names[topic_idx])
                assigned_scores.append(sim_val)

        if assigned_topics:
            assignments[username] = assigned_topics
            confidence_by_user[username] = assigned_scores

            # Write back to the ORIGINAL source file (not username-based path)
            acct["geo_clusters"] = assigned_topics  # plural - list
            acct["geo_confidences"] = assigned_scores
            json.dump(acct, open(src_path, "w"), indent=2)

    # Count total assignments (not just accounts)
    total_assignments = sum(len(topics) for topics in assignments.values())

    logger.info(
        "Assigned %d accounts to geographic clusters (%d total assignments, threshold=%.2f)",
        len(assignments),
        total_assignments,
        min_confidence,
    )

    return GeoClusterResult(
        total_accounts=len(accounts),
        geo_assigned=len(assignments),
        n_clusters=len(set(t for topics in assignments.values() for t in topics)),
        assignments=assignments,
        confidence_by_user=confidence_by_user,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = geo_cluster_all()
    print(f"\nGeographic clustering complete:")
    print(f"  Total accounts: {result.total_accounts}")
    print(f"  Assigned to geo clusters: {result.geo_assigned}")
    print(f"  Geographic clusters used: {result.n_clusters}")