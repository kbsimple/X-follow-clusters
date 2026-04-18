"""Populate recent_tweets_text from cached tweets (no API calls).

Reads from data/tweets.db and updates data/enrichment/*.json files.
Use this to run clustering using ONLY cached data.

Usage:
    .venv/bin/python -m src.enrich.populate_tweets
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.enrich.tweet_cache import TweetCache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Populate recent_tweets_text from TweetCache for all enriched accounts."""
    cache_dir = Path("data/enrichment")
    tweet_cache = TweetCache()

    if not cache_dir.exists():
        logger.error("No enrichment cache found at %s", cache_dir)
        logger.info("Run enrichment first: .venv/bin/python -m src.enrich.test_enrich")
        return 1

    json_files = list(cache_dir.glob("*.json"))
    if not json_files:
        logger.error("No account JSON files found in %s", cache_dir)
        return 1

    updated_count = 0
    skipped_count = 0

    for json_file in json_files:
        if json_file.stem in ("suspended", "protected", "errors"):
            continue

        try:
            with open(json_file, encoding="utf-8") as f:
                account = json.load(f)

            user_id = account.get("id")
            if not user_id:
                skipped_count += 1
                continue

            # Load cached tweets
            result = tweet_cache.load_tweets(user_id)

            if result.count == 0:
                skipped_count += 1
                continue

            # Build recent_tweets_text from cached tweets
            tweet_texts = []
            for tweet in result.tweets[:50]:  # Max 50 tweets
                text = tweet.get("text", "")
                if text:
                    tweet_texts.append(text)

            account["recent_tweets"] = result.tweets[:50]
            account["recent_tweets_text"] = " ".join(tweet_texts)

            # Write back to JSON
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(account, f, indent=2)

            updated_count += 1
            logger.info("Updated %s: %d tweets", json_file.stem, result.count)

        except Exception as e:
            logger.warning("Error processing %s: %s", json_file, e)
            skipped_count += 1

    print(f"\n{'='*50}")
    print(f"Populated recent_tweets_text from cache")
    print(f"  Updated: {updated_count} accounts")
    print(f"  Skipped: {skipped_count} accounts (no cached tweets)")
    print(f"{'='*50}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())