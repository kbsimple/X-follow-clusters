"""Main enrichment orchestration: batch process all following accounts.

Reads following.js, enriches each account via X API in batches of 100,
caches immediately, tracks suspended/protected accounts, and flags
accounts missing bio/location for Phase 3 scraping.

Usage:
    python -m src.enrich.enrich --input data/following.js --output data/enrichment

    # Or via Python API:
    from src.enrich import enrich_all, EnrichmentResult
    result = enrich_all(
        following_path="data/following.js",
        cache_dir=Path("data/enrichment"),
    )
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.auth import ensure_authenticated, verify_credentials, XAuth
from src.enrich.api_client import XEnrichmentClient
from src.enrich.rate_limiter import ExponentialBackoff, RateLimitError
from src.parse import parse_following_js, FollowingRecord

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class EnrichmentResult:
    """Result of an enrichment run.

    Attributes:
        total: Total accounts parsed from following.js.
        enriched: Successfully enriched accounts.
        suspended: Suspended accounts detected (error code 63).
        protected: Protected accounts detected (error code 179).
        errors: Accounts that failed with other errors.
        cache_dir: Directory containing cached enrichment files.
    """

    total: int
    enriched: int
    suspended: int
    protected: int
    errors: int
    cache_dir: Path

    # Detailed tracking lists
    suspended_ids: list[str] = field(default_factory=list)
    protected_ids: list[str] = field(default_factory=list)
    error_details: list[dict[str, Any]] = field(default_factory=list)


def _chunked(lst: list, size: int) -> list[list]:
    """Split a list into chunks of at most `size` elements."""
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def enrich_all(
    following_path: str | Path = Path("data/following.js"),
    cache_dir: str | Path = Path("data/enrichment"),
) -> EnrichmentResult:
    """Enrich all accounts from following.js.

    Args:
        following_path: Path to the following.js file.
        cache_dir: Directory for cached enrichment JSON files.

    Returns:
        EnrichmentResult with counts and tracking lists.

    Raises:
        AuthError: If credentials are missing or invalid.
        ParseError: If following.js cannot be parsed.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load credentials and verify
    logger.info("Loading credentials...")
    auth = ensure_authenticated()
    logger.info("Verifying credentials with GET /2/users/me...")
    verify_credentials(auth)
    logger.info("Credentials verified.")

    # 2. Parse following.js
    logger.info("Parsing %s...", following_path)
    records = parse_following_js(following_path)
    logger.info("Parsed %d accounts from following.js", len(records))
    total = len(records)

    # 3. Set up client with custom backoff
    backoff = ExponentialBackoff(base=1.0, max_delay=300.0)
    client = XEnrichmentClient(auth, cache_dir=cache_dir, backoff=backoff)

    # 4. Process in batches of 100
    BATCH_SIZE = 100
    enriched = 0
    suspended = 0
    protected = 0
    errors = 0
    suspended_ids: list[str] = []
    protected_ids: list[str] = []
    error_details: list[dict[str, Any]] = []

    batches = _chunked(records, BATCH_SIZE)
    logger.info("Processing %d accounts in %d batches...", total, len(batches))

    for batch_idx, batch in enumerate(batches, 1):
        ids = [r.account_id for r in batch]
        logger.info(
            "Batch %d/%d: fetching %d accounts...",
            batch_idx,
            len(batches),
            len(ids),
        )

        try:
            response = client.get_users(ids)

            # Process errors for suspended (63) and protected (179) accounts
            for err in response.errors:
                code = err.get("code")
                value = err.get("value") or err.get("resource_id", "unknown")
                if code == 63:
                    suspended += 1
                    suspended_ids.append(value)
                    _write_special_cache(cache_dir, "suspended", suspended_ids)
                elif code == 179:
                    protected += 1
                    protected_ids.append(value)
                    _write_special_cache(cache_dir, "protected", protected_ids)
                else:
                    errors += 1
                    error_details.append({"id": value, "code": code, "error": err})
                    _write_special_cache(cache_dir, "errors", error_details)

            batch_enriched = len(response.data)
            enriched += batch_enriched
            logger.info(
                "Batch %d/%d: enriched %d accounts (total: %d)",
                batch_idx,
                len(batches),
                batch_enriched,
                enriched,
            )

        except RateLimitError as e:
            logger.warning(
                "Rate limit hit on batch %d: reset at %d, retry after %.1fs",
                batch_idx,
                e.reset_timestamp,
                e.retry_after,
            )
            # Retry this batch after sleeping
            import time
            time.sleep(e.retry_after)
            backoff.reset()
            # Re-fetch the same batch
            try:
                response = client.get_users(ids)
                batch_enriched = len(response.data)
                enriched += batch_enriched
                # Re-process errors
                for err in response.errors:
                    code = err.get("code")
                    value = err.get("value") or err.get("resource_id", "unknown")
                    if code == 63:
                        suspended += 1
                        suspended_ids.append(value)
                        _write_special_cache(cache_dir, "suspended", suspended_ids)
                    elif code == 179:
                        protected += 1
                        protected_ids.append(value)
                        _write_special_cache(cache_dir, "protected", protected_ids)
                    else:
                        errors += 1
                        error_details.append({"id": value, "code": code, "error": err})
                        _write_special_cache(cache_dir, "errors", error_details)
            except Exception as e2:
                logger.error("Retry failed for batch %d: %s", batch_idx, e2)
                errors += len(ids)
                error_details.append({"batch": batch_idx, "error": str(e2)})
                _write_special_cache(cache_dir, "errors", error_details)

        except Exception as e:
            logger.error("Batch %d/%d failed: %s", batch_idx, len(batches), e)
            errors += len(ids)
            error_details.append({"batch": batch_idx, "error": str(e)})
            _write_special_cache(cache_dir, "errors", error_details)

    result = EnrichmentResult(
        total=total,
        enriched=enriched,
        suspended=suspended,
        protected=protected,
        errors=errors,
        cache_dir=cache_dir,
        suspended_ids=suspended_ids,
        protected_ids=protected_ids,
        error_details=error_details,
    )

    logger.info(
        "Enrichment complete: %d/%d enriched, %d suspended, %d protected, %d errors",
        enriched,
        total,
        suspended,
        protected,
        errors,
    )

    return result


def _write_special_cache(cache_dir: Path, name: str, data: Any) -> None:
    """Write a special tracking JSON file (suspended, protected, errors)."""
    path = cache_dir / f"{name}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Enrich following accounts via X API")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/following.js"),
        help="Path to following.js (default: data/following.js)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/enrichment"),
        help="Path to cache directory (default: data/enrichment)",
    )
    args = parser.parse_args()

    try:
        result = enrich_all(following_path=args.input, cache_dir=args.output)
        print(
            f"Enrichment complete: {result.enriched}/{result.total} enriched, "
            f"{result.suspended} suspended, {result.protected} protected, "
            f"{result.errors} errors"
        )
        return 0
    except Exception as e:
        logger.error("Enrichment failed: %s", e)
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
