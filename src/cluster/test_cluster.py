"""Test driver script for the clustering pipeline.

A quick manual testing script that:
1. Loads enriched account data from cache
2. Auto-generates seed categories from account data
3. Runs embedding and clustering
4. Shows what lists would be created

Usage:
    .venv/bin/python -m src.cluster.test_cluster

Or with custom options:
    .venv/bin/python -m src.cluster.test_cluster --max-accounts 50 --algorithm hdbscan
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.WARNING,  # Reduce noise from sentence-transformers
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_enriched_accounts(cache_dir: Path, max_accounts: int | None = None) -> list[dict]:
    """Load enriched accounts from cache directory.

    Args:
        cache_dir: Directory containing enrichment JSON files.
        max_accounts: Maximum accounts to load (None = all).

    Returns:
        List of account dicts.
    """
    accounts = []
    json_files = sorted(cache_dir.glob("*.json"))

    for fpath in json_files:
        if fpath.stem in ("suspended", "protected", "errors"):
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                account = json.load(f)
            if account.get("username"):
                accounts.append(account)
        except Exception as e:
            print(f"Warning: Could not load {fpath}: {e}")

    if max_accounts:
        accounts = accounts[:max_accounts]

    return accounts


def auto_generate_seeds(accounts: list[dict], seeds_per_category: int = 3) -> dict[str, list[str]]:
    """Auto-generate seed categories based on account patterns.

    Creates categories based on common keywords in bios/locations.

    Args:
        accounts: List of account dicts.
        seeds_per_category: Number of seed accounts per category.

    Returns:
        Dict mapping category name to list of seed usernames.
    """
    # Define patterns for auto-categorization
    patterns = {
        "ai_tech": ["ai", "ml", "machine learning", "engineer", "software", "developer", "tech", "startup", "founder", "cto", "data"],
        "science_research": ["research", "scientist", "phd", "professor", "university", "academic", "lab"],
        "media_journalism": ["journalist", "writer", "editor", "news", "media", "reporter", "author"],
        "business_finance": ["investor", "vc", "ceo", "founder", "entrepreneur", "finance", "capital"],
        "politics_activism": ["politics", "activist", "campaign", "policy", "government", "advocate"],
    }

    # Assign accounts to categories based on patterns
    category_accounts: dict[str, list[tuple[str, float]]] = {cat: [] for cat in patterns}

    for account in accounts:
        username = account.get("username", "")
        bio = (account.get("description", "") or "").lower()
        location = (account.get("location", "") or "").lower()
        combined = f"{bio} {location}"

        for category, keywords in patterns.items():
            score = sum(1 for kw in keywords if kw in combined)
            if score > 0:
                category_accounts[category].append((username, score))

    # Sort by score and take top N per category
    seeds = {}
    for category, candidates in category_accounts.items():
        candidates.sort(key=lambda x: -x[1])  # Sort by score descending
        seeds[category] = [u for u, _ in candidates[:seeds_per_category]]
        if not seeds[category]:
            # Remove empty categories
            del seeds[category]

    return seeds


def print_cluster_summary(
    accounts: list[dict],
    embeddings: np.ndarray,
    labels: np.ndarray,
    silhouette_scores: dict[int, float],
) -> None:
    """Print a detailed summary of clustering results.

    Args:
        accounts: List of account dicts.
        embeddings: Embedding matrix.
        labels: Cluster labels for each account.
        silhouette_scores: Silhouette score per cluster.
    """
    # Group accounts by cluster
    cluster_members: dict[int, list[dict]] = {}
    for i, label in enumerate(labels):
        label = int(label)
        if label not in cluster_members:
            cluster_members[label] = []
        cluster_members[label].append(accounts[i])

    # Sort clusters by size (largest first)
    sorted_clusters = sorted(cluster_members.items(), key=lambda x: -len(x[1]))

    print("\n" + "=" * 70)
    print("CLUSTERING RESULTS - WHAT LISTS WOULD BE CREATED")
    print("=" * 70)

    for cluster_id, members in sorted_clusters:
        n_members = len(members)
        silhouette = silhouette_scores.get(cluster_id, 0.0)

        # Determine cluster quality
        quality = "🟢" if silhouette >= 0.5 else ("🟡" if silhouette >= 0.25 else "🔴")

        print(f"\n{'─' * 70}")
        print(f"📋 Cluster {cluster_id} ({n_members} members, silhouette={silhouette:.2f}) {quality}")
        print(f"{'─' * 70}")

        # Show sample members (first 10)
        for i, account in enumerate(members[:10]):
            username = account.get("username", "unknown")
            name = account.get("name", "")[:40]
            bio = (account.get("description", "") or "")[:60]
            location = account.get("location", "") or ""

            print(f"  {i+1:2}. @{username:<20} {name}")
            if bio:
                print(f"      Bio: {bio}{'...' if len(account.get('description', '') or '') > 60 else ''}")
            if location:
                print(f"      Loc: {location}")

        if n_members > 10:
            print(f"  ... and {n_members - 10} more")

    # Summary stats
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total = len(accounts)
    n_clusters = len(cluster_members)

    print(f"  Total accounts:           {total}")
    print(f"  Clusters created:         {n_clusters}")
    print(f"  Avg cluster size:         {total / n_clusters:.1f}")
    print(f"  Avg silhouette score:     {np.mean(list(silhouette_scores.values())):.3f}")

    # Size distribution
    sizes = [len(m) for m in cluster_members.values()]
    print(f"\n  Cluster sizes: {sorted(sizes, reverse=True)}")

    # Quality breakdown
    high_quality = sum(1 for s in silhouette_scores.values() if s >= 0.5)
    medium_quality = sum(1 for s in silhouette_scores.values() if 0.25 <= s < 0.5)
    low_quality = sum(1 for s in silhouette_scores.values() if s < 0.25)

    print(f"\n  Quality breakdown:")
    print(f"    🟢 High (≥0.5):         {high_quality} clusters")
    print(f"    🟡 Medium (0.25-0.5):   {medium_quality} clusters")
    print(f"    🔴 Low (<0.25):         {low_quality} clusters")

    print("\n" + "=" * 70)


def run_clustering_test(
    cache_dir: Path,
    max_accounts: int | None = None,
    algorithm: str = "kmeans",
    auto_seeds: bool = True,
) -> int:
    """Run the clustering test.

    Args:
        cache_dir: Directory containing enrichment cache.
        max_accounts: Maximum accounts to process.
        algorithm: Clustering algorithm ("kmeans" or "hdbscan").
        auto_seeds: Whether to auto-generate seed categories.

    Returns:
        0 on success, 1 on error.
    """
    print("=" * 70)
    print("CLUSTERING TEST DRIVER")
    print("=" * 70)

    # Step 1: Load accounts
    print("\n[Step 1] Loading enriched accounts...")
    accounts = load_enriched_accounts(cache_dir, max_accounts)
    print(f"  Loaded {len(accounts)} accounts")

    if len(accounts) < 10:
        print("  ERROR: Need at least 10 accounts for clustering")
        return 1

    # Step 2: Generate or load seeds
    print("\n[Step 2] Preparing seed categories...")
    if auto_seeds:
        seeds = auto_generate_seeds(accounts)
        print(f"  Auto-generated {len(seeds)} seed categories:")
        for cat, usernames in seeds.items():
            print(f"    - {cat}: {usernames}")
    else:
        # Load from config file
        import yaml
        seed_path = Path("config/seed_accounts.yaml")
        if not seed_path.exists():
            print("  ERROR: config/seed_accounts.yaml not found")
            return 1
        with open(seed_path) as f:
            seed_config = yaml.safe_load(f)
        seeds = {}
        for cat, cat_data in seed_config.items():
            if isinstance(cat_data, dict) and "examples" in cat_data:
                seeds[cat] = cat_data["examples"]
            elif isinstance(cat_data, list):
                seeds[cat] = cat_data
        print(f"  Loaded {len(seeds)} categories from config")

    # Step 3: Create embeddings
    print("\n[Step 3] Creating embeddings...")
    from src.cluster.embed import (
        EMBEDDING_MODEL,
        embed_accounts,
        load_seed_embeddings,
        compute_clusters,
        compute_silhouette_scores,
    )

    try:
        embeddings, valid_accounts = embed_accounts(accounts, cache_path=cache_dir.parent / "test_embeddings.npy")
        print(f"  Embedded {len(valid_accounts)} accounts using {EMBEDDING_MODEL}")
    except ValueError as e:
        print(f"  ERROR: {e}")
        return 1

    # Step 4: Load seed embeddings
    print("\n[Step 4] Loading seed embeddings...")
    seed_embeddings = load_seed_embeddings(seeds, cache_dir)
    n_valid_seeds = sum(1 for v in seed_embeddings.values() if v.shape[0] > 0)
    print(f"  Found embeddings for {n_valid_seeds}/{len(seeds)} seed categories")

    # Step 5: Run clustering
    print(f"\n[Step 5] Running {algorithm.upper()} clustering...")
    labels, seed_centroids, final_centroids, category_names = compute_clusters(
        embeddings,
        seed_embeddings,
        algorithm=algorithm,
    )
    print(f"  Created {len(final_centroids)} clusters")

    # Step 6: Compute silhouette scores
    print("\n[Step 6] Computing quality metrics...")
    silhouette_scores = compute_silhouette_scores(embeddings, labels)

    # Step 7: Print results
    print_cluster_summary(valid_accounts, embeddings, labels, silhouette_scores)

    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Test the clustering pipeline")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/enrichment"),
        help="Directory containing enrichment cache (default: data/enrichment)",
    )
    parser.add_argument(
        "--max-accounts",
        type=int,
        default=None,
        help="Maximum accounts to process (default: all)",
    )
    parser.add_argument(
        "--algorithm",
        choices=["kmeans", "hdbscan"],
        default="kmeans",
        help="Clustering algorithm (default: kmeans)",
    )
    parser.add_argument(
        "--no-auto-seeds",
        action="store_true",
        help="Use seed_accounts.yaml instead of auto-generated seeds",
    )
    args = parser.parse_args()

    return run_clustering_test(
        cache_dir=args.cache_dir,
        max_accounts=args.max_accounts,
        algorithm=args.algorithm,
        auto_seeds=not args.no_auto_seeds,
    )


if __name__ == "__main__":
    sys.exit(main())