"""X profile page scraper using curl_cffi for TLS impersonation.

Provides:
- XProfileScraper: curl_cffi-based scraper with retry logic and block detection
- BlockDetectedError: raised when scraping is blocked
- ScrapeError: raised after max retries exhausted

Usage:
    from src.scrape.scraper import XProfileScraper

    scraper = XProfileScraper(cache_dir=Path("data/enrichment"))
    result = scraper.scrape_profile("elonmusk")
"""

from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path
from typing import Any

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None  # type: ignore

from src.enrich.rate_limiter import ExponentialBackoff

logger = logging.getLogger(__name__)


class BlockDetectedError(Exception):
    """Raised when scraping is blocked (429, empty body, captcha redirect)."""
    pass


class ScrapeError(Exception):
    """Raised after max retry attempts are exhausted."""
    pass


class XProfileScraper:
    """X profile page scraper with TLS impersonation and graceful block handling.

    Attributes:
        cache_dir: Directory containing per-account JSON cache files from Phase 2.
        min_delay: Minimum seconds between requests (default 2.0).
        max_delay: Maximum seconds between requests (default 5.0).
        max_attempts: Maximum retry attempts per profile (default 3).
        crawl_delay: Minimum crawl delay from robots.txt (default 1.0).

    Uses curl_cffi for JA3/TLS fingerprint impersonation to avoid
    anti-bot blocks. Falls back to None on block (graceful degradation)
    rather than raising, per SCRAPE-05.
    """

    def __init__(
        self,
        cache_dir: Path | str,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        max_attempts: int = 3,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_attempts = max_attempts
        self.crawl_delay = 1.0  # default; updated after robots.txt parse

        # Parse robots.txt for crawl delay
        self._parse_robots_txt()

        # Create curl_cffi session with browser impersonation
        if curl_requests is None:
            raise ImportError(
                "curl_cffi is required for scraping. Install with: pip install curl_cffi"
            )
        self._session = curl_requests.Session(impersonate="chrome")

        # Backoff for 429 handling (reuses Phase 2 ExponentialBackoff)
        self._backoff = ExponentialBackoff(base=2.0, max_delay=300.0)

        # Track last block status for scrape_all orchestrator
        self._last_blocked = False

    def _parse_robots_txt(self) -> None:
        """Fetch and parse robots.txt to extract crawl-delay.

        Honors Crawl-delay directive as minimum floor. Per D-02: ignore
        per-path disallows for public user profiles.
        """
        try:
            from urllib.robotparser import RobotFileParser
            rp = RobotFileParser()
            rp.set_url("https://x.com/robots.txt")
            rp.read()
            delay = rp.crawl_delay("*")
            if delay is not None:
                self.crawl_delay = float(delay)
                logger.debug("robots.txt crawl-delay: %.1f", self.crawl_delay)
            else:
                logger.debug("No crawl-delay in robots.txt, using default 1.0")
        except Exception as e:
            logger.warning("Could not parse robots.txt: %s. Using default crawl-delay 1.0.", e)

    def is_blocked(self, response: Any) -> bool:
        """Detect if a response indicates a block or anti-bot challenge.

        Returns True if:
        - HTTP status is 429 (rate limited)
        - HTTP status is 200 but body is empty
        - Redirect URL contains "challenges" (captcha/challenge page)
        - HTTP status is 200 but no <title> tag in response

        Args:
            response: curl_cffi Response object.

        Returns:
            True if blocked, False otherwise.
        """
        # Explicit rate limit
        if response.status_code == 429:
            return True

        # Empty body after 200
        if response.status_code == 200 and not response.text.strip():
            return True

        # Captcha or challenge redirect
        if hasattr(response, "url") and response.url:
            if "challenges" in response.url:
                return True

        # Missing expected HTML structure
        if response.status_code == 200 and "<title>" not in response.text:
            return True

        return False

    def _apply_delay(self) -> None:
        """Sleep a random delay between min_delay and max_delay with jitter.

        Also honors robots.txt crawl_delay as a minimum floor.
        """
        base = random.uniform(self.min_delay, self.max_delay)
        jitter = random.uniform(0, 0.5)
        delay = max(self.crawl_delay, base) + jitter
        time.sleep(delay)

    def _cache_scraped_fields(self, username: str, scraped: dict[str, Any]) -> None:
        """Merge scraped fields into the existing cache file.

        Reads the existing cache file (or creates minimal dict if not exists),
        updates with scraped fields, writes back to same file.

        Args:
            username: Account username (used for cache key).
            scraped: Dict of scraped fields to merge in.
        """
        cache_path = self.cache_dir / f"{username}.json"

        # Read existing cache or start fresh
        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cached = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Could not read cache for %s: %s. Creating new.", username, e)
                cached = {}
        else:
            cached = {}

        # Merge scraped fields
        cached.update(scraped)

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cached, f, indent=2)
        except OSError as e:
            logger.warning("Could not write cache for %s: %s", username, e)

    def scrape_profile(self, username: str) -> dict[str, Any] | None:
        """Scrape supplemental profile fields for a single account.

        Attempts up to max_attempts times with exponential backoff on 429s.
        Returns None on block or failure (graceful degradation per SCRAPE-05).

        Args:
            username: X account username (without @).

        Returns:
            Dict of scraped fields if successful, None if blocked or failed.
        """
        from src.scrape.parser import parse_profile_fields

        url = f"https://x.com/{username}"
        self._last_blocked = False

        for attempt in range(self.max_attempts):
            try:
                response = self._session.get(url, timeout=15)

                # Handle 429 with backoff
                if response.status_code == 429:
                    delay = self._backoff.delay()
                    logger.warning(
                        "Rate limited for %s (attempt %d/%d), waiting %.1fs",
                        username,
                        attempt + 1,
                        self.max_attempts,
                        delay,
                    )
                    time.sleep(delay)
                    self._backoff._attempt += 1
                    continue

                # Non-200 status
                if response.status_code != 200:
                    logger.warning(
                        "HTTP %d for %s (attempt %d/%d)",
                        response.status_code,
                        username,
                        attempt + 1,
                        self.max_attempts,
                    )
                    return None

                # Block detection
                if self.is_blocked(response):
                    logger.warning("Block detected for %s", username)
                    self._last_blocked = True
                    return None

                # Parse fields
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "lxml")
                scraped = parse_profile_fields(soup)

                # Cache results
                self._cache_scraped_fields(username, scraped)

                logger.debug("Scraped %s successfully", username)
                return scraped

            except Exception as e:
                logger.warning(
                    "Exception scraping %s (attempt %d/%d): %s",
                    username,
                    attempt + 1,
                    self.max_attempts,
                    e,
                )
                if attempt == self.max_attempts - 1:
                    return None

        # Exhausted retries
        logger.error("Exhausted %d attempts for %s", self.max_attempts, username)
        return None
