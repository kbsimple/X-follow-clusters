"""Test driver script for the enrichment pipeline.

A quick manual testing script that:
1. Loads environment variables from .env file
2. Authenticates with X API via OAuth 2.0 PKCE
3. Parses data/following.js for account IDs
4. Identifies accounts without existing enrichment cache
5. Enriches up to 5 uncached accounts
6. Prints progress and summary

Usage:
    .venv/bin/python -m src.enrich.test_enrich
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.auth.x_auth import ensure_authenticated
from src.enrich.api_client import USER_FIELDS, XEnrichmentClient
from src.parse.following_parser import parse_following_js

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def print_enriched_profile(user: dict) -> None:
    """Print enriched profile data in a formatted block.

    Args:
        user: User dict from API response.
    """
    account_id = user.get("id", "unknown")
    username = user.get("username", "unknown")
    name = user.get("name", "unknown")
    bio = user.get("description") or ""
    location = user.get("location") or ""
    metrics = user.get("public_metrics", {})
    verified = user.get("verified", False)
    protected = user.get("protected", False)
    needs_scraping = user.get("needs_scraping", False)

    # Truncate bio if longer than 100 chars
    bio_display = bio[:100] + "..." if len(bio) > 100 else bio
    if not bio_display:
        bio_display = "(no bio)"

    print(f"    ┌─────────────────────────────────────────────────")
    print(f"    │ ID:             {account_id}")
    print(f"    │ Username:       @{username}")
    print(f"    │ Name:           {name}")
    print(f"    │ Bio:            {bio_display}")
    print(f"    │ Location:       {location or '(no location)'}")
    print(f"    │ Followers:      {metrics.get('followers_count', 0):,}")
    print(f"    │ Following:      {metrics.get('following_count', 0):,}")
    print(f"    │ Tweets:         {metrics.get('tweet_count', 0):,}")
    print(f"    │ Listed:         {metrics.get('listed_count', 0):,}")
    print(f"    │ Verified:       {verified}")
    print(f"    │ Protected:      {protected}")
    print(f"    │ Needs Scraping: {needs_scraping}")
    print(f"    └─────────────────────────────────────────────────")


def main() -> int:
    """Run the enrichment test driver.

    Returns:
        0 on success, 1 on error.
    """
    print("=" * 60)
    print("Enrichment Test Driver")
    print("=" * 60)

    # Step 1: Load environment variables from .env file
    print("\n[Step 1] Loading environment variables from .env file...")
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)
        print("  Loaded .env file")
    else:
        print("  No .env file found, using existing environment variables")

    # Step 2: Authenticate with X API
    print("\n[Step 2] Authenticating with X API (OAuth 2.0 PKCE)...")
    try:
        auth = ensure_authenticated()
        print(f"  Authentication successful!")
    except Exception as e:
        print(f"  ERROR: Authentication failed: {e}")
        return 1

    # Step 3: Parse following.js
    print("\n[Step 3] Parsing data/following.js...")
    following_path = Path("data/following.js")
    if not following_path.exists():
        print(f"  ERROR: {following_path} not found")
        return 1

    try:
        records = parse_following_js(following_path)
        print(f"  Found {len(records)} accounts in following.js")
    except Exception as e:
        print(f"  ERROR: Failed to parse following.js: {e}")
        return 1

    # Step 4: Scan for existing cache files
    print("\n[Step 4] Scanning for existing enrichment cache...")
    cache_dir = Path("data/enrichment")
    cache_dir.mkdir(parents=True, exist_ok=True)

    cached_ids = set()
    if cache_dir.exists():
        for cache_file in cache_dir.glob("*.json"):
            # Extract account_id from filename (e.g., "12345.json" -> "12345")
            cached_ids.add(cache_file.stem)

    print(f"  Found {len(cached_ids)} cached accounts")

    # Step 5: Filter to uncached accounts
    print("\n[Step 5] Identifying uncached accounts...")
    all_ids = {r.account_id for r in records}
    uncached_ids = all_ids - cached_ids
    uncached_list = sorted(uncached_ids)

    print(f"  Total accounts in following.js: {len(all_ids)}")
    print(f"  Already cached: {len(cached_ids)}")
    print(f"  Need enrichment: {len(uncached_list)}")

    if not uncached_list:
        print("\n  All accounts already cached. Nothing to enrich.")
        return 0

    # Step 6: Take first 5 uncached accounts
    sample_size = min(5, len(uncached_list))
    sample_ids = uncached_list[:sample_size]
    print(f"\n[Step 6] Taking first {sample_size} uncached accounts for enrichment:")
    print("  Cache status for each account:")
    for aid in sample_ids:
        cache_file = cache_dir / f"{aid}.json"
        if cache_file.exists():
            try:
                cached_data = json.loads(cache_file.read_text())
                username = cached_data.get("username", "unknown")
                name = cached_data.get("name", "unknown")
                has_bio = bool(cached_data.get("description"))
                has_location = bool(cached_data.get("location"))
                needs_scraping = cached_data.get("needs_scraping", False)
                print(f"    - {aid}: CACHED @{username} ({name})")
                print(f"        has_bio={has_bio}, has_location={has_location}, needs_scraping={needs_scraping}")
            except Exception as e:
                print(f"    - {aid}: CACHED (error reading: {e})")
        else:
            print(f"    - {aid}: NOT CACHED")

    # Step 7: Create enrichment client and enrich
    print("\n[Step 7] Enriching accounts...")
    client = XEnrichmentClient(auth, cache_dir=cache_dir)

    # Show what fields are being requested
    print(f"  Requesting fields: {USER_FIELDS}")

    enriched_count = 0
    error_count = 0
    errors = []

    try:
        response = client.get_users(sample_ids)

        # Track results
        enriched_count = len(response.data)
        error_count = len(response.errors)

        # Print enriched profile data for each account
        print("\n  Enriched profiles:")
        for user in response.data:
            print_enriched_profile(user)

        # Track errors
        for err in response.errors:
            account_id = err.get("resource_id", "unknown")
            error_detail = err.get("detail", str(err))
            errors.append((account_id, error_detail))
            print(f"    x Error: {account_id} - {error_detail}")

    except Exception as e:
        print(f"  ERROR during enrichment: {e}")
        return 1

    # Step 8: Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total accounts in following.js:    {len(all_ids)}")
    print(f"  Already cached:                    {len(cached_ids)}")
    print(f"  Newly enriched (this run):         {enriched_count}")
    print(f"  Errors:                            {error_count}")

    if errors:
        print("\n  Error details:")
        for account_id, detail in errors:
            print(f"    - {account_id}: {detail}")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())