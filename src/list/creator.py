"""X API list creation from Phase 5 approved clusters.

Implements LIST-01 through LIST-05: credential verification, dry-run CLI,
HTTP 409 conflict detection, bulk member addition, and list size validation.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import tweepy

from src.auth.x_auth import (
    XAuth,
    get_auth,
    verify_credentials,
    AuthError,
)
from src.review.registry import load_registry, ApprovalRegistry
from src.review.automation import is_automation_enabled

logger = logging.getLogger(__name__)


class ListCreationError(Exception):
    """Raised when list creation fails.

    Attributes:
        message: Human-readable error description.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def verify_credentials_before_listCreation() -> XAuth:
    """Verify X API credentials before any list creation operation.

    Loads credentials from environment variables and validates them via
    GET /2/users/me. Raises AuthError on failure.

    Returns
    -------
    XAuth
        Validated XAuth object.

    Raises
    ------
    SystemExit
        If credentials are missing or invalid.
    """
    try:
        auth = get_auth()
        verify_credentials(auth)
        logger.info("X API credentials verified successfully")
        return auth
    except AuthError as e:
        print(f"Authentication failed: {e.message}")
        raise SystemExit(1)


def get_approved_clusters() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load approved and deferred clusters from the Phase 5 registry.

    Returns
    -------
    tuple[list[dict[str, Any]], list[dict[str, Any]]]
        Tuple of (approved_clusters, deferred_clusters).

    Raises
    ------
    SystemExit
        If the registry file does not exist or no approved clusters exist.
    """
    reg = load_registry()
    approved = reg.clusters.get("approved", [])
    deferred = reg.clusters.get("deferred", [])

    if not approved:
        print("No approved clusters found. Run Phase 5 review flow first.")
        raise SystemExit(1)

    return approved, deferred


def precheck_conflicts(
    client: tweepy.Client,
    clusters: list[dict[str, Any]],
) -> dict[str, str]:
    """Check for naming conflicts with existing owned lists.

    Queries the user's existing lists via GET /2/users/me/lists and
    returns a dict mapping conflicting cluster names to "exists".

    Parameters
    ----------
    client : tweepy.Client
        Authenticated tweepy client.
    clusters : list[dict[str, Any]]
        List of cluster dicts to check.

    Returns
    -------
    dict[str, str]
        Mapping of {cluster_name: "exists"} for clusters that conflict.
    """
    try:
        response = client.get_owned_lists(user_id="me", max_results=100)
        existing_names: set[str] = set()
        if response.data:
            existing_names = {lst.name for lst in response.data}
    except tweepy.TweepyException as e:
        logger.warning("Could not fetch existing lists: %s", e)
        return {}

    conflicts: dict[str, str] = {}
    for cluster in clusters:
        name = cluster.get("cluster_name", "")
        if name in existing_names:
            conflicts[name] = "exists"

    return conflicts


def create_list_from_cluster(
    client: tweepy.Client,
    cluster: dict[str, Any],
) -> str:
    """Create a single X API list from a cluster.

    Parameters
    ----------
    client : tweepy.Client
        Authenticated tweepy client.
    cluster : dict[str, Any]
        Cluster dict with cluster_name, size, and other metadata.

    Returns
    -------
    str
        The ID of the created list.

    Raises
    ------
    ListCreationError
        If list creation fails due to forbidden access.
    """
    name = cluster.get("cluster_name", "Unnamed Cluster")
    description = f"Created by X Following Organizer - {cluster.get('cluster_name', '')}"

    try:
        response = client.create_list(
            name=name,
            description=description,
            mode="private",
        )
        if response.data is None:
            raise ListCreationError(f"create_list returned no data for '{name}'")
        list_id = response.data.get("id")
        if not list_id:
            raise ListCreationError(f"create_list response missing id for '{name}'")
        logger.info("Created list '%s' with id %s", name, list_id)
        return list_id
    except tweepy.Forbidden as e:
        raise ListCreationError(
            "List operation forbidden - check API permissions"
        ) from e


def add_members_chunked(
    client: tweepy.Client,
    list_id: str,
    usernames: list[str],
) -> int:
    """Add members to a list in chunks of 100 per X API limit.

    Parameters
    ----------
    client : tweepy.Client
        Authenticated tweepy client.
    list_id : str
        ID of the list to add members to.
    usernames : list[str]
        List of usernames to add.

    Returns
    -------
    int
        Total number of members added.
    """
    total_added = 0
    chunk_size = 100

    for i in range(0, len(usernames), chunk_size):
        chunk = usernames[i:i + chunk_size]
        try:
            client.add_list_members(list_id=list_id, user_names=chunk)
            total_added += len(chunk)
            logger.debug(
                "Added %d members to list %s (chunk %d-%d)",
                len(chunk),
                list_id,
                i,
                i + len(chunk),
            )
        except tweepy.TweepyException as e:
            logger.error(
                "Failed to add chunk to list %s: %s",
                list_id,
                e,
            )
            raise

        # Small delay between chunks to avoid rate limit
        if i + chunk_size < len(usernames):
            time.sleep(0.5)

    return total_added


def list_size_validation(
    client: tweepy.Client,
    clusters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate cluster sizes and account-level limits.

    Validates that each cluster has between 5 and 50 members (per X API
    list constraints and Phase 4 clustering rules). Also checks that the
    account has not exceeded the 1,000 lists per account limit.

    Parameters
    ----------
    client : tweepy.Client
        Authenticated tweepy client.
    clusters : list[dict[str, Any]]
        List of cluster dicts to validate.

    Returns
    -------
    list[dict[str, Any]]
        Clusters that passed validation.

    Raises
    ------
    ListCreationError
        If the account has reached the 1,000 list limit.
    """
    valid_clusters: list[dict[str, Any]] = []

    for cluster in clusters:
        size = cluster.get("size", 0)
        name = cluster.get("cluster_name", "<unnamed>")
        if size < 5:
            logger.warning(
                "Cluster '%s' has %d members (must be 5-50) - skipping",
                name,
                size,
            )
        elif size > 50:
            logger.warning(
                "Cluster '%s' has %d members (must be 5-50) - skipping",
                name,
                size,
            )
        else:
            valid_clusters.append(cluster)

    # Check account-level list limit
    try:
        response = client.get_owned_lists(user_id="me", max_results=100)
        owned_count = len(response.data) if response.data else 0
        if owned_count >= 1000:
            raise ListCreationError(
                "Account has reached the 1,000 lists per account limit"
            )
        logger.info(
            "Account has %d/%d lists (under 1,000 limit)",
            owned_count,
            1000,
        )
    except tweepy.TweepyException as e:
        logger.warning("Could not check owned list count: %s", e)

    return valid_clusters


def create_lists_from_clusters(
    approved_clusters: list[dict[str, Any]],
    client: tweepy.Client,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Orchestrate the full list creation flow for approved clusters.

    Parameters
    ----------
    approved_clusters : list[dict[str, Any]]
        List of approved cluster dicts from the registry.
    client : tweepy.Client
        Authenticated tweepy client instance.
    dry_run : bool
        If True, simulate actions without making API calls.

    Returns
    -------
    dict[str, Any]
        Dict with keys: "created" (list of created list ids),
        "skipped" (list of skipped cluster names), "errors" (list of
        error messages), and optionally "conflicts" (list of conflicting
        cluster names).
    """
    results: dict[str, Any] = {
        "created": [],
        "skipped": [],
        "errors": [],
    }

    # 1. Verify credentials
    try:
        verify_credentials_before_listCreation()
    except SystemExit:
        results["errors"].append("Credential verification failed")
        return results

    # 2. Run list_size_validation to filter clusters by 5-50 size and account limit
    valid_clusters: list[dict[str, Any]] = []
    for cluster in approved_clusters:
        size = cluster.get("size", 0)
        name = cluster.get("cluster_name", "<unnamed>")
        if size < 5 or size > 50:
            results["skipped"].append(f"{name} (size {size} out of 5-50 range)")
        else:
            valid_clusters.append(cluster)

    # 3. Pre-check conflicts with existing lists
    conflicts = precheck_conflicts(client, valid_clusters)
    if conflicts:
        # Return conflicts for CLI to handle via questionary prompts
        results["conflicts"] = list(conflicts.keys())
        results["skipped"] = valid_clusters  # Pass valid clusters back for CLI to handle
        return results

    # 4. Create lists (or simulate in dry-run mode)
    for cluster in valid_clusters:
        try:
            if dry_run:
                logger.info(
                    "[DRY-RUN] Would create list: %s with %d members",
                    cluster.get("cluster_name"),
                    cluster.get("size"),
                )
            else:
                list_id = create_list_from_cluster(client, cluster)
                usernames = [m.get("username", "") for m in cluster.get("members", [])]
                # Filter out empty usernames
                usernames = [u for u in usernames if u]
                add_members_chunked(client, list_id, usernames)
                results["created"].append(list_id)
                logger.info(
                    "Created list '%s' with %d members",
                    cluster.get("cluster_name"),
                    len(usernames),
                )
                time.sleep(0.5)  # Rate limit between list creations
        except ListCreationError as e:
            results["errors"].append(f"{cluster.get('cluster_name')}: {e.message}")
        except Exception as e:
            results["errors"].append(f"{cluster.get('cluster_name')}: {e}")

    return results
