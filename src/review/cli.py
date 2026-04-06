"""Review CLI entry point: python -m src.review.cli"""
import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from rich.console import Console

from src.review.registry import load_registry, APPROVAL_REGISTRY_PATH, AUTOMATION_ROUNDS
from src.review.histogram import display_size_histogram

console = Console()


def load_cluster_data(cache_dir: Path = Path("data/enrichment")) -> dict[int, list[dict]]:
    """Load all enrichment JSON files and group by cluster_id.

    Parameters
    ----------
    cache_dir : Path
        Directory containing data/enrichment/{username}.json files.

    Returns
    -------
    dict[int, list[dict]]
        Mapping from cluster_id to list of account dicts.
    """
    clusters: dict[int, list[dict]] = {}
    for fpath in sorted(cache_dir.glob("*.json")):
        if fpath.stem in ("suspended", "protected", "errors"):
            continue
        try:
            d = json_load(fpath)
        except Exception:
            continue
        cid = d.get("cluster_id")
        if cid is not None:
            clusters.setdefault(int(cid), []).append(d)
    return clusters


def json_load(path: Path) -> dict:
    """Load a JSON file, trying multiple encodings."""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return __import__("json").load(open(path, encoding=enc))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {path}")


def build_cluster_summary(clusters: dict[int, list[dict]]) -> list[dict]:
    """Build summary list from cluster data for table display.

    Parameters
    ----------
    clusters : dict[int, list[dict]]
        Cluster data loaded from enrichment JSONs.

    Returns
    -------
    list[dict]
        Summary dicts with cluster_id, cluster_name, size, silhouette, members, histogram.
    """
    # Load silhouette scores from any account (they store per-cluster silhouette)
    silhouette_by_cluster: dict[int, float] = {}
    for cid, accounts in clusters.items():
        scores = [a.get("silhouette_score", 0.0) for a in accounts]
        silhouette_by_cluster[cid] = float(np.mean(scores)) if scores else 0.0

    # Size histogram
    all_labels = []
    for cid, accounts in clusters.items():
        all_labels.extend([cid] * len(accounts))

    from src.cluster.embed import generate_size_histogram
    hist = generate_size_histogram(np.array(all_labels))

    summaries = []
    for cid, accounts in sorted(clusters.items()):
        names = [a.get("cluster_name", f"cluster_{cid}") for a in accounts]
        name_counter = Counter(names)
        top_name = name_counter.most_common(1)[0][0] if name_counter else f"cluster_{cid}"
        summaries.append({
            "cluster_id": cid,
            "cluster_name": top_name,
            "size": len(accounts),
            "silhouette": silhouette_by_cluster.get(cid, 0.0),
            "members": [a["username"] for a in accounts],
            "histogram": hist,
        })
    return summaries


def main():
    parser = argparse.ArgumentParser(description="Review and approve clusters")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/enrichment"))
    parser.add_argument("--skip-histogram", action="store_true", help="Skip size histogram display")
    args = parser.parse_args()

    from src.review.registry import load_registry, AUTOMATION_ROUNDS
    from src.review.histogram import display_size_histogram
    from src.review.table import display_cluster_table, display_member_details
    from src.review.metrics import compute_member_confidences, get_cluster_member_details
    from src.review.batch import get_batch_approvable_clusters, confirm_batch_approve, apply_batch_approve
    from src.review.actions import handle_cluster_action
    from src.review.automation import should_offer_automation, offer_automation_mode

    reg = load_registry()
    console.print(f"[dim]Session: {reg.session_id} | Rounds: {reg.rounds_completed}/{AUTOMATION_ROUNDS} | Automation: {reg.automation_enabled}[/dim]\n")

    # Load cluster data
    clusters = load_cluster_data(args.cache_dir)
    if not clusters:
        console.print("[bold red]No clusters found. Run Phase 4 clustering first.[/bold red]")
        sys.exit(1)

    summaries = build_cluster_summary(clusters)
    hist = summaries[0]["histogram"] if summaries else None

    if not args.skip_histogram and hist:
        display_size_histogram(hist)

    # Compute per-member confidences
    try:
        member_scores = compute_member_confidences(args.cache_dir)
    except RuntimeError as e:
        console.print(f"[yellow]{e}[/yellow]")
        member_scores = {}

    # Build registry status map
    registry_status: dict[int, str] = {}
    for cid in summaries:
        registry_status[cid] = "pending"

    for e in reg.clusters["approved"]:
        registry_status[e["cluster_id"]] = "approved"
    for e in reg.clusters["deferred"]:
        registry_status[e["cluster_id"]] = "deferred"
    for e in reg.clusters["rejected"]:
        registry_status[e["cluster_id"]] = "rejected"

    # Batch approve check
    eligible = get_batch_approvable_clusters(summaries, registry_status)
    if eligible:
        to_approve = confirm_batch_approve(eligible, reg)
        if to_approve:
            reg = apply_batch_approve(to_approve, reg)
            # Refresh status
            for e in reg.clusters["approved"]:
                registry_status[e["cluster_id"]] = "approved"

    # Automation offer
    if should_offer_automation(reg):
        reg = offer_automation_mode(reg)

    # Main review loop: "See all, then act" per D-03
    pending = [c for c in summaries if registry_status.get(c["cluster_id"], "pending") == "pending"]

    if pending:
        display_cluster_table(pending, member_scores, registry_status)
        console.print(f"\n[bold]Reviewing {len(pending)} pending clusters...[/bold]\n")

        for i, cluster in enumerate(pending, 1):
            from src.review.table import print_review_prompt
            print_review_prompt(cluster, i, len(pending))

            reg, changed = handle_cluster_action(
                cluster, reg, member_scores, args.cache_dir, summaries
            )

            if changed:
                # Refresh cluster data after merge/split
                clusters = load_cluster_data(args.cache_dir)
                summaries = build_cluster_summary(clusters)
                member_scores = compute_member_confidences(args.cache_dir)
                # Rebuild status
                registry_status = {c["cluster_id"]: "pending" for c in summaries}
                for e in reg.clusters["approved"]:
                    registry_status[e["cluster_id"]] = "approved"
                for e in reg.clusters["deferred"]:
                    registry_status[e["cluster_id"]] = "deferred"
                for e in reg.clusters["rejected"]:
                    registry_status[e["cluster_id"]] = "rejected"
    else:
        console.print("[bold green]All clusters have been reviewed![/bold green]\n")

    # Final summary
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Approved: {len(reg.clusters['approved'])}")
    console.print(f"  Deferred: {len(reg.clusters['deferred'])}")
    console.print(f"  Rejected: {len(reg.clusters['rejected'])}")
    console.print(f"  Rounds completed: {reg.rounds_completed}")
    console.print(f"  Automation: {'enabled' if reg.automation_enabled else 'disabled'}\n")

    console.print("Proceed to Phase 6: /gsd:execute-phase 6")


if __name__ == "__main__":
    main()
