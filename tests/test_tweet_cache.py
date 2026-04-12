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
from unittest.mock import MagicMock, patch

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


class TestIncrementalFetch:
    """Test XEnrichmentClient.get_recent_tweets with cache-first logic."""

    def test_cache_hit_returns_cached_without_api_call(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_recent_tweets returns cached tweets without API call when cache is full."""
        from src.enrich.api_client import XEnrichmentClient

        user_id = "cache_hit_user"
        # Pre-populate cache with 60 tweets (more than max_tweets=50)
        tweets = []
        for i in range(60):
            tweets.append({
                "id": f"tweet_{i}",
                "text": f"Tweet {i}",
                "created_at": f"2024-05-21T17:34:{i % 60:02d}.000Z",
                "public_metrics": {"like_count": i},
            })
        temp_tweet_cache.persist_tweets(user_id, tweets)

        # Mock the API client
        mock_client = MagicMock(spec=XEnrichmentClient)
        mock_client._fetch_tweets_from_api = MagicMock(return_value=[])

        # Since we need to test the actual method, we'll patch _fetch_tweets_from_api
        with patch.object(XEnrichmentClient, '_fetch_tweets_from_api') as mock_fetch:
            # Create a real client instance
            auth = MagicMock()
            auth.access_token = "test_token"
            client = XEnrichmentClient(auth=auth)

            result = client.get_recent_tweets(user_id, max_tweets=50, tweet_cache=temp_tweet_cache)

            # Verify no API call was made
            mock_fetch.assert_not_called()
            # Verify cached tweets returned
            assert len(result) == 50

    def test_cache_miss_fetches_new_tweets_with_since_id(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_recent_tweets fetches from API when cache is empty."""
        from src.enrich.api_client import XEnrichmentClient

        user_id = "cache_miss_user"
        # Empty cache - no tweets for this user

        new_tweets = [
            {
                "id": "new_tweet_1",
                "text": "New tweet 1",
                "created_at": "2024-05-22T10:00:00.000Z",
                "public_metrics": {"like_count": 1},
            },
            {
                "id": "new_tweet_2",
                "text": "New tweet 2",
                "created_at": "2024-05-22T10:01:00.000Z",
                "public_metrics": {"like_count": 2},
            },
        ]

        with patch.object(XEnrichmentClient, '_fetch_tweets_from_api') as mock_fetch:
            mock_fetch.return_value = new_tweets

            auth = MagicMock()
            auth.access_token = "test_token"
            client = XEnrichmentClient(auth=auth)

            result = client.get_recent_tweets(user_id, max_tweets=50, tweet_cache=temp_tweet_cache)

            # Verify API was called with since_id=None (no cached tweets)
            mock_fetch.assert_called_once_with(user_id, 50, since_id=None)
            # Verify new tweets persisted
            cached = temp_tweet_cache.load_tweets(user_id)
            assert cached.count == 2
            # Verify tweets returned
            assert len(result) == 2

    def test_partial_cache_uses_since_id_for_new_tweets(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_recent_tweets uses since_id when cache has partial tweets."""
        from src.enrich.api_client import XEnrichmentClient

        user_id = "partial_cache_user"
        # Pre-populate cache with 30 tweets
        cached_tweets = []
        for i in range(30):
            cached_tweets.append({
                "id": f"cached_tweet_{i}",
                "text": f"Cached tweet {i}",
                "created_at": f"2024-05-21T17:34:{i % 60:02d}.000Z",
                "public_metrics": {"like_count": i},
            })
        temp_tweet_cache.persist_tweets(user_id, cached_tweets)

        # Get the newest tweet ID from cache (watermark)
        newest_id = temp_tweet_cache.get_newest_tweet_id(user_id)

        new_tweets = [
            {
                "id": "new_tweet_partial_1",
                "text": "New tweet partial 1",
                "created_at": "2024-05-22T10:00:00.000Z",
                "public_metrics": {"like_count": 100},
            },
        ]

        with patch.object(XEnrichmentClient, '_fetch_tweets_from_api') as mock_fetch:
            mock_fetch.return_value = new_tweets

            auth = MagicMock()
            auth.access_token = "test_token"
            client = XEnrichmentClient(auth=auth)

            result = client.get_recent_tweets(user_id, max_tweets=50, tweet_cache=temp_tweet_cache)

            # Verify API was called with since_id=watermark (20 tweets needed)
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args
            assert call_args[0][0] == user_id
            assert call_args[0][1] == 20  # 50 - 30 = 20 needed
            assert call_args[1].get('since_id') == newest_id

    def test_merged_result_new_first_then_cached(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_recent_tweets returns new tweets first, then cached."""
        from src.enrich.api_client import XEnrichmentClient

        user_id = "merge_user"
        # Pre-populate cache with older tweets
        cached_tweets = [{
            "id": "cached_old",
            "text": "Cached old tweet",
            "created_at": "2024-05-20T10:00:00.000Z",
            "public_metrics": {"like_count": 5},
        }]
        temp_tweet_cache.persist_tweets(user_id, cached_tweets)

        # New tweets (fetched from API) - more recent
        new_tweets = [{
            "id": "new_recent",
            "text": "New recent tweet",
            "created_at": "2024-05-22T10:00:00.000Z",
            "public_metrics": {"like_count": 10},
        }]

        with patch.object(XEnrichmentClient, '_fetch_tweets_from_api') as mock_fetch:
            mock_fetch.return_value = new_tweets

            auth = MagicMock()
            auth.access_token = "test_token"
            client = XEnrichmentClient(auth=auth)

            result = client.get_recent_tweets(user_id, max_tweets=50, tweet_cache=temp_tweet_cache)

            # Verify new tweets come first
            assert result[0]["id"] == "new_recent"
            # Cached tweets have 'tweet_id' key from database schema
            assert result[1]["tweet_id"] == "cached_old"

    def test_empty_api_response_returns_cached_gracefully(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_recent_tweets returns cached tweets when API returns empty."""
        from src.enrich.api_client import XEnrichmentClient

        user_id = "empty_api_user"
        # Pre-populate cache with tweets
        cached_tweets = [{
            "id": "cached_tweet",
            "text": "Cached tweet",
            "created_at": "2024-05-21T10:00:00.000Z",
            "public_metrics": {"like_count": 5},
        }]
        temp_tweet_cache.persist_tweets(user_id, cached_tweets)

        # API returns empty list (no new tweets)
        with patch.object(XEnrichmentClient, '_fetch_tweets_from_api') as mock_fetch:
            mock_fetch.return_value = []

            auth = MagicMock()
            auth.access_token = "test_token"
            client = XEnrichmentClient(auth=auth)

            result = client.get_recent_tweets(user_id, max_tweets=50, tweet_cache=temp_tweet_cache)

            # Verify cached tweets returned without error
            assert len(result) == 1
            # Cached tweets have 'tweet_id' key from database schema
            assert result[0]["tweet_id"] == "cached_tweet"

    def test_no_tweet_cache_uses_original_behavior(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_recent_tweets without tweet_cache uses original API behavior."""
        from src.enrich.api_client import XEnrichmentClient

        user_id = "no_cache_user"
        new_tweets = [
            {
                "id": "api_tweet_1",
                "text": "API tweet 1",
                "created_at": "2024-05-22T10:00:00.000Z",
                "public_metrics": {"like_count": 1},
            },
        ]

        with patch.object(XEnrichmentClient, '_fetch_tweets_from_api') as mock_fetch:
            mock_fetch.return_value = new_tweets

            auth = MagicMock()
            auth.access_token = "test_token"
            client = XEnrichmentClient(auth=auth)

            # Call without tweet_cache parameter
            result = client.get_recent_tweets(user_id, max_tweets=50)

            # Verify API was called directly (no cache logic)
            mock_fetch.assert_called_once_with(user_id, 50)
            assert len(result) == 1
            assert result[0]["id"] == "api_tweet_1"

    def test_cache_count_less_than_max_fetches_remaining(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_recent_tweets fetches only the remaining count when cache has partial tweets."""
        from src.enrich.api_client import XEnrichmentClient

        user_id = "partial_fetch_user"
        # Pre-populate cache with exactly 30 tweets
        cached_tweets = []
        for i in range(30):
            cached_tweets.append({
                "id": f"cached_{i}",
                "text": f"Cached {i}",
                "created_at": f"2024-05-21T17:34:{i % 60:02d}.000Z",
                "public_metrics": {"like_count": i},
            })
        temp_tweet_cache.persist_tweets(user_id, cached_tweets)

        new_tweets = [
            {
                "id": "new_1",
                "text": "New 1",
                "created_at": "2024-05-22T10:00:00.000Z",
                "public_metrics": {"like_count": 100},
            },
        ]

        with patch.object(XEnrichmentClient, '_fetch_tweets_from_api') as mock_fetch:
            mock_fetch.return_value = new_tweets

            auth = MagicMock()
            auth.access_token = "test_token"
            client = XEnrichmentClient(auth=auth)

            result = client.get_recent_tweets(user_id, max_tweets=50, tweet_cache=temp_tweet_cache)

            # Verify API was called for exactly 20 tweets (50 - 30 = 20)
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args
            assert call_args[0][1] == 20  # max_tweets argument

    def test_api_exception_returns_partial_results(
        self, temp_tweet_cache: TweetCache
    ) -> None:
        """Test get_recent_tweets returns cached tweets when API raises exception."""
        from src.enrich.api_client import XEnrichmentClient

        user_id = "exception_user"
        # Pre-populate cache with tweets
        cached_tweets = [{
            "id": "cached_exception",
            "text": "Cached exception tweet",
            "created_at": "2024-05-21T10:00:00.000Z",
            "public_metrics": {"like_count": 5},
        }]
        temp_tweet_cache.persist_tweets(user_id, cached_tweets)

        with patch.object(XEnrichmentClient, '_fetch_tweets_from_api') as mock_fetch:
            # API raises exception
            mock_fetch.side_effect = Exception("API error")

            auth = MagicMock()
            auth.access_token = "test_token"
            client = XEnrichmentClient(auth=auth)

            result = client.get_recent_tweets(user_id, max_tweets=50, tweet_cache=temp_tweet_cache)

            # Should return cached tweets even though API failed
            assert len(result) == 1
            assert result[0]["tweet_id"] == "cached_exception"