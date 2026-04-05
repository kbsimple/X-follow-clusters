"""Rate limit handling with exponential backoff and jitter.

Provides custom rate limit error handling for X API calls, replacing
tweepy's built-in simple sleep-until-reset with exponential backoff.

Usage:
    from src.enrich.rate_limiter import ExponentialBackoff, RateLimitError

    backoff = ExponentialBackoff()
    try:
        result = api_call()
    except RateLimitError as e:
        time.sleep(e.retry_after)
        # retry the call
"""

from __future__ import annotations

import random
import time


class RateLimitError(Exception):
    """Raised when an X API rate limit is hit (HTTP 429).

    Attributes:
        reset_timestamp: Unix timestamp when the rate limit resets.
        retry_after: Seconds to wait before retrying.
        remaining: Number of API calls remaining at the time of the error.
    """

    def __init__(self, reset_timestamp: int, retry_after: float, remaining: int):
        super().__init__(
            f"Rate limit hit. Resets at {reset_timestamp}, "
            f"retry after {retry_after:.1f}s, {remaining} calls remaining."
        )
        self.reset_timestamp = reset_timestamp
        self.retry_after = retry_after
        self.remaining = remaining


class ExponentialBackoff:
    """Exponential backoff with jitter for rate limit handling.

    Calculates delay using formula:
        delay = min(base * (2 ** attempt) + random.uniform(0, 1), max_delay)

    Attributes:
        base: Initial delay in seconds (default 1.0).
        max_delay: Maximum delay cap in seconds (default 300.0).
    """

    def __init__(self, base: float = 1.0, max_delay: float = 300.0):
        self.base = base
        self.max_delay = max_delay
        self._attempt = 0

    def delay(self) -> float:
        """Calculate and return the next delay in seconds.

        Returns:
            Seconds to sleep. Always at least base + jitter.
        """
        delay = min(self.base * (2 ** self._attempt) + random.uniform(0, 1), self.max_delay)
        self._attempt += 1
        return delay

    def reset(self) -> None:
        """Reset the attempt counter."""
        self._attempt = 0

    @property
    def attempt(self) -> int:
        """Current attempt number (0-indexed)."""
        return self._attempt
