from rich.console import Console
from rich.table import Table


def display_size_histogram(size_histogram: dict) -> None:
    """Display cluster size histogram and warn if skewed.

    Warns if pct_under_5 > 0.5 (more than 50% of clusters have < 5 members).
    Prints histogram summary table with cluster IDs and member counts.

    Parameters
    ----------
    size_histogram : dict
        Histogram dict from generate_size_histogram() with keys:
        counts, bins, total_clusters, clusters_under_5, pct_under_5.
    """
    console = Console()

    pct = size_histogram.get("pct_under_5", 0.0)
    under_5 = size_histogram.get("clusters_under_5", 0)
    total = size_histogram.get("total_clusters", 0)

    # Warning banner if heavily skewed
    if pct > 0.5:
        console.print(f"[bold red]WARNING: {under_5}/{total} clusters ({pct*100:.0f}%) have fewer than 5 members.[/bold red]")
        console.print("[yellow]Clusters with very few members may be noise or over-fragmented.[/yellow]")
        console.print("[yellow]Consider merging small clusters or re-running with different algorithm settings.[/yellow]\n")
    else:
        console.print(f"[green]Size distribution OK: {total - under_5}/{total} clusters have 5+ members.[/green]\n")

    # Histogram table
    table = Table(title="Cluster Size Distribution", show_header=True)
    table.add_column("Cluster ID", justify="right", style="cyan")
    table.add_column("Size", justify="right", style="magenta")

    counts = size_histogram.get("counts", [])
    bins = size_histogram.get("bins", [])
    for cid, cnt in zip(bins, counts):
        flag = " [yellow](small)[/yellow]" if cnt < 5 else ""
        table.add_row(str(cid), str(cnt) + flag)

    console.print(table)
    console.print()
