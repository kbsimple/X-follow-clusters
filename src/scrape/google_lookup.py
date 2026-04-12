"""Google search lookup for cold-start X accounts via SerpApi.

Per D-06: Trigger only when account has no bio AND no website.
Per D-07: Extract title + snippet only from first organic result.
Per D-08: If SERPAPI_KEY absent, skip with warning (never block).
Per D-09: Track search count; warn at 200, fail gracefully at 250 (free tier limit).

Usage:
    from src.scrape.google_lookup import google_lookup_account, GoogleLookupResult

    result = google_lookup_account("username", cache_dir="data/enrichment")
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import serpapi
    _SERPAPI_AVAILABLE = True
except ImportError:
    _SERPAPI_AVAILABLE = False

logger = logging.getLogger(__name__)


# Track searches across all accounts for the session (per D-09)
_session_search_count = 0
_WARN_AT = 200
_FAIL_AT = 250


@dataclass
class GoogleLookupResult:
    """Result of a Google lookup for an X account.

    Attributes:
        username: The X account username looked up.
        result_title: Title from first organic Google result, or None.
        result_snippet: Snippet from first organic Google result, or None.
        search_count: Total searches performed in this session.
    """

    username: str
    result_title: str | None
    result_snippet: str | None
    search_count: int


def _perform_google_search(username: str) -> dict | None:
    """Perform Google search for an X account via SerpApi.

    Per D-07: Extract title + snippet only from first organic result.

    Args:
        username: X account username to search for.

    Returns:
        Dict with result_title and result_snippet, or None if no results.

    Raises:
        Warning logged at 200 searches, ValueError at 250.
    """
    global _session_search_count

    if not _SERPAPI_AVAILABLE:
        logger.warning("serpapi package not installed. Run: pip install serpapi")
        return None

    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        logger.warning("SERPAPI_KEY env var not set. Skipping Google search for %s", username)
        return None

    # Warn at 200, fail at 250 (per D-09)
    if _session_search_count >= _FAIL_AT:
        logger.warning("Google search count (%d) at free tier limit (250). Skipping %s.", _session_search_count, username)
        return None

    if _session_search_count == _WARN_AT:
        logger.warning("Google search count (%d) approaching limit (250).", _session_search_count)

    try:
        client = serpapi.Client(api_key=api_key)
        results = client.search({
            "engine": "google",
            "q": f'"{username}" site:x.com OR site:twitter.com',
            "num": 5,  # get a few results to disambiguate
        })

        _session_search_count += 1

        organic = results.get("organic_results", [])
        if not organic:
            return {"result_title": None, "result_snippet": None}

        # Per D-07: extract title + snippet only from first result
        first = organic[0]
        return {
            "result_title": first.get("title", ""),
            "result_snippet": first.get("snippet", ""),
        }

    except Exception as e:
        logger.warning("SerpApi error for %s: %s", username, e)
        return None


def google_lookup_account(
    username: str,
    cache_dir: Path | str = Path("data/enrichment"),
) -> GoogleLookupResult | None:
    """Look up an X account on Google for external context.

    Per D-06: trigger ONLY when account has no bio AND no website.
    Per D-07: extract title + snippet only.
    Per D-08: if SERPAPI_KEY absent, skip with warning (never block).

    Args:
        username: Account username.
        cache_dir: Directory containing {username}.json cache files.

    Returns:
        GoogleLookupResult if conditions met, None if no lookup was performed.
    """
    cache_dir = Path(cache_dir)
    cache_path = cache_dir / f"{username}.json"

    if not cache_path.exists():
        return None

    with open(cache_path, encoding="utf-8") as f:
        account: dict[str, Any] = json.load(f)

    bio = account.get("bio") or account.get("description", "")
    website = account.get("website", "")

    # Per D-06: only run if NO bio AND NO website
    if bio or website:
        return None

    # Perform the search
    result = _perform_google_search(username)
    if result is None:
        return GoogleLookupResult(
            username=username,
            result_title=None,
            result_snippet=None,
            search_count=_session_search_count,
        )

    # Cache the results (per D-18 for entity fields pattern)
    account["google_result_title"] = result["result_title"]
    account["google_result_snippet"] = result["result_snippet"]

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(account, f, indent=2)

    return GoogleLookupResult(
        username=username,
        result_title=result["result_title"],
        result_snippet=result["result_snippet"],
        search_count=_session_search_count,
    )


__all__ = ["google_lookup_account", "GoogleLookupResult", "_session_search_count"]