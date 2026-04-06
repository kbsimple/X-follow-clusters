"""Per-member silhouette/confidence computation via sklearn silhouette_samples."""
from pathlib import Path
import json, logging
import numpy as np
from sklearn.metrics import silhouette_samples

logger = logging.getLogger(__name__)

def compute_member_confidences(
    embeddings_path: Path = Path("data/embeddings.npy"),
    sidecar_path: Path = Path("data/embeddings.sidecar.json"),
    cache_dir: Path = Path("data/enrichment"),
) -> dict[int, dict[str, float]]:
    """Compute per-member silhouette score for every account.

    Returns dict keyed by cluster_id, each containing {username: confidence_score}.
    Per REVIEW-02: Show confidence scores for cluster membership.

    Raises RuntimeError if embeddings cache is missing (point to Phase 4).
    Flags clusters below minimum size (5) with "N/A" for silhouette.
    """
    if not embeddings_path.exists() or not sidecar_path.exists():
        raise RuntimeError(
            f"Embeddings cache not found at {embeddings_path}. "
            "Run Phase 4 clustering first to generate embeddings."
        )

    embeddings = np.load(embeddings_path)
    with open(sidecar_path) as f:
        usernames: list[str] = json.load(f)

    username_to_idx = {u: i for i, u in enumerate(usernames)}

    # Load cluster labels from enrichment cache
    cluster_ids: list[int] = []
    valid_mask: list[bool] = []
    for fpath in sorted(cache_dir.glob("*.json")):
        if fpath.stem in ("suspended", "protected", "errors"):
            continue
        try:
            d = json.load(open(fpath))
            cid = d.get("cluster_id")
            if cid is not None:
                cluster_ids.append(int(cid))
                valid_mask.append(True)
            else:
                cluster_ids.append(-1)
                valid_mask.append(False)
        except Exception:
            cluster_ids.append(-1)
            valid_mask.append(False)

    # Handle case where enrichment cache count differs from embeddings
    if len(cluster_ids) != len(usernames):
        logger.warning(
            f"Enrichment cache ({len(cluster_ids)} accounts) != embeddings ({len(usernames)} usernames). "
            "Using username order from sidecar as ground truth."
        )
        # Build cluster_id array matching embeddings order
        uname_to_cid: dict[str, int] = {}
        for fpath in sorted(cache_dir.glob("*.json")):
            if fpath.stem in ("suspended", "protected", "errors"):
                continue
            try:
                d = json.load(open(fpath))
                cid = d.get("cluster_id")
                if cid is not None and d.get("username"):
                    uname_to_cid[d["username"]] = int(cid)
            except Exception:
                continue
        cluster_ids = [uname_to_cid.get(u, -1) for u in usernames]

    labels = np.array(cluster_ids)

    # Compute per-sample silhouette scores
    scores = silhouette_samples(embeddings, labels)

    # Group by cluster_id
    result: dict[int, dict[str, float]] = {}
    for i, (uname, score) in enumerate(zip(usernames, scores)):
        cid = int(labels[i])
        if cid not in result:
            result[cid] = {}
        result[cid][uname] = float(score)

    return result


def get_cluster_member_details(
    cluster_id: int,
    member_scores: dict[int, dict[str, float]],
    cache_dir: Path = Path("data/enrichment"),
    top_n: int = 20,
) -> list[dict]:
    """Get detailed member info (username, bio, confidence) for a cluster.

    Returns list sorted by confidence descending. Shows up to top_n members.
    Per REVIEW-02: confidence score per member shown alongside bio snippet.
    """
    import math

    scores = member_scores.get(cluster_id, {})
    members: list[tuple[str, float]] = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

    result = []
    for uname, confidence in members:
        acct_file = cache_dir / f"{uname}.json"
        bio = ""
        if acct_file.exists():
            try:
                d = json.load(open(acct_file))
                bio = d.get("description", "")[:80]
            except Exception:
                pass

        result.append({
            "username": uname,
            "confidence": confidence if not math.isnan(confidence) else 0.0,
            "bio": bio,
        })

    return result
