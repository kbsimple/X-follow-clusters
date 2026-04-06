"""Per-cluster action handlers: approve, reject, rename, merge, split, defer."""
import questionary
import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from src.review.registry import ApprovalRegistry, save_registry, AUTOMATION_ROUNDS
from src.review.merge_split import merge_clusters, split_cluster
from src.review.metrics import get_cluster_member_details, compute_member_confidences
from src.cluster.name import name_cluster
from src.cluster.embed import generate_size_histogram
import numpy as np

console = Console()


def _get_action_choices(has_members: bool = True) -> list[str]:
    """Return action choices for a cluster."""
    choices = [
        "approve",
        "reject",
        "rename",
        "merge",
        "split",
        "defer",
        "see members",
        "back",
    ]
    return choices


def handle_cluster_action(
    cluster: dict,
    reg: ApprovalRegistry,
    member_scores: dict[int, dict[str, float]],
    cache_dir: Path = Path("data/enrichment"),
    all_clusters: Optional[list[dict]] = None,
) -> tuple[ApprovalRegistry, bool]:
    """Handle all actions for a single cluster.

    Returns (updated_registry, cluster_changed).
    cluster_changed=True means the cluster was modified (merge/split/rename) and
    display should refresh.

    Per REVIEW-03: Support per-cluster actions approve, reject, rename, merge, split, defer.
    Per REVIEW-05: Deferred clusters do not block others.
    Per D-08: Deferred clusters marked in registry but excluded from Phase 6.
    """
    cluster_changed = False
    cid = cluster["cluster_id"]

    while True:
        action = questionary.select(
            f"Action for '[cyan]{cluster['cluster_name']}[/cyan]' "
            f"({cluster['size']} members, sil={cluster['silhouette']:.3f}):",
            choices=_get_action_choices(),
        ).ask()

        if action is None or action == "back":
            break

        elif action == "approve":
            reg = _do_approve(cluster, reg)
            break

        elif action == "reject":
            reg = _do_reject(cluster, reg)
            break

        elif action == "rename":
            new_name = _do_rename(cluster, reg, cache_dir)
            if new_name:
                cluster["cluster_name"] = new_name
                cluster_changed = True
            break

        elif action == "merge":
            if not all_clusters:
                console.print("[yellow]No other clusters available to merge with.[/yellow]")
                continue
            target = _prompt_merge_target(cluster, all_clusters)
            if target:
                new_cid, new_name = merge_clusters(cluster["cluster_id"], target["cluster_id"], cache_dir)
                cluster["cluster_id"] = new_cid
                cluster["cluster_name"] = new_name
                cluster_changed = True
                console.print(f"[green]Merged into new cluster: {new_name} (id={new_cid})[/green]")
            break

        elif action == "split":
            moved = _do_split(cluster, member_scores, cache_dir)
            if moved:
                cluster["size"] -= len(moved)
                cluster_changed = True
                console.print(f"[green]Moved {len(moved)} members out of this cluster.[/green]")
            break

        elif action == "defer":
            reg = _do_defer(cluster, reg)
            break

        elif action == "see members":
            details = get_cluster_member_details(cid, member_scores, cache_dir)
            from src.review.table import display_member_details
            display_member_details(cluster, details, member_scores)
            # Loop continues to re-prompt

    return reg, cluster_changed


def _do_approve(cluster: dict, reg: ApprovalRegistry) -> ApprovalRegistry:
    """Add cluster to approved list. Increments rounds_completed only for NEW approval."""
    cid = cluster["cluster_id"]
    already_approved = any(e["cluster_id"] == cid for e in reg.clusters["approved"])

    entry = {
        "cluster_id": cid,
        "cluster_name": cluster["cluster_name"],
        "size": cluster["size"],
        "silhouette": cluster["silhouette"],
        "members": cluster["members"],
        "round_approved": reg.rounds_completed + 1,
    }

    # Remove from deferred/rejected if re-reviewing
    reg.clusters["deferred"] = [e for e in reg.clusters["deferred"] if e["cluster_id"] != cid]
    reg.clusters["rejected"] = [e for e in reg.clusters["rejected"] if e["cluster_id"] != cid]

    if not already_approved:
        reg.clusters["approved"].append(entry)
        reg.rounds_completed += 1
        console.print(f"[green]Approved: {cluster['cluster_name']} (round {reg.rounds_completed})[/green]")
    else:
        console.print(f"[dim]Already approved: {cluster['cluster_name']}[/dim]")

    save_registry(reg)
    return reg


def _do_reject(cluster: dict, reg: ApprovalRegistry) -> ApprovalRegistry:
    """Add cluster to rejected list."""
    cid = cluster["cluster_id"]
    reg.clusters["deferred"] = [e for e in reg.clusters["deferred"] if e["cluster_id"] != cid]
    reg.clusters["approved"] = [e for e in reg.clusters["approved"] if e["cluster_id"] != cid]

    entry = {"cluster_id": cid, "cluster_name": cluster["cluster_name"], "size": cluster["size"]}
    if not any(e["cluster_id"] == cid for e in reg.clusters["rejected"]):
        reg.clusters["rejected"].append(entry)

    console.print(f"[red]Rejected: {cluster['cluster_name']}[/red]")
    save_registry(reg)
    return reg


def _do_defer(cluster: dict, reg: ApprovalRegistry) -> ApprovalRegistry:
    """Mark cluster as deferred for later review."""
    cid = cluster["cluster_id"]
    # Remove from approved/rejected if re-deferring
    reg.clusters["approved"] = [e for e in reg.clusters["approved"] if e["cluster_id"] != cid]
    reg.clusters["rejected"] = [e for e in reg.clusters["rejected"] if e["cluster_id"] != cid]

    entry = {
        "cluster_id": cid,
        "cluster_name": cluster["cluster_name"],
        "size": cluster["size"],
        "silhouette": cluster["silhouette"],
        "members": cluster["members"],
    }
    # Avoid duplicate defer entries
    if not any(e["cluster_id"] == cid for e in reg.clusters["deferred"]):
        reg.clusters["deferred"].append(entry)

    console.print(f"[blue]Deferred: {cluster['cluster_name']}[/blue]")
    save_registry(reg)
    return reg


def _do_rename(cluster: dict, reg: ApprovalRegistry, cache_dir: Path) -> Optional[str]:
    """Rename a cluster via LLM naming. Updates all member cache files."""
    cid = cluster["cluster_id"]

    # Load member bios for naming
    bios = []
    for uname in cluster["members"][:10]:
        acct_file = cache_dir / f"{uname}.json"
        if acct_file.exists():
            try:
                d = json.load(open(acct_file))
                bio = d.get("description", "")
                if bio:
                    bios.append(bio)
            except Exception:
                pass

    if not bios:
        console.print("[yellow]No bios available for naming. Using rule-based fallback.[/yellow]")

    new_name = name_cluster(bios) if bios else name_cluster([])

    # Update all member cache files
    for uname in cluster["members"]:
        acct_file = cache_dir / f"{uname}.json"
        if acct_file.exists():
            try:
                d = json.load(open(acct_file))
                d["cluster_name"] = new_name
                json.dump(d, open(acct_file, "w"), indent=2)
            except Exception:
                pass

    # Update registry if already approved
    for entry in reg.clusters["approved"]:
        if entry["cluster_id"] == cid:
            entry["cluster_name"] = new_name

    console.print(f"[green]Renamed to: {new_name}[/green]")
    save_registry(reg)
    return new_name


def _prompt_merge_target(cluster: dict, all_clusters: list[dict]) -> Optional[dict]:
    """Prompt user to select a merge target cluster."""
    other_clusters = [c for c in all_clusters if c["cluster_id"] != cluster["cluster_id"]]
    if not other_clusters:
        return None

    choices = [f"{c['cluster_name']} ({c['size']} members)" for c in other_clusters]
    choices.append("Cancel")

    choice = questionary.select(
        f"Merge '[cyan]{cluster['cluster_name']}[/cyan]' with which cluster?",
        choices=choices,
    ).ask()

    if choice and choice != "Cancel":
        idx = choices.index(choice)
        return other_clusters[idx]
    return None


def _do_split(
    cluster: dict,
    member_scores: dict[int, dict[str, float]],
    cache_dir: Path,
) -> list[str]:
    """Split: user selects members to move to nearest neighbor cluster.

    Per D-09: Split moves selected members to nearest neighbor or re-review.
    Returns list of usernames that were moved.
    """
    cid = cluster["cluster_id"]
    details = get_cluster_member_details(cid, member_scores, cache_dir, top_n=50)

    # Multi-select which members to move
    member_choices = [f"{d['username']} (conf={d['confidence']:.3f})" for d in details]
    member_choices.append("Done selecting")

    selected = questionary.checkbox(
        f"Select members to move out of '[cyan]{cluster['cluster_name']}[/cyan]':",
        choices=member_choices,
    ).ask()

    if not selected or "Done selecting" in selected:
        return []

    # Extract usernames from selections
    moved_usernames = []
    for choice in selected:
        if choice == "Done selecting":
            continue
        # Parse "username (conf=0.XXX)" format
        uname = choice.rsplit(" (conf=", 1)[0]
        moved_usernames.append(uname)

    if not moved_usernames:
        return []

    # Call split_cluster to reassign
    moved = split_cluster(cid, moved_usernames, cache_dir)
    return moved