"""CLI entry point for profile scraping.

Usage:
    python -m src.scrape --input data/enrichment --output data/enrichment

    # Or via Python API:
    from src.scrape import scrape_all
    result = scrape_all(cache_dir="data/enrichment")
"""

from __future__ import annotations

import argparse
import sys
import logging
from pathlib import Path

from src.scrape import scrape_all
from src.scrape.link_follower import LinkFollowResult
from src.scrape.entities import EntityResult
from src.scrape.google_lookup import GoogleLookupResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main() -> int:
    """CLI entry point for profile scraping."""
    parser = argparse.ArgumentParser(
        description="Scrape supplemental profile fields for accounts flagged needs_scraping"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/enrichment"),
        help="Enrichment cache directory (default: data/enrichment)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/enrichment"),
        help="Output directory (same as input for scraping, default: data/enrichment)",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=2.0,
        help="Minimum delay between requests in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=5.0,
        help="Maximum delay between requests in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--3scrape",
        action="store_true",
        help="Run Phase 8 3scrape pipeline: link following, entity extraction, Google search",
    )
    args = parser.parse_args()

    try:
        if args.3scrape:
            result = scrape_all(
                cache_dir=args.input,
                min_delay=args.min_delay,
                max_delay=args.max_delay,
                mode="3scrape",
            )
            print(
                f"3scrape complete: {result.total} total, "
                f"{result.link_followed} link_followed, "
                f"{result.entities_extracted} entities_extracted, "
                f"{result.google_looked_up} google_looked_up"
            )
        else:
            result = scrape_all(
                cache_dir=args.input,
                min_delay=args.min_delay,
                max_delay=args.max_delay,
            )
            print(
                f"Scraping complete: {result.scraped}/{result.total} scraped, "
                f"{result.skipped} skipped (no scraping needed), "
                f"{result.failed} failed, {result.blocked} blocked"
            )
        return 0
    except Exception as e:
        logging.error("Scraping failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
