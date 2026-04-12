"""SQLite-backed tweet cache with O(1) deduplication.

Provides TweetCache class for persisting tweets with automatic deduplication
via PRIMARY KEY constraint. Tweet IDs are stored as TEXT to prevent precision
loss for 64-bit X snowflake IDs.

Usage:
    from src.enrich.tweet_cache import TweetCache

    cache = TweetCache()  # Creates data/tweets.db

    # Persist tweets (duplicates ignored)
    count = cache.persist_tweets("user_123", tweets)

    # Load cached tweets for a user
    result = cache.load_tweets("user_123")
    for tweet in result.tweets:
        print(tweet["text"])
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TweetCacheResult:
    """Result of loading tweets from cache.

    Attributes:
        tweets: List of tweet dicts with tweet_id, user_id, text, etc.
        count: Number of tweets in the result.
        user_id: The user_id that was queried.
    """

    tweets: list[dict[str, Any]]
    count: int
    user_id: str


class TweetCache:
    """SQLite-backed tweet cache with O(1) deduplication.

    Stores tweets in a SQLite database with:
    - TEXT PRIMARY KEY for tweet_id (prevents 64-bit precision loss)
    - Indexes on user_id and created_at for efficient queries
    - WAL mode for concurrent reads during writes
    - INSERT OR IGNORE for atomic deduplication
    """

    def __init__(self, db_path: Path | str = Path("data/tweets.db")) -> None:
        """Initialize TweetCache with database path.

        Creates the database file and schema if they don't exist.

        Args:
            db_path: Path to SQLite database file. Defaults to data/tweets.db.
        """
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create database file and schema if they don't exist.

        Creates:
        - Parent directories if needed
        - tweets table with TEXT tweet_id PRIMARY KEY
        - Indexes on user_id and created_at
        - WAL journal mode for concurrent reads
        """
        # Create parent directories
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            CREATE TABLE IF NOT EXISTS tweets (
                tweet_id      TEXT PRIMARY KEY,
                user_id       TEXT NOT NULL,
                text          TEXT,
                created_at    TEXT,
                like_count    INTEGER DEFAULT 0,
                retweet_count INTEGER DEFAULT 0,
                reply_count   INTEGER DEFAULT 0,
                fetched_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_tweets_user ON tweets(user_id);
            CREATE INDEX IF NOT EXISTS idx_tweets_created ON tweets(created_at DESC);
        """
        )
        conn.commit()
        conn.close()

    def load_tweets(self, user_id: str) -> TweetCacheResult:
        """Load all cached tweets for a user, newest first.

        Args:
            user_id: X user ID to load tweets for.

        Returns:
            TweetCacheResult with tweets, count, and user_id.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT tweet_id, user_id, text, created_at,
                   like_count, retweet_count, reply_count
            FROM tweets
            WHERE user_id = ?
            ORDER BY created_at DESC
        """,
            (user_id,),
        ).fetchall()
        conn.close()

        tweets = [dict(row) for row in rows]
        return TweetCacheResult(tweets=tweets, count=len(tweets), user_id=user_id)

    def persist_tweets(
        self,
        user_id: str,
        tweets: list[dict[str, Any]],
    ) -> int:
        """Persist tweets with automatic deduplication via PRIMARY KEY.

        Uses INSERT OR IGNORE to skip duplicate tweet_ids atomically.
        Returns count of newly inserted tweets (excludes duplicates).

        Args:
            user_id: X user ID that owns these tweets.
            tweets: List of tweet dicts from X API.

        Returns:
            Number of tweets inserted (duplicates ignored).
        """
        if not tweets:
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Extract tweet fields for batch insert
        rows = [
            (
                t.get("id"),
                user_id,
                t.get("text"),
                t.get("created_at"),
                t.get("public_metrics", {}).get("like_count", 0),
                t.get("public_metrics", {}).get("retweet_count", 0),
                t.get("public_metrics", {}).get("reply_count", 0),
            )
            for t in tweets
        ]

        cursor.executemany(
            """
            INSERT OR IGNORE INTO tweets
            (tweet_id, user_id, text, created_at, like_count, retweet_count, reply_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            rows,
        )

        inserted = cursor.rowcount
        conn.commit()
        conn.close()
        return inserted