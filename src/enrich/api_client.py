"""X API enrichment client with rate limit tracking and immediate caching.

Wraps tweepy.Client with:
- Immediate disk caching of each response (one file per account)
- Rate limit header parsing and custom backoff
- Error code tracking for suspended (63) and protected (179) accounts

Usage:
    from src.enrich.api_client import XEnrichmentClient
    from src.auth import XAuth

    client = XEnrichmentClient(auth)
    result = client.get_users(["123", "456"])
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import tweepy

from src.enrich.rate_limiter import ExponentialBackoff, RateLimitError

logger = logging.getLogger(__name__)

# User fields to request from GET /2/users
USER_FIELDS = [
    "description",      # bio text
    "location",         # user-defined location
    "public_metrics",    # followers_count, following_count, tweet_count, listed_count
    "verified",         # verified status
    "protected",         # protected status
    "pinned_tweet_id",  # pinned tweet ID (text requires separate call)
]


class CacheWriteError(Exception):
    """Raised when a cache file write fails."""

    def __init__(self, account_id: str, path: str, cause: str):
        super().__init__(f"Failed to write cache for {account_id} at {path}: {cause}")
        self.account_id = account_id
        self.path = path
        self.cause = cause


@dataclass
class EnrichmentResponse:
    """Result of a batch get_users call.

    Attributes:
        data: List of user dicts from the API.
        errors: List of error dicts (including suspended/protected).
        response: Raw requests.Response for header access.
    """

    data: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    response: requests.Response


class XEnrichmentClient:
    """Tweepy client wrapper with rate limiting and immediate caching.

    Uses return_type=requests.Response to access raw rate limit headers.
    Writes each user's data to disk immediately upon receipt.
    """

    def __init__(
        self,
        auth,
        cache_dir: Path | str = Path("data/enrichment"),
        backoff: ExponentialBackoff | None = None,
    ):
        """Initialize the enrichment client.

        Args:
            auth: XAuth instance with API credentials.
            cache_dir: Directory to write per-account JSON cache files.
            backoff: ExponentialBackoff instance for rate limit handling.
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.backoff = backoff or ExponentialBackoff()

        # Create tweepy Client with OAuth 1.0a (user context = 900 req/15min)
        # wait_on_rate_limit=False so we handle 429s ourselves
        self._client = tweepy.Client(
            consumer_key=auth.api_key,
            consumer_secret=auth.api_secret,
            access_token=auth.access_token,
            access_token_secret=auth.access_token_secret,
            bearer_token=auth.bearer_token,
            wait_on_rate_limit=False,
            return_type=requests.Response,  # Required for rate limit header access
        )

    def get_users(
        self,
        ids: list[str],
        max_attempts: int = 3,
    ) -> EnrichmentResponse:
        """Fetch user profiles for a batch of account IDs.

        Args:
            ids: List of account ID strings (up to 100).
            max_attempts: Number of retry attempts on rate limit errors.

        Returns:
            EnrichmentResponse with data, errors, and raw response.

        Raises:
            RateLimitError: When rate limit is hit and all retries exhausted.
            tweepy.Forbidden: For non-retryable errors.
        """
        for attempt in range(max_attempts):
            try:
                response = self._client.get_users(
                    ids=ids,
                    user_fields=USER_FIELDS,
                )

                # Parse rate limit headers
                remaining = int(response.headers.get("x-rate-limit-remaining", 0))
                reset_ts = int(response.headers.get("x-rate-limit-reset", 0))

                # Check if we would hit rate limit with next batch
                # With 900/15min limit, we have plenty of room
                if remaining == 0:
                    raise RateLimitError(
                        reset_timestamp=reset_ts,
                        retry_after=self.backoff.delay(),
                        remaining=remaining,
                    )

                # Parse response body as JSON
                body = response.json()

                data = body.get("data") or []
                errors = body.get("errors") or []

                # Write each user's data to cache immediately
                for user in data:
                    self._cache_user(user)

                return EnrichmentResponse(
                    data=data,
                    errors=errors,
                    response=response,
                )

            except RateLimitError:
                if attempt < max_attempts - 1:
                    delay = self.backoff.delay()
                    logger.warning("Rate limited, waiting %.1fs before retry", delay)
                    time.sleep(delay)
                    continue
                raise

        # Should not reach here
        raise RateLimitError(
            reset_timestamp=0,
            retry_after=self.backoff.delay(),
            remaining=0,
        )

    def _cache_user(self, user: dict[str, Any]) -> None:
        """Write a single user's data to cache.

        Args:
            user: User dict from API response.

        Raises:
            CacheWriteError: If write fails (logged but does not raise).
        """
        account_id = user.get("id")
        if not account_id:
            logger.warning("Cannot cache user with no ID: %s", user)
            return

        path = self.cache_dir / f"{account_id}.json"

        # Add needs_scraping flag if bio or location is missing
        enriched = dict(user)
        bio = user.get("description") or ""
        location = user.get("location") or ""
        if not bio or not location:
            enriched["needs_scraping"] = True
        else:
            enriched["needs_scraping"] = False

        try:
            path.write_text(json.dumps(enriched, indent=2), encoding="utf-8")
        except Exception as e:
            # Log warning but do NOT retry - continue with enrichment
            logger.warning(
                "Cache write failed for %s at %s: %s",
                account_id,
                path,
                e,
            )
            # Still raise as CacheWriteError per spec, but don't stop processing
            raise CacheWriteError(
                account_id=account_id,
                path=str(path),
                cause=str(e),
            )
