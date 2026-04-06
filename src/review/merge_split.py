"""Merge and split cluster operations.

Merge (D-09): Union of two clusters re-clustered with k=1; new cluster gets LLM-generated name.
Split (D-09): Selected members moved to nearest neighbor cluster centroid.
"""
import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np

from src.cluster.name import name_cluster

logger = logging.getLogger(__name__)


def _load_accounts_for_clusters(
    cluster_ids: list[int],
    cache_dir: Path,
) -> list[tuple[str, dict]]:
    """Load (username, account_dict) for all accounts in given cluster_ids."""
    accounts = []
    for fpath in sorted(cache_dir.glob("*.json")):
        if fpath.stem in ("suspended", "protected", "errors"):
            continue
        try:
            d = json.load(open(fpath))
            cid = d.get("cluster_id")
            if cid is not None and int(cid) in cluster_ids:
                accounts.append((d.get("username", fpath.stem), d))
        except Exception:
            continue
    return accounts


def _get_embeddings_for_usernames(
    usernames: list[str],
    embeddings_path: Path = Path("data/embeddings.npy"),
    sidecar_path: Path = Path("data/embeddings.sidecar.json"),
) -> tuple[np.ndarray, list[str]]:
    """Extract embedding vectors for a subset of usernames from the cached embeddings."""
    embeddings = np.load(embeddings_path)
    with open(sidecar_path) as f:
        all_usernames: list[str] = json.load(f)

    username_set = set(usernames)
    mask = np.array([u in username_set for u in all_usernames])
    subset_emb = embeddings[mask]
    subset_names = [u for u in all_usernames if u in username_set]

    return subset_emb, subset_names


def _get_final_centroids(
    cache_dir: Path = Path("data/enrichment"),
) -> np.ndarray:
    """Reconstruct final_centroids array from current cluster assignments.

    Computes mean embedding per cluster_id from the cached embeddings.
    This is used for split nearest-neighbor reassignment.
    """
    embeddings = np.load(Path("data/embeddings.npy"))
    with open(Path("data/embeddings.sidecar.json")) as f:
        all_usernames: list[str] = json.load(f)

    username_to_idx = {u: i for i, u in enumerate(all_usernames)}

    cluster_members: dict[int, list[int]] = {}
    for fpath in sorted(cache_dir.glob("*.json")):
        if fpath.stem in ("suspended", "protected", "errors"):
            continue
        try:
            d = json.load(open(fpath))
            cid = d.get("cluster_id")
            uname = d.get("username")
            if cid is not None and uname in username_to_idx:
                idx = username_to_idx[uname]
                cluster_members.setdefault(int(cid), []).append(idx)
        except Exception:
            continue

    if not cluster_members:
        raise RuntimeError("No cluster assignments found in cache.")

    max_cid = max(cluster_members.keys())
    centroids = np.zeros((max_cid + 1, embeddings.shape[1]))
    for cid, indices in cluster_members.items():
        centroids[cid] = np.mean(embeddings[indices], axis=0)

    return centroids


def merge_clusters(
    cluster_a_id: int,
    cluster_b_id: int,
    cache_dir: Path = Path("data/enrichment"),
) -> tuple[int, str]:
    """Merge two clusters into one new cluster.

    Per D-09: Union of members from both clusters, re-clustered with k=1.
    New cluster gets LLM-generated name from member bios.

    Args:
        cluster_a_id: First cluster to merge
        cluster_b_id: Second cluster to merge
        cache_dir: Path to enrichment cache

    Returns:
        (new_cluster_id, new_cluster_name)

    Raises:
        RuntimeError: If embeddings cache is missing
    """
    embeddings_path = Path("data/embeddings.npy")
    sidecar_path = Path("data/embeddings.sidecar.json")

    if not embeddings_path.exists() or not sidecar_path.exists():
        raise RuntimeError("Embeddings cache required for merge. Run Phase 4 first.")

    # Collect all accounts from both clusters
    accounts = _load_accounts_for_clusters([cluster_a_id, cluster_b_id], cache_dir)
    if not accounts:
        raise RuntimeError(f"No accounts found for clusters {cluster_a_id} and {cluster_b_id}")

    all_usernames = [uname for uname, _ in accounts]

    # Get embeddings for union
    union_emb, union_names = _get_embeddings_for_usernames(all_usernames, embeddings_path, sidecar_path)

    # Build seed: mean of all union members as a single centroid
    # Use k=1 to force one cluster; empty seed dict = no anchor guidance
    from src.cluster.embed import compute_clusters

    seed_emb: dict[str, np.ndarray] = {}
    labels, _, _, _ = compute_clusters(
        union_emb,
        seed_emb,
        algorithm="kmeans",
        min_size=1,
        max_size=len(union_emb),
    )

    new_cluster_id = int(labels[0])

    # Name the merged cluster via LLM
    bios = []
    for uname, acct in accounts[:10]:
        bio = acct.get("description", "")
        if bio:
            bios.append(bio)

    new_name = name_cluster(bios) if bios else name_cluster([])

    # Write updated cluster_id and cluster_name to all affected cache files
    for uname, acct in accounts:
        acct["cluster_id"] = new_cluster_id
        acct["cluster_name"] = new_name
        out_path = cache_dir / f"{uname}.json"
        try:
            json.dump(acct, open(out_path, "w"), indent=2)
        except Exception as e:
            logger.warning(f"Could not update {out_path}: {e}")

    logger.info(f"Merged clusters {cluster_a_id}+{cluster_b_id} -> cluster {new_cluster_id} ('{new_name}')")
    return new_cluster_id, new_name


def split_cluster(
    source_cluster_id: int,
    members_to_move: list[str],
    cache_dir: Path = Path("data/enrichment"),
) -> list[str]:
    """Move selected members from source cluster to nearest neighbor cluster.

    Per D-09: Split moves selected members to nearest neighbor or re-review.
    Uses existing final_centroids to find nearest neighbor (excluding source).

    Args:
        source_cluster_id: Cluster to split
        members_to_move: Usernames of members to move out
        cache_dir: Path to enrichment cache

    Returns:
        List of usernames successfully moved
    """
    from src.review.metrics import compute_member_confidences

    embeddings_path = Path("data/embeddings.npy")
    sidecar_path = Path("data/embeddings.sidecar.json")

    if not embeddings_path.exists():
        raise RuntimeError("Embeddings cache required for split. Run Phase 4 first.")

    embeddings = np.load(embeddings_path)
    with open(sidecar_path) as f:
        all_usernames: list[str] = json.load(f)

    username_to_idx = {u: i for i, u in enumerate(all_usernames)}

    # Get centroids from current cluster assignments
    centroids = _get_final_centroids(cache_dir)

    moved = []
    for uname in members_to_move:
        if uname not in username_to_idx:
            logger.warning(f"Username {uname} not found in embeddings")
            continue

        idx = username_to_idx[uname]
        emb = embeddings[idx]

        # Distance to all centroids; exclude source cluster
        dists = np.linalg.norm(centroids - emb, axis=1)
        dists[source_cluster_id] = np.inf
        nearest = int(np.argmin(dists))

        # Update cache file
        acct_file = cache_dir / f"{uname}.json"
        if acct_file.exists():
            try:
                d = json.load(open(acct_file))
                d["cluster_id"] = nearest
                # cluster_name will be updated when name_all_clusters is re-run
                json.dump(d, open(acct_file, "w"), indent=2)
                moved.append(uname)
                logger.info(f"Moved {uname} from cluster {source_cluster_id} to {nearest}")
            except Exception as e:
                logger.warning(f"Could not update {acct_file}: {e}")

    return moved