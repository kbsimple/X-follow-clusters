"""Batch approve logic and confirmation prompt."""
import questionary
from rich.console import Console
from typing import Optional
from src.review.registry import ApprovalRegistry, save_registry

console = Console()

BATCH_SIZE_THRESHOLD = 10
BATCH_SILHOUETTE_THRESHOLD = 0.5


def get_batch_approvable_clusters(
    summaries: list[dict],
    registry_status: dict[int, str],
) -> list[dict]:
    """Return clusters that meet batch approval criteria.

    Per REVIEW-04 and D-07: Batch approve for clusters with:
    - size >= BATCH_SIZE_THRESHOLD (10 members)
    - silhouette >= BATCH_SILHOUETTE_THRESHOLD (0.5)
    - status is "pending" (not already approved/rejected/deferred)

    Args:
        summaries: List from build_cluster_summary()
        registry_status: {cluster_id: status}

    Returns:
        List of cluster summaries eligible for batch approve.
    """
    import math

    eligible = []
    for cluster in summaries:
        cid = cluster["cluster_id"]
        size = cluster["size"]
        sil = cluster["silhouette"]
        status = registry_status.get(cid, "pending")

        if status != "pending":
            continue
        if size < BATCH_SIZE_THRESHOLD:
            continue
        if math.isnan(sil) or sil < BATCH_SILHOUETTE_THRESHOLD:
            continue

        eligible.append(cluster)

    return eligible


def confirm_batch_approve(
    eligible_clusters: list[dict],
    reg: ApprovalRegistry,
) -> Optional[list[dict]]:
    """Confirm batch approve with user via questionary prompt.

    Per REVIEW-04: Batch approve available for eligible clusters.
    Shows count and names of clusters to be approved.
    Returns list of clusters to batch-approve if confirmed, None if cancelled.

    Args:
        eligible_clusters: from get_batch_approvable_clusters()
        reg: current approval registry

    Returns:
        List of clusters to approve if confirmed, None if user declines.
    """
    if not eligible_clusters:
        return None

    names = [c["cluster_name"] for c in eligible_clusters]
    total_size = sum(c["size"] for c in eligible_clusters)

    console.print(f"\n[bold green]Batch approve eligible:[/bold green] {len(eligible_clusters)} clusters, {total_size} total members\n")
    for name in names:
        console.print(f"  - {name}")

    choice = questionary.select(
        f"Approve {len(eligible_clusters)} clusters automatically?",
        choices=[
            f"Approve all {len(eligible_clusters)} clusters",
            "Review each cluster individually",
            "Skip batch approve",
        ],
    ).ask()

    if choice and "Approve all" in choice:
        return eligible_clusters
    return None


def apply_batch_approve(
    clusters: list[dict],
    reg: ApprovalRegistry,
) -> ApprovalRegistry:
    """Add batch-approved clusters to registry as approved.

    Per REVIEW-04: Batch-approved clusters are added to clusters["approved"]
    with round_approved = rounds_completed + 1 (counts as a new approval round).

    Args:
        clusters: List of cluster summaries to approve
        reg: current approval registry

    Returns:
        Updated registry with batch-approved clusters added.
    """
    import datetime

    new_round = reg.rounds_completed + 1
    for cluster in clusters:
        entry = {
            "cluster_id": cluster["cluster_id"],
            "cluster_name": cluster["cluster_name"],
            "size": cluster["size"],
            "silhouette": cluster["silhouette"],
            "members": cluster["members"],
            "round_approved": new_round,
        }
        # Remove from other lists if re-batching
        reg.clusters["deferred"] = [
            e for e in reg.clusters["deferred"] if e["cluster_id"] != cluster["cluster_id"]
        ]
        reg.clusters["rejected"] = [
            e for e in reg.clusters["rejected"] if e["cluster_id"] != cluster["cluster_id"]
        ]
        # Add to approved if not already there
        if not any(e["cluster_id"] == cluster["cluster_id"] for e in reg.clusters["approved"]):
            reg.clusters["approved"].append(entry)

    reg.rounds_completed = new_round
    reg.batch_approved_count += len(clusters)
    reg.timestamp = datetime.datetime.now().isoformat()

    return reg
