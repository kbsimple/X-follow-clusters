"""Tests for TweetCache class with SQLite storage.

These tests verify:
1. TweetCache() creates database file at specified path with proper schema
2. TweetCache() creates table with tweet_id TEXT PRIMARY KEY column
3. TweetCache() creates index on user_id column
4. load_tweets(user_id) returns empty list for user with no cached tweets
5. load_tweets(user_id) returns tweets ordered by created_at DESC
6. persist_tweets(user_id, tweets) inserts tweets and returns count
7. persist_tweets with duplicate tweet_id does not raise error (INSERT OR IGNORE)
8. persist_tweets returns 0 when all tweets are duplicates
9. TweetCache handles tweets with missing optional fields
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from src.enrich.tweet_cache import TweetCache, TweetCacheResult


# Sample tweet matching data/enrichment/1000591.json structure
SAMPLE_TWEET: dict[str, Any] = {
    "id": "1792972284669407635",
    "text": "/fin",
    "created_at": "2024-05-21T17:34:39.000Z",
    "public_metrics": {
        "like_count": 49,
        "retweet_count": 5,
        "reply_count": 10,
    },
}

SAMPLE_TWEET_2: dict[str, Any] = {
    "id": "1792972282605801983",
    "text": "I wrote a post about moving my Internet presence onchain",
    "created_at": "2024-05-21T17:34:38.000Z",
    "public_metrics": {
        "like_count": 90,
        "retweet_count": 10,
        "reply_count": 22,
    },
}


class TestTweetCacheInit:
    """Test TweetCache initialization and schema creation."""

    def test_init_creates_database_file(self, temp_tweet_cache: TweetCache) -> None:
        """Test that TweetCache instantiation creates database file."""
        db_path = temp_tweet_cache.db_path
        assert db_path.exists()
        assert db_path.is_file()

    def test_init_creates_schema_with_text_tweet_id(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test that tweet_id column is TEXT type (critical for 64-bit snowflake IDs)."""
        conn = sqlite3.connect(temp_tweet_cache.db_path)
        cursor = conn.cursor()

        # Query table info to get column types
        cursor.execute("PRAGMA table_info(tweets)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        assert "tweet_id" in columns
        assert columns["tweet_id"] == "TEXT"

    def test_init_creates_user_id_index(self, temp_tweet_cache: TweetCache) -> None:
        """Test that index on user_id column exists for efficient queries."""
        conn = sqlite3.connect(temp_tweet_cache.db_path)
        cursor = conn.cursor()

        # Query indexes
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tweets'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "idx_tweets_user" in indexes

    def test_init_creates_created_at_index(self, temp_tweet_cache: TweetCache) -> None:
        """Test that index on created_at column exists for ordering."""
        conn = sqlite3.connect(temp_tweet_cache.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tweets'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "idx_tweets_created" in indexes

    def test_init_sets_wal_mode(self, temp_tweet_cache: TweetCache) -> None:
        """Test that WAL mode is enabled for concurrent reads."""
        conn = sqlite3.connect(temp_tweet_cache.db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()

        assert mode.lower() == "wal"


class TestTweetCacheLoad:
    """Test TweetCache.load_tweets method."""

    def test_load_tweets_returns_empty_result_for_nonexistent_user(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test load_tweets returns empty result for user with no cached tweets."""
        result = temp_tweet_cache.load_tweets("nonexistent_user")

        assert isinstance(result, TweetCacheResult)
        assert result.tweets == []
        assert result.count == 0
        assert result.user_id == "nonexistent_user"

    def test_load_tweets_returns_tweets_ordered_by_created_at_desc(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test load_tweets returns tweets in created_at DESC order."""
        user_id = "test_user_123"

        # Insert tweets out of order (older first, newer second)
        temp_tweet_cache.persist_tweets(user_id, [SAMPLE_TWEET_2, SAMPLE_TWEET])

        result = temp_tweet_cache.load_tweets(user_id)

        assert result.count == 2
        # SAMPLE_TWEET has later timestamp, should be first
        assert result.tweets[0]["tweet_id"] == SAMPLE_TWEET["id"]
        assert result.tweets[1]["tweet_id"] == SAMPLE_TWEET_2["id"]

    def test_load_tweets_returns_only_tweets_for_specified_user(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test load_tweets only returns tweets for the specified user_id."""
        user_1 = "user_1"
        user_2 = "user_2"

        temp_tweet_cache.persist_tweets(user_1, [SAMPLE_TWEET])
        temp_tweet_cache.persist_tweets(user_2, [SAMPLE_TWEET_2])

        result_1 = temp_tweet_cache.load_tweets(user_1)
        result_2 = temp_tweet_cache.load_tweets(user_2)

        assert result_1.count == 1
        assert result_1.tweets[0]["tweet_id"] == SAMPLE_TWEET["id"]

        assert result_2.count == 1
        assert result_2.tweets[0]["tweet_id"] == SAMPLE_TWEET_2["id"]


class TestTweetCachePersist:
    """Test TweetCache.persist_tweets method."""

    def test_persist_tweets_inserts_tweets_and_returns_count(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test persist_tweets inserts tweets and returns correct count."""
        user_id = "test_user_456"

        count = temp_tweet_cache.persist_tweets(user_id, [SAMPLE_TWEET])

        assert count == 1

        result = temp_tweet_cache.load_tweets(user_id)
        assert result.count == 1

    def test_persist_tweets_with_duplicate_ids_does_not_insert_duplicates(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test persist_tweets uses INSERT OR IGNORE for deduplication."""
        user_id = "test_user_789"

        # Insert same tweet twice
        count_1 = temp_tweet_cache.persist_tweets(user_id, [SAMPLE_TWEET])
        count_2 = temp_tweet_cache.persist_tweets(user_id, [SAMPLE_TWEET])

        assert count_1 == 1
        assert count_2 == 0  # Duplicate ignored

        result = temp_tweet_cache.load_tweets(user_id)
        assert result.count == 1  # Still only one tweet

    def test_persist_tweets_extracts_public_metrics_correctly(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test persist_tweets extracts like_count, retweet_count, reply_count."""
        user_id = "metrics_user"

        temp_tweet_cache.persist_tweets(user_id, [SAMPLE_TWEET])

        result = temp_tweet_cache.load_tweets(user_id)
        tweet = result.tweets[0]

        assert tweet["like_count"] == 49
        assert tweet["retweet_count"] == 5
        assert tweet["reply_count"] == 10

    def test_persist_tweets_handles_empty_list_gracefully(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test persist_tweets returns 0 for empty tweet list."""
        user_id = "empty_user"

        count = temp_tweet_cache.persist_tweets(user_id, [])

        assert count == 0

    def test_persist_tweets_handles_missing_public_metrics(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test persist_tweets handles tweets with missing public_metrics."""
        user_id = "missing_metrics_user"

        tweet_no_metrics: dict[str, Any] = {
            "id": "123456789",
            "text": "Hello world",
            "created_at": "2024-01-01T00:00:00.000Z",
            # No public_metrics
        }

        count = temp_tweet_cache.persist_tweets(user_id, [tweet_no_metrics])

        assert count == 1

        result = temp_tweet_cache.load_tweets(user_id)
        tweet = result.tweets[0]

        # Should have default values
        assert tweet["like_count"] == 0
        assert tweet["retweet_count"] == 0
        assert tweet["reply_count"] == 0

    def test_persist_tweets_handles_partial_public_metrics(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test persist_tweets handles tweets with partial public_metrics."""
        user_id = "partial_metrics_user"

        tweet_partial: dict[str, Any] = {
            "id": "987654321",
            "text": "Partial metrics",
            "created_at": "2024-01-02T00:00:00.000Z",
            "public_metrics": {
                "like_count": 100,
                # Missing retweet_count and reply_count
            },
        }

        temp_tweet_cache.persist_tweets(user_id, [tweet_partial])

        result = temp_tweet_cache.load_tweets(user_id)
        tweet = result.tweets[0]

        assert tweet["like_count"] == 100
        assert tweet["retweet_count"] == 0  # Default
        assert tweet["reply_count"] == 0  # Default

    def test_persist_tweets_batch_inserts_multiple_tweets(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test persist_tweets can insert multiple tweets at once."""
        user_id = "batch_user"

        tweets = [SAMPLE_TWEET, SAMPLE_TWEET_2]
        count = temp_tweet_cache.persist_tweets(user_id, tweets)

        assert count == 2

        result = temp_tweet_cache.load_tweets(user_id)
        assert result.count == 2


class TestTweetCacheDeduplication:
    """Test tweet deduplication via PRIMARY KEY constraint."""

    def test_same_tweet_for_different_user_is_still_deduplicated(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test that INSERT OR IGNORE prevents duplicate tweet_ids.

        Note: tweet_id is globally unique on X, so the same tweet_id
        cannot exist for different users. If someone tries to insert
        the same tweet_id for a different user, it's still deduplicated.
        """
        user_1 = "user_a"
        user_2 = "user_b"

        # Insert same tweet_id for user_1, then try for user_2
        count_1 = temp_tweet_cache.persist_tweets(user_1, [SAMPLE_TWEET])
        count_2 = temp_tweet_cache.persist_tweets(user_2, [SAMPLE_TWEET])

        # First insert succeeds, second is deduplicated (0 rows)
        assert count_1 == 1
        assert count_2 == 0  # Deduplicated via INSERT OR IGNORE

        # Only user_1 has the tweet
        result_1 = temp_tweet_cache.load_tweets(user_1)
        result_2 = temp_tweet_cache.load_tweets(user_2)

        assert result_1.count == 1
        assert result_2.count == 0

    def test_tweet_id_as_text_preserves_large_ids(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test that large tweet IDs are stored correctly as TEXT."""
        user_id = "large_id_user"

        # X snowflake IDs are 64-bit (larger than JavaScript safe integer)
        large_id = "17929722846694076351"  # 20 digits, clearly > 2^53

        large_tweet: dict[str, Any] = {
            "id": large_id,
            "text": "Large ID tweet",
            "created_at": "2024-01-03T00:00:00.000Z",
            "public_metrics": {"like_count": 1},
        }

        temp_tweet_cache.persist_tweets(user_id, [large_tweet])

        result = temp_tweet_cache.load_tweets(user_id)
        assert result.tweets[0]["tweet_id"] == large_id


class TestTweetCacheWatermark:
    """Test TweetCache.get_newest_tweet_id method for watermark tracking."""

    def test_get_newest_tweet_id_returns_none_for_empty_cache(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_newest_tweet_id returns None for user with no cached tweets."""
        result = temp_tweet_cache.get_newest_tweet_id("unknown_user")

        assert result is None

    def test_get_newest_tweet_id_returns_id_for_single_tweet(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_newest_tweet_id returns correct ID for single cached tweet."""
        user_id = "single_tweet_user"
        temp_tweet_cache.persist_tweets(user_id, [SAMPLE_TWEET])

        result = temp_tweet_cache.get_newest_tweet_id(user_id)

        assert result == SAMPLE_TWEET["id"]

    def test_get_newest_tweet_id_returns_newest_for_multiple_tweets(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_newest_tweet_id returns newest ID when multiple tweets exist."""
        user_id = "multi_tweet_user"
        # SAMPLE_TWEET has created_at "2024-05-21T17:34:39.000Z" (newer)
        # SAMPLE_TWEET_2 has created_at "2024-05-21T17:34:38.000Z" (older)
        temp_tweet_cache.persist_tweets(user_id, [SAMPLE_TWEET, SAMPLE_TWEET_2])

        result = temp_tweet_cache.get_newest_tweet_id(user_id)

        # Should return the newest (SAMPLE_TWEET has later timestamp)
        assert result == SAMPLE_TWEET["id"]

    def test_get_newest_tweet_id_returns_newest_when_inserted_out_of_order(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_newest_tweet_id returns newest even when tweets inserted out of order."""
        user_id = "out_of_order_user"
        # Insert older tweet first, newer tweet second
        temp_tweet_cache.persist_tweets(user_id, [SAMPLE_TWEET_2])
        temp_tweet_cache.persist_tweets(user_id, [SAMPLE_TWEET])

        result = temp_tweet_cache.get_newest_tweet_id(user_id)

        # Should still return the newest (SAMPLE_TWEET) regardless of insert order
        assert result == SAMPLE_TWEET["id"]