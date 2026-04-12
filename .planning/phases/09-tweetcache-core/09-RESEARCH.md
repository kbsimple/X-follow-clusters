# Phase 09: TweetCache Core - Research

**Researched:** 2026-04-12
**Domain:** SQLite tweet caching with O(1) deduplication
**Confidence:** HIGH

## Summary

This phase implements the foundational storage layer for tweet caching using SQLite. The core deliverable is a `TweetCache` class that can load cached tweets for a user from SQLite and persist new tweets with automatic deduplication via PRIMARY KEY constraints. The research confirms that SQLite (built-in to Python) is the correct choice: zero dependencies, O(1) deduplication, indexed queries for watermark lookups, and WAL mode for safe concurrent reads.

Key architectural decision: tweets are stored in a separate `data/tweets.db` database rather than embedded in account JSON files. This enables efficient accumulation without file bloat, indexed queries for `since_id` watermarks (Phase 10), and atomic deduplication. Tweet IDs MUST be stored as TEXT to prevent JavaScript precision loss (X snowflake IDs are 64-bit integers, JavaScript only supports 53-bit safely).

**Primary recommendation:** Create `src/enrich/tweet_cache.py` with TweetCache class, SQLite schema with TEXT primary key, and unit tests following existing `tests/test_*.py` patterns.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlite3` | Python built-in (3.9+) | Tweet cache database | Zero dependencies, PRIMARY KEY deduplication, WAL mode for concurrent reads, handles 500K+ tweets easily |
| `pathlib.Path` | Python built-in | File path handling | Consistent with existing codebase patterns |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` | Python built-in | TweetCache result dataclass | Return type for cache operations |
| `json` | Python built-in | Account JSON interop | Reading account metadata (not tweets) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLite | Parquet per account | Parquet not append-friendly; requires rewriting entire file for accumulation |
| SQLite | Embed in account JSON | Inefficient deduplication O(n), file bloat, no indexing for watermark queries |
| `sqlite3` | `aiosqlite` | 15x slower for sequential ops; no benefit since existing codebase is synchronous |
| `sqlite3` | SQLAlchemy | ORM overhead for simple key-value access; direct queries are cleaner |

**Installation:** No installation required - `sqlite3` is built-in to Python 3.9+.

**Version verification:**
```bash
python3 -c "import sqlite3; print(sqlite3.sqlite_version)"
# Current system: 3.51.0 (verified 2026-04-12)
```

## Architecture Patterns

### Recommended Project Structure

```
src/
├── enrich/
│   ├── __init__.py
│   ├── api_client.py       # EXISTING - XEnrichmentClient
│   ├── enrich.py           # EXISTING - enrichment orchestration
│   ├── rate_limiter.py     # EXISTING - exponential backoff
│   ├── test_enrich.py      # EXISTING - test driver
│   └── tweet_cache.py      # NEW - TweetCache class
data/
├── enrichment/             # EXISTING - account JSON files
│   └── {account_id}.json
└── tweets.db               # NEW - SQLite tweet cache
tests/
├── conftest.py             # EXISTING - shared fixtures
└── test_tweet_cache.py     # NEW - TweetCache unit tests
```

### Pattern 1: TweetCache Class Design

**What:** A cache-first tweet storage class that loads cached tweets from SQLite and persists new tweets with automatic deduplication.

**When to use:** Phase 9 implements core load/save. Phase 10 adds incremental fetch. Phase 11 adds merge logic.

**Example:**
```python
# src/enrich/tweet_cache.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TweetCacheResult:
    """Result of loading tweets from cache."""
    tweets: list[dict[str, Any]]
    count: int
    user_id: str


class TweetCache:
    """SQLite-backed tweet cache with O(1) deduplication."""

    def __init__(self, db_path: Path | str = Path("data/tweets.db")):
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create database and schema if not exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            CREATE TABLE IF NOT EXISTS tweets (
                tweet_id    TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                text        TEXT,
                created_at  TEXT,
                like_count  INTEGER DEFAULT 0,
                retweet_count INTEGER DEFAULT 0,
                reply_count INTEGER DEFAULT 0,
                fetched_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_tweets_user ON tweets(user_id);
            CREATE INDEX IF NOT EXISTS idx_tweets_created ON tweets(created_at DESC);
        ''')
        conn.commit()
        conn.close()

    def load_tweets(self, user_id: str) -> TweetCacheResult:
        """Load all cached tweets for a user, newest first."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''
            SELECT tweet_id, user_id, text, created_at,
                   like_count, retweet_count, reply_count
            FROM tweets
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,)).fetchall()
        conn.close()

        tweets = [dict(row) for row in rows]
        return TweetCacheResult(tweets=tweets, count=len(tweets), user_id=user_id)

    def persist_tweets(
        self,
        user_id: str,
        tweets: list[dict[str, Any]],
    ) -> int:
        """Persist tweets with automatic deduplication via PRIMARY KEY.

        Returns count of newly inserted tweets (excludes duplicates).
        """
        if not tweets:
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Batch insert with INSERT OR IGNORE for deduplication
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

        cursor.executemany('''
            INSERT OR IGNORE INTO tweets
            (tweet_id, user_id, text, created_at, like_count, retweet_count, reply_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', rows)

        inserted = cursor.rowcount
        conn.commit()
        conn.close()
        return inserted
```

**Source:** Adapted from milestone STACK.md schema design [CITED: .planning/research/STACK.md]

### Pattern 2: TweetCache Integration with api_client.py

**What:** The existing `get_recent_tweets()` method will delegate to TweetCache for storage.

**When to use:** Phase 10 modifies this method to use cache-first logic. Phase 9 only needs TweetCache class.

**Current signature (from api_client.py:212-260):**
```python
def get_recent_tweets(
    self,
    user_id: str,
    max_tweets: int = 50,
) -> list[dict[str, Any]]:
```

### Anti-Patterns to Avoid

- **Storing tweet IDs as INTEGER:** X snowflake IDs are 64-bit; SQLite INTEGER can handle up to 8 bytes (64-bit), but TEXT is safer for consistency with JSON serialization and prevents any edge case precision loss.
- **Embedding tweets in account JSON:** Current `recent_tweets` array in account JSON is overwritten each run. Accumulating there causes file bloat and O(n) deduplication.
- **Using `INSERT` without `OR IGNORE`:** Would raise IntegrityError on duplicate tweet_id, crashing the pipeline.
- **Skipping WAL mode:** Without WAL, concurrent reads block during writes, causing performance issues.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Deduplication | Set-based dedup in Python | SQLite PRIMARY KEY | O(1) at database level, atomic, no race conditions |
| Connection pooling | Custom connection manager | sqlite3.connect per operation | SQLite handles connection pooling internally; overhead is minimal |
| Transaction management | Manual begin/commit | Context manager or explicit commit | SQLite autocommit mode with explicit commit is simpler |
| File locking | Custom lock file | SQLite WAL mode | WAL handles concurrent reads automatically |

**Key insight:** SQLite's PRIMARY KEY constraint provides atomic deduplication. Attempting to dedupe in Python requires reading all existing tweets into memory (O(n)), checking for duplicates, then writing back. SQLite handles this with a single `INSERT OR IGNORE` statement.

## Common Pitfalls

### Pitfall 1: Tweet ID Precision Loss

**What goes wrong:** X snowflake IDs are 64-bit integers. JavaScript/JSON only safely represent integers up to 2^53. Storing as INTEGER or serializing through JSON without `id_str` causes precision loss for IDs > 9007199254740991.

**Why it happens:** Default JSON serialization may convert large integers incorrectly; some ORMs auto-detect INTEGER type.

**How to avoid:**
1. Schema uses `TEXT PRIMARY KEY` for tweet_id
2. Always use `id_str` from X API (already strings in current codebase)
3. Never cast tweet IDs to int

**Warning signs:** Duplicate tweets appearing, tweet lookups failing, IDs changing between fetch and store.

**Source:** [CITED: Twitter Developer Docs — Twitter IDs] — Official documentation confirms 64-bit ID requirement.

### Pitfall 2: Missing Index on user_id

**What goes wrong:** Without an index on `user_id`, loading tweets for a single user requires a full table scan O(n). With 500K+ tweets, this becomes noticeably slow.

**Why it happens:** Developers forget that PRIMARY KEY only indexes `tweet_id`, not `user_id`.

**How to avoid:** Schema includes `CREATE INDEX IF NOT EXISTS idx_tweets_user ON tweets(user_id)`.

**Warning signs:** `SELECT` queries taking >100ms for single-user lookups.

### Pitfall 3: Database File Permission Issues

**What goes wrong:** `data/tweets.db` cannot be created if `data/` directory doesn't exist or has wrong permissions.

**Why it happens:** SQLite doesn't auto-create parent directories.

**How to avoid:** `TweetCache._ensure_schema()` calls `self.db_path.parent.mkdir(parents=True, exist_ok=True)`.

**Warning signs:** `sqlite3.OperationalError: unable to open database file`.

### Pitfall 4: Unclosed Database Connections

**What goes wrong:** Not calling `conn.close()` leaks file handles and prevents WAL checkpoint.

**Why it happens:** Forgetting to close in error paths, or assuming garbage collection handles it.

**How to avoid:** Always close connections in finally block or use context manager pattern.

**Warning signs:** "database is locked" errors, `.wal` file growing unbounded.

## Code Examples

Verified patterns from existing codebase:

### Existing Tweet Structure (from data/enrichment/1000591.json)

```json
{
  "recent_tweets": [
    {
      "created_at": "2024-05-21T17:34:39.000Z",
      "id": "1792972284669407635",
      "public_metrics": {
        "retweet_count": 5,
        "reply_count": 10,
        "like_count": 49,
        "quote_count": 0,
        "bookmark_count": 2,
        "impression_count": 30751
      },
      "text": "/fin"
    }
  ]
}
```

**Key observations:**
- `id` is already a string in JSON (correct)
- `created_at` is ISO 8601 format
- `public_metrics` nested structure needs flattening for schema

### Existing Test Fixture Pattern (from tests/conftest.py)

```python
@pytest.fixture
def temp_enrichment_cache(tmp_path: Path) -> Path:
    """Create a temp enrichment cache directory with sample JSON files."""
    cache_dir = tmp_path / "enrichment"
    cache_dir.mkdir()
    # Create sample files...
    return cache_dir
```

**Apply to TweetCache testing:**
```python
@pytest.fixture
def temp_tweet_cache(tmp_path: Path) -> TweetCache:
    """Create a TweetCache with temporary database."""
    db_path = tmp_path / "tweets.db"
    return TweetCache(db_path=db_path)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Embed tweets in account JSON | Separate SQLite database | Milestone v1.2 design | Enables efficient accumulation, indexed queries, O(1) dedup |
| INTEGER tweet_id | TEXT tweet_id | From project inception | Prevents precision loss for 64-bit X snowflake IDs |
| DELETE journal mode | WAL mode | 2025 SQLite best practices | Concurrent reads during writes, better performance |

**Deprecated/outdated:**
- `aiosqlite`: 15x slower for sequential operations; only useful for concurrent async code
- `journal_mode=DELETE`: Replaced by WAL for better concurrency

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Consumer layer (embed.py, entities.py) will continue reading `recent_tweets` and `recent_tweets_text` from account JSON after Phase 11 merges | Architecture | Would require updating consumer layer to read from SQLite |
| A2 | Phase 11 accumulation will merge new tweets with cached tweets correctly without requiring consumer changes | Architecture | Embedding regeneration may need optimization |

**If this table is empty:** All claims in this research were verified or cited.

## Open Questions

1. **Should `recent_tweets` in account JSON be removed after SQLite migration?**
   - What we know: Current codebase reads `recent_tweets` from JSON (embed.py, entities.py)
   - What's unclear: Whether Phase 11 should update consumers to read from SQLite or maintain dual storage
   - Recommendation: Phase 11 should rebuild `recent_tweets_text` in account JSON for backward compatibility; Phase 12+ could migrate consumers

2. **What is the maximum practical tweets.db size?**
   - What we know: CACHE-03 says "no limit on stored posts"
   - What's unclear: Practical limits for SQLite before performance degrades
   - Recommendation: SQLite handles 10M+ rows easily; monitor query performance after 500K tweets

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.9+ | Core runtime | Yes | 3.9.6 | - |
| SQLite 3.35+ | WAL mode, UPSERT | Yes | 3.51.0 | - |
| pytest 8.0+ | Test framework | Yes | 8.4.2 | - |
| tweepy 4.14+ | API client (Phase 10) | Yes | 4.14.0+ | - |

**Missing dependencies with no fallback:** None - all dependencies available.

**Missing dependencies with fallback:** None.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | - |
| V3 Session Management | No | - |
| V4 Access Control | No | - |
| V5 Input Validation | Yes | SQLite parameterized queries (prevent SQL injection) |
| V6 Cryptography | No | - |

### Known Threat Patterns for Python/SQLite

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL Injection | Tampering | Parameterized queries via `?` placeholders - NEVER string concatenation |
| Path Traversal | Tampering | Validate db_path is within expected directory (data/) |

**Mitigation example:**
```python
# SAFE: Parameterized query
conn.execute("SELECT * FROM tweets WHERE user_id = ?", (user_id,))

# DANGEROUS: String concatenation - DO NOT USE
conn.execute(f"SELECT * FROM tweets WHERE user_id = '{user_id}'")
```

## Sources

### Primary (HIGH confidence)
- [CITED: .planning/research/STACK.md] - Schema design, integration patterns
- [CITED: .planning/research/ARCHITECTURE.md] - Component responsibilities, data flow
- [CITED: .planning/research/SUMMARY.md] - Milestone-level research findings
- [VERIFIED: sqlite3.sqlite_version] - SQLite 3.51.0 available on system
- [VERIFIED: tests/conftest.py] - Existing test fixture patterns

### Secondary (MEDIUM confidence)
- [CITED: Twitter Developer Docs — Twitter IDs] - 64-bit ID handling requirement
- [CITED: twitter-to-sqlite v0.22] - Production schema patterns for tweet storage

### Tertiary (LOW confidence)
- None - all claims verified or cited

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - SQLite is built-in, schema design from milestone research
- Architecture: HIGH - TweetCache class design follows existing codebase patterns
- Pitfalls: HIGH - Documented by X API official docs and production bugs

**Research date:** 2026-04-12
**Valid until:** 30 days - SQLite patterns are stable; schema design may evolve in Phase 11