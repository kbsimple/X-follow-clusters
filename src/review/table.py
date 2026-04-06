"""Rich table rendering for cluster summary and member detail display."""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from typing import Optional
import math

console = Console()

def _status_color(status: str) -> str:
    """Return color style for cluster status."""
    return {
        "pending": "yellow",
        "approved": "green",
        "rejected": "red",
        "deferred": "blue",
    }.get(status, "white")


def display_cluster_table(
    summaries: list[dict],
    member_scores: dict[int, dict[str, float]],
    registry_status: dict[int, str],
) -> None:
    """Display all clusters in a summary table.

    Per REVIEW-01 and D-02: Table columns: Cluster Name | Members Preview | Size | Silhouette | Status

    Args:
        summaries: List from build_cluster_summary() — {cluster_id, cluster_name, size, silhouette, members}
        member_scores: Per-member confidence from compute_member_confidences()
        registry_status: {cluster_id: "pending"|"approved"|"rejected"|"deferred"}
    """
    table = Table(
        title="Suggested Clusters",
        show_header=True,
        header_style="bold white",
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Cluster Name", style="cyan bold", width=25)
    table.add_column("Members Preview", style="white", width=30)
    table.add_column("Size", justify="right", style="magenta", width=5)
    table.add_column("Silhouette", justify="right", width=10)
    table.add_column("Status", width=10)

    for i, cluster in enumerate(summaries, 1):
        cid = cluster["cluster_id"]
        name = cluster["cluster_name"]
        size = cluster["size"]
        sil = cluster["silhouette"]

        # Members preview: top 3 by confidence
        scores = member_scores.get(cid, {})
        top_members = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        preview = ", ".join(u for u, _ in top_members) if top_members else "(no data)"

        # Silhouette color
        if size < 5:
            sil_str = "N/A"
            sil_style = "dim"
        elif sil >= 0.5:
            sil_str = f"{sil:.3f}"
            sil_style = "green"
        elif sil >= 0.3:
            sil_str = f"{sil:.3f}"
            sil_style = "yellow"
        else:
            sil_str = f"{sil:.3f}"
            sil_style = "red bold"

        status = registry_status.get(cid, "pending")
        status_style = _status_color(status)

        table.add_row(
            str(i),
            name,
            f"[dim]{preview}[/dim]",
            str(size),
            f"[{sil_style}]{sil_str}[/]",
            f"[{status_style}]{status}[/]",
        )

    console.print(table)


def display_member_details(
    cluster: dict,
    member_details: list[dict],
    all_member_scores: dict[int, dict[str, float]],
) -> None:
    """Display detailed per-member view for a single cluster.

    Per REVIEW-02: Per-member confidence displayed with username and bio snippet.
    Shows top 20 members sorted by confidence descending.

    Args:
        cluster: {cluster_id, cluster_name, size, silhouette, members}
        member_details: from get_cluster_member_details()
        all_member_scores: full scores dict for comparison
    """
    cid = cluster["cluster_id"]
    sil = cluster["silhouette"]
    import math

    sil_str = f"{sil:.3f}" if not math.isnan(sil) else "N/A"

    panel_title = (
        f"[bold cyan]{cluster['cluster_name']}[/bold cyan]  "
        f"[dim]|[/dim]  [magenta]{cluster['size']} members[/magenta]  "
        f"[dim]|[/dim]  silhouette={sil_str}"
    )

    # Build member rows
    table = Table(show_header=True, header_style="bold white", box=None)
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Username", style="cyan", width=20)
    table.add_column("Confidence", justify="right", width=10)
    table.add_column("Bio snippet", style="white")

    for rank, member in enumerate(member_details, 1):
        conf = member["confidence"]
        if math.isnan(conf):
            conf_str = "N/A"
            conf_style = "dim"
        elif conf >= 0.5:
            conf_str = f"{conf:.3f}"
            conf_style = "green"
        elif conf >= 0.3:
            conf_str = f"{conf:.3f}"
            conf_style = "yellow"
        else:
            conf_str = f"{conf:.3f}"
            conf_style = "red"

        bio = member["bio"][:60] + ("..." if len(member["bio"]) > 60 else "")

        table.add_row(
            str(rank),
            member["username"],
            f"[{conf_style}]{conf_str}[/]",
            bio or "[dim]No bio[/dim]",
        )

    console.print(Panel(table, title=panel_title, border_style="cyan"))


def print_review_prompt(cluster: dict, rank: int, total: int) -> None:
    """Print the action prompt for a single cluster during review."""
    console.print(f"\n[bold]Cluster {rank}/{total}:[/bold] [cyan]{cluster['cluster_name']}[/cyan] ({cluster['size']} members, sil={cluster['silhouette']:.3f})")
