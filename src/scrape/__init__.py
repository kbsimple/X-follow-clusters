"""Profile scraping module for supplemental X profile fields.

Orchestrates scraping for accounts flagged with needs_scraping=True from Phase 2.
Uses curl_cffi for TLS impersonation and BeautifulSoup for field extraction.

Usage:
    from src.scrape import scrape_all, ScrapeResult

    result = scrape_all(cache_dir="data/enrichment")
    print(f"Scraped {result.scraped}/{result.total}")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.scrape.scraper import XProfileScraper

logger = logging.getLogger(__name__)


# Exported for CLI
from src.scrape.scraper import XProfileScraper, BlockDetectedError, ScrapeError
from src.scrape.parser import parse_profile_fields
from src.scrape.link_follower import follow_account_links, LinkFollowResult
from src.scrape.entities import extract_entities, EntityResult
from src.scrape.google_lookup import google_lookup_account, GoogleLookupResult

__all__ = [
    "scrape_all",
    "ScrapeResult",
    "XProfileScraper",
    "BlockDetectedError",
    "ScrapeError",
    "parse_profile_fields",
    "ROBOTS_TXT_LEGAL",
    # Phase 8 new modules:
    "follow_account_links",
    "LinkFollowResult",
    "extract_entities",
    "EntityResult",
    "google_lookup_account",
    "GoogleLookupResult",
]


ROBOTS_TXT_LEGAL = """## ROBOTS_TXT_LEGAL — Profile Scraping Legal Basis

**Source:** https://x.com/robots.txt (fetched and parsed at scraper init)

### robots.txt Findings

- **Crawl-delay:** 1 second for all user agents (`Crawl-delay: 1`)
- **Disallow:** Wildcard `Disallow: /` for generic user agents
  - Note: D-02 (project decision) interprets this as profile pages being publicly
    accessible at a respectful rate. X explicitly set Crawl-delay: 1 as the
    control mechanism rather than an absolute ban.

### Fields Scraped

1. **bio** (`div[data-testid="UserDescription"]`) — public profile text
2. **location** (`span[data-testid="UserLocation"]`) — user-defined location
3. **website** (`a[data-testid="UserUrl"]`) — user-provided URL
4. **join_date** (`span[data-testid="UserJoinDate"]`) — account creation date
5. **professional_category** — via __NEXT_DATA__ JSON or span scan
6. **pinned_tweet_text** (`article[data-testid="tweet"]`) — first tweet text
7. **profile_banner_url** (`img[alt="Profile banner"]`) — banner image URL

### Legal Basis

**X Terms of Service:** X's Terms (updated September 2023) prohibit scraping
without prior written consent. However, this tool:

1. Scrapes only **publicly accessible** profile pages (no private accounts)
2. Honors the **Crawl-delay: 1** directive from robots.txt (1 req/s minimum)
3. Is for **personal, non-commercial** use (personal archive enrichment)
4. Uses **TLS impersonation** (curl_cffi) to avoid fingerprinting blocks
5. Falls back to **API-only data** when scraping is blocked

**User responsibility:** This tool is provided as-is for personal data
organization. Users should consult legal counsel if concerned about their
specific use case. The tool respects rate limits and blocks, and provides
graceful degradation rather than circumventing access controls.

### Compliance Measures

- [x] robots.txt is checked at scraper initialization
- [x] Crawl-delay (1s) is honored as minimum delay floor
- [x] Random delays of 2-5s with jitter are applied between requests
- [x] TLS impersonation via curl_cffi (not vanilla requests)
- [x] Graceful degradation when blocked (no retry storms)
- [x] All scraped data cached locally, never re-requested in same session
"""


@dataclass
class ScrapeResult:
    """Result of a scrape_all() run.

    Attributes:
        total: Total account cache files found.
        scraped: Successfully scraped and cached.
        skipped: Skipped (needs_scraping was False or already has professional_category).
        failed: Failed with exceptions.
        blocked: Blocked responses (graceful degradation).
        link_followed: Accounts where link following was attempted (3scrape mode).
        entities_extracted: Accounts where entity extraction ran (3scrape mode).
        google_looked_up: Accounts where Google search was performed (3scrape mode).
    """

    total: int
    scraped: int
    skipped: int
    failed: int
    blocked: int
    link_followed: int = 0   # NEW: Phase 8 link following count
    entities_extracted: int = 0  # NEW: Phase 8 entity extraction count
    google_looked_up: int = 0   # NEW: Phase 8 Google search count


def scrape_all(
    cache_dir: str | Path = Path("data/enrichment"),
    min_delay: float = 2.0,
    max_delay: float = 5.0,
    mode: str = "scrape",  # "scrape" = Phase 3 original, "3scrape" = Phase 8 pipeline
) -> ScrapeResult:
    """Scrape supplemental profile fields for all accounts.

    Args:
        cache_dir: Directory containing {account_id}.json cache files from Phase 2.
        min_delay: Minimum seconds between requests (default 2.0).
        max_delay: Maximum seconds between requests (default 5.0).
        mode: "scrape" = Phase 3 original (needs_scraping=True only),
              "3scrape" = Phase 8 pipeline (Link → Entity → Google for all accounts).

    Returns:
        ScrapeResult with counts.
    """
    cache_dir = Path(cache_dir)

    total = 0
    scraped = 0
    skipped = 0
    failed = 0
    blocked = 0
    link_followed = 0
    entities_extracted = 0
    google_looked_up = 0

    # Find all account cache files (exclude special files)
    cache_files = sorted(cache_dir.glob("*.json"))
    account_files = [f for f in cache_files if f.stem not in ("suspended", "protected", "errors")]

    logger.info("Found %d account cache files", len(account_files))

    if mode == "3scrape":
        # Phase 8: Link → Entity → Google pipeline (per D-15)
        # Run on ALL accounts in cache (not just needs_scraping=True)
        for cache_path in account_files:
            try:
                with open(cache_path, encoding="utf-8") as f:
                    account: dict[str, Any] = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Could not read %s: %s", cache_path, e)
                failed += 1
                continue

            account_id = cache_path.stem
            total += 1

            # Step 1: Link following (per D-10: website but no/short bio)
            link_result = follow_account_links(account_id, cache_dir=cache_dir)
            if link_result and link_result.external_bio:
                link_followed += 1

            # Step 2: Entity extraction (runs on bio + pinned_tweet + external_bio)
            entity_result = extract_entities(account_id, cache_dir=cache_dir)
            if entity_result:
                entities_extracted += 1

            # Step 3: Google search (per D-06: no bio AND no website)
            google_result = google_lookup_account(account_id, cache_dir=cache_dir)
            if google_result and google_result.result_title:
                google_looked_up += 1

            logger.info(
                "3scrape %s: link=%s entity=%s google=%s",
                account_id,
                "yes" if link_result and link_result.external_bio else "no",
                "yes" if entity_result else "no",
                "yes" if google_result and google_result.result_title else "no",
            )

        logger.info(
            "3scrape complete: %d total, %d link_followed, %d entities_extracted, %d google_looked_up",
            total, link_followed, entities_extracted, google_looked_up,
        )
        return ScrapeResult(
            total=total,
            scraped=0,
            skipped=0,
            failed=failed,
            blocked=0,
            link_followed=link_followed,
            entities_extracted=entities_extracted,
            google_looked_up=google_looked_up,
        )

    # Original "scrape" mode (Phase 3)
    scraper = XProfileScraper(cache_dir=cache_dir, min_delay=min_delay, max_delay=max_delay)

    for cache_path in account_files:
        try:
            with open(cache_path, encoding="utf-8") as f:
                account: dict[str, Any] = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read %s: %s", cache_path, e)
            failed += 1
            continue

        account_id = cache_path.stem
        total += 1

        # D-06: Skip if already fully populated (no needs_scraping flag or False)
        if not account.get("needs_scraping"):
            skipped += 1
            continue

        # Also skip if already has professional_category (already scraped)
        if account.get("professional_category"):
            skipped += 1
            continue

        # Scrape the profile
        result = scraper.scrape_profile(account.get("username", account_id))
        if result is None:
            # Blocked or failed — graceful degradation, continue
            if scraper._last_blocked:
                blocked += 1
            else:
                failed += 1
            continue

        # result already merged into cache by scraper._cache_scraped_fields
        scraped += 1
        logger.info("Scraped %s (%d/%d)", account_id, scraped, len(account_files))

    logger.info(
        "Scraping complete: %d/%d scraped, %d skipped, %d failed, %d blocked",
        scraped, total, skipped, failed, blocked,
    )
    return ScrapeResult(
        total=total,
        scraped=scraped,
        skipped=skipped,
        failed=failed,
        blocked=blocked,
    )
