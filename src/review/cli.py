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

    # Load registry
    reg = load_registry()
    console.print(f"[dim]Registry session: {reg.session_id}, rounds_completed={reg.rounds_completed}, automation_enabled={reg.automation_enabled}[/dim]\n")

    # Load cluster data
    clusters = load_cluster_data(args.cache_dir)
    if not clusters:
        console.print("[bold red]No clusters found. Run Phase 4 clustering first.[/bold red]")
        sys.exit(1)

    summaries = build_cluster_summary(clusters)
    hist = summaries[0]["histogram"] if summaries else None

    # Display size histogram (REVIEW-06)
    if not args.skip_histogram and hist:
        display_size_histogram(hist)

    # Check automation offer (REVIEW-07)
    if reg.rounds_completed >= AUTOMATION_ROUNDS and not reg.automation_offered:
        console.print(f"[bold green]You have completed {reg.rounds_completed} approval rounds.[/bold green]")
        console.print("[yellow]Full automation mode is now available for future review sessions.[/yellow]\n")

    console.print(f"[bold]Found {len(summaries)} clusters to review.[/bold]")
    console.print("Run this module with subcommands for review operations (see Plan 05-02 and 05-03).")
    console.print("Plan 05-02: Table display + per-member confidence + batch approve")
    console.print("Plan 05-03: Per-cluster actions + merge/split + automation offer\n")


if __name__ == "__main__":
    main()
