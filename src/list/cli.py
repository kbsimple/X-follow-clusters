"""Phase 6 CLI: Create X API lists from approved clusters and export data.

Usage:
    python -m src.list.cli --dry-run    # Default: show what would be created
    python -m src.list.cli --execute    # Actually create lists and export data
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import requests
import tweepy
from rich.console import Console
from rich.table import Table

from src.auth.x_auth import get_auth, verify_credentials, AuthError, XAuth
from src.list.creator import (
    verify_credentials_before_listCreation,
    get_approved_clusters,
    precheck_conflicts,
    create_list_from_cluster,
    add_members_chunked,
    list_size_validation,
    create_lists_from_clusters,
    ListCreationError,
)
from src.review.registry import load_registry
from src.review.automation import is_automation_enabled

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)


def build_tweepy_client(auth: XAuth) -> tweepy.Client:
    """Build an authenticated tweepy Client."""
    return tweepy.Client(
        consumer_key=auth.api_key,
        consumer_secret=auth.api_secret,
        access_token=auth.access_token,
        access_token_secret=auth.access_token_secret,
        bearer_token=auth.bearer_token,
        wait_on_rate_limit=False,
        return_type=requests.Response,
    )


def print_dry_run(approved: list[dict], deferred: list[dict]) -> None:
    """Print dry-run summary of what would be created."""
    console.print("\n[bold]=== Phase 6: Dry Run ===[/bold]")
    console.print(f"[cyan]Approved clusters ready for list creation: {len(approved)}[/cyan]\n")

    if approved:
        table = Table(title="Approved Clusters")
        table.add_column("Cluster Name", style="green")
        table.add_column("Members", justify="right")
        table.add_column("Silhouette", justify="right")
        for c in approved:
            table.add_row(
                c.get("cluster_name", ""),
                str(c.get("size", "")),
                f"{c.get('silhouette', 0):.3f}" if c.get("silhouette") else "N/A",
            )
        console.print(table)

    if deferred:
        console.print(f"\n[yellow]Deferred clusters (no list will be created): {len(deferred)}[/yellow]")
        for c in deferred:
            console.print(f"  - {c.get('cluster_name', '')} ({c.get('size', 0)} members)")

    total_members = sum(c.get("size", 0) for c in approved)
    console.print(f"\n[green]Ready to create {len(approved)} lists ({total_members} total members)[/green]")
    console.print("[dim]Run with --execute to create lists for real[/dim]\n")


def handle_conflicts(
    conflicts: list[str],
    approved: list[dict],
) -> tuple[list[dict], list[str]]:
    """Handle naming conflicts via interactive prompts.

    Returns the list of clusters to create and a list of renamed cluster names.
    """
    import questionary

    renamed: list[str] = []
    remaining: list[dict] = []

    for cluster in approved:
        name = cluster.get("cluster_name", "")
        if name not in conflicts:
            remaining.append(cluster)
            continue

        console.print(f"\n[yellow]List name already exists: '{name}'[/yellow]")
        choice = questionary.select(
            f"How would you like to handle '{name}'?",
            choices=[
                "Rename new list",
                "Skip this list",
                "Abort entirely",
            ],
        ).ask()

        if choice == "Abort entirely":
            console.print("[red]Aborted by user.[/red]")
            raise SystemExit(1)
        elif choice == "Skip this list":
            console.print(f"  Skipping '{name}'")
            renamed.append(name)  # Mark as skipped
        elif choice == "Rename new list":
            new_name = questionary.text(
                "Enter new list name:",
                default=f"{name} (from cluster)",
            ).ask()
            cluster = dict(cluster)
            cluster["cluster_name"] = new_name
            remaining.append(cluster)
            renamed.append(f"{name} -> {new_name}")
            console.print(f"  Renamed to '{new_name}'")

    return remaining, renamed


def execute_list_creation(approved: list[dict], deferred: list[dict]) -> None:
    """Execute list creation (non-dry-run)."""
    # Verify credentials
    try:
        auth = verify_credentials_before_listCreation()
    except SystemExit:
        raise

    client = build_tweepy_client(auth)
    reg = load_registry()
    automation_enabled = is_automation_enabled(reg)

    # Pre-check all conflicts before any creation
    conflicts = precheck_conflicts(client, approved)
    if conflicts:
        console.print(f"\n[yellow]Found {len(conflicts)} naming conflicts![/yellow]")
        approved, renamed = handle_conflicts(list(conflicts.keys()), approved)
        for r in renamed:
            logger.info("Conflict resolved: %s", r)

    # Validate cluster sizes
    valid_clusters = list_size_validation(client, approved)
    skipped = [c for c in approved if c not in valid_clusters]
    for c in skipped:
        logger.warning("Skipping '%s' due to size validation", c.get("cluster_name"))

    if not valid_clusters:
        console.print("[yellow]No clusters pass validation. Nothing to create.[/yellow]")
        return

    # Automation mode check
    if automation_enabled:
        console.print(
            f"\n[cyan]Automation mode: creating {len(valid_clusters)} lists without confirmation[/cyan]"
        )
    else:
        console.print(f"\n[bold]Creating {len(valid_clusters)} lists:[/bold]")
        import questionary
        to_create: list[dict] = []
        for cluster in valid_clusters:
            name = cluster.get("cluster_name", "")
            size = cluster.get("size", 0)
            choice = questionary.select(
                f"Create list '{name}' ({size} members)?",
                choices=["Yes, create it", "Skip", "Abort all"],
            ).ask()
            if choice == "Abort all":
                console.print("[yellow]Aborted.[/yellow]")
                raise SystemExit(0)
            elif choice == "Skip":
                logger.info("Skipped '%s' by user choice", name)
            else:
                to_create.append(cluster)
        valid_clusters = to_create

    # Create lists
    created_count = 0
    total_members = 0
    for cluster in valid_clusters:
        name = cluster.get("cluster_name", "")
        try:
            list_id = create_list_from_cluster(client, cluster)
            usernames = [
                m.get("username", "") for m in cluster.get("members", [])
            ]
            usernames = [u for u in usernames if u]
            count = add_members_chunked(client, list_id, usernames)
            created_count += 1
            total_members += count
            console.print(
                f"[green]Created list '{name}' with {count} members[/green]"
            )
            time.sleep(0.5)
        except ListCreationError as e:
            console.print(f"[red]Failed to create '{name}': {e.message}[/red]")
        except Exception as e:
            console.print(f"[red]Error creating '{name}': {e}[/red]")

    console.print(
        f"\n[green]Summary: {created_count} lists created, {total_members} members added[/green]"
    )

    # Note about deferred clusters
    if deferred:
        console.print(
            f"\n[yellow]Note: {len(deferred)} deferred clusters are exported to "
            "CSV by this phase (no X API list created for them).[/yellow]"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 6: Create X API lists from approved clusters",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be created without making API calls (default)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute list creation and data export",
    )
    parser.add_argument(
        "--skip-credentials-check",
        action="store_true",
        help="Bypass credential verification (for testing only)",
    )
    args = parser.parse_args()

    # Load registry
    try:
        approved, deferred = get_approved_clusters()
    except SystemExit:
        raise

    if args.execute:
        # Import export here to avoid hard dependency when only running --dry-run
        from src.list.exporter import export_all

        try:
            execute_list_creation(approved, deferred)
        except SystemExit:
            raise
        finally:
            # Always run export after list creation attempt
            try:
                console.print("\n[cyan]Exporting data...[/cyan]")
                result = export_all()
                console.print(
                    f"[green]Export complete: {result}[/green]"
                )
            except Exception as e:
                console.print(f"[red]Export failed: {e}[/red]")
    else:
        print_dry_run(approved, deferred)


if __name__ == "__main__":
    main()
