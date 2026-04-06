"""Data export for Phase 6: Parquet and CSV export of enrichment data and clusters.

Implements EXPORT-01 (Parquet for enriched followers) and EXPORT-02 (CSV for
approved/deferred clusters).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.review.registry import load_registry

logger = logging.getLogger(__name__)

EXPORT_DIR = Path("data/export")
FOLLOWERS_PARQUET = EXPORT_DIR / "followers.parquet"
CLUSTERS_CSV = EXPORT_DIR / "clusters.csv"


def export_clusters_to_csv() -> Path:
    """Export approved and deferred clusters to CSV.

    Creates data/export/clusters.csv with one row per cluster and columns:
    cluster_id, cluster_name, status, size, silhouette, member_handles,
    central_member_usernames.

    Returns
    -------
    Path
        Path to the created clusters.csv file.
    """
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    reg = load_registry()
    approved = reg.clusters.get("approved", [])
    deferred = reg.clusters.get("deferred", [])

    rows: list[dict[str, Any]] = []

    for cluster in approved:
        members = cluster.get("members", [])
        member_usernames = [m.get("username", "") for m in members if m.get("username")]
        central = cluster.get("central_member_usernames", [])
        if isinstance(central, list):
            central_str = ", ".join(str(u) for u in central)
        else:
            central_str = str(central) if central else ""

        rows.append({
            "cluster_id": cluster.get("cluster_id", ""),
            "cluster_name": cluster.get("cluster_name", ""),
            "status": "approved",
            "size": cluster.get("size", 0),
            "silhouette": cluster.get("silhouette", ""),
            "member_handles": ", ".join(member_usernames),
            "central_member_usernames": central_str,
        })

    for cluster in deferred:
        members = cluster.get("members", [])
        member_usernames = [m.get("username", "") for m in members if m.get("username")]
        central = cluster.get("central_member_usernames", [])
        if isinstance(central, list):
            central_str = ", ".join(str(u) for u in central)
        else:
            central_str = str(central) if central else ""

        rows.append({
            "cluster_id": cluster.get("cluster_id", ""),
            "cluster_name": cluster.get("cluster_name", ""),
            "status": "deferred",
            "size": cluster.get("size", 0),
            "silhouette": cluster.get("silhouette", ""),
            "member_handles": ", ".join(member_usernames),
            "central_member_usernames": central_str,
        })

    df = pd.DataFrame(rows)
    df.to_csv(CLUSTERS_CSV, index=False)
    logger.info("Exported %d clusters to %s", len(rows), CLUSTERS_CSV)
    return CLUSTERS_CSV


def export_followers_to_parquet() -> Path:
    """Export all enriched follower records to Parquet.

    Reads all files from data/enrichment/ (excluding suspended.json,
    protected.json, errors.json) and writes them to
    data/export/followers.parquet.

    Returns
    -------
    Path
        Path to the created followers.parquet file.

    Raises
    ------
    RuntimeError
        If no enrichment files are found.
    """
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    enrichment_dir = Path("data/enrichment")
    if not enrichment_dir.exists():
        raise RuntimeError(
            "No enrichment data found. Run Phase 4 clustering first."
        )

    rows: list[dict[str, Any]] = []
    skipped = 0

    for fpath in sorted(enrichment_dir.glob("*.json")):
        if fpath.stem in ("suspended", "protected", "errors"):
            skipped += 1
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            rows.append(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("Skipping %s: %s", fpath.name, e)
            continue

    if not rows:
        raise RuntimeError(
            "No enrichment data found. Run Phase 4 clustering first."
        )

    df = pd.DataFrame(rows)
    df.to_parquet(FOLLOWERS_PARQUET, index=False)
    logger.info(
        "Exported %d follower records to %s (skipped %d special files)",
        len(rows),
        FOLLOWERS_PARQUET,
        skipped,
    )
    return FOLLOWERS_PARQUET


def export_all() -> dict[str, Any]:
    """Run both CSV and Parquet export and return summary.

    Returns
    -------
    dict[str, Any]
        Summary with cluster CSV path and followers Parquet path,
        plus row counts.
    """
    clusters_path = export_clusters_to_csv()
    followers_path = export_followers_to_parquet()

    # Read back counts
    clusters_df = pd.read_csv(clusters_path)
    followers_df = pd.read_parquet(followers_path)

    summary = {
        "clusters_csv": str(clusters_path),
        "clusters_rows": len(clusters_df),
        "followers_parquet": str(followers_path),
        "followers_rows": len(followers_df),
    }

    logger.info(
        "Export complete: clusters.csv=%d rows, followers.parquet=%d rows",
        summary["clusters_rows"],
        summary["followers_rows"],
    )
    return summary
