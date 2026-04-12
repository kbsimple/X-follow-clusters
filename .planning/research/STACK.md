# Stack Research: Tweet Caching with Accumulation

**Domain:** Tweet caching for X API enrichment pipeline
**Researched:** 2026-04-12
**Confidence:** HIGH

## Recommended Stack Additions

### Core Storage: SQLite (built-in)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `sqlite3` | Python built-in | Tweet cache database | Zero dependencies, automatic deduplication via PRIMARY KEY, handles 500K+ tweets easily, synchronous (matches existing codebase) |

**Rationale:** The project is synchronous (no async/await), so `sqlite3` is the right choice. Async alternatives like `aiosqlite` add overhead (15x slower for sequential ops) without benefit since SQLite has a single-writer lock anyway.

### Storage Format Decision

| Choice | Recommendation | Why |
|--------|----------------|-----|
| **SQLite DB** | `data/tweets.db` | Separate from account JSON, efficient deduplication, indexed queries |
| JSON files | NOT recommended for tweets | Inefficient deduplication, must read/parse/write entire file, no indexing |

**Why separate SQLite rather than embedding in account JSON:**
1. Deduplication: `INSERT OR IGNORE` with PRIMARY KEY is O(1) vs O(n) for JSON array scans
2. Accumulation: Tweets grow unbounded; embedded arrays bloat account files
3. Query efficiency: Index on `created_at` enables chronological queries without loading all tweets
4. Write safety: SQLite handles concurrent reads; JSON files risk corruption on partial writes

## Schema Design

```sql
CREATE TABLE IF NOT EXISTS tweets (
    tweet_id    TEXT PRIMARY KEY,  -- X snowflake IDs as TEXT (avoid integer overflow)
    user_id     TEXT NOT NULL,     -- Account ID for joins
    text        TEXT,              -- Tweet content
    created_at  TEXT,              -- ISO 8601 timestamp from X API
    like_count  INTEGER DEFAULT 0,
    retweet_count INTEGER DEFAULT 0,
    reply_count INTEGER DEFAULT 0,
    fetched_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Essential indexes
CREATE INDEX IF NOT EXISTS idx_tweets_user ON tweets(user_id);
CREATE INDEX IF NOT EXISTS idx_tweets_created ON tweets(created_at DESC);

-- Enable WAL for better read/write concurrency
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
```

**Key design decisions:**
- `tweet_id` as TEXT: X IDs are 64-bit integers that can overflow Python floats; TEXT is safe
- `user_id` index: Enables `SELECT * FROM tweets WHERE user_id = ?` without full table scan
- `created_at` index: Supports "newest tweets" queries for `since_id` logic
- WAL mode: Allows reads during writes (important for accumulation across runs)

## Integration Pattern

### Fetch Flow (Accumulation)

```python
def fetch_and_cache_tweets(client, user_id: str, cache_db: Path) -> list[dict]:
    """Fetch new tweets only, accumulate in SQLite."""
    conn = sqlite3.connect(cache_db)

    # Get newest cached tweet ID for this user
    since_id = conn.execute(
        'SELECT tweet_id FROM tweets WHERE user_id = ? ORDER BY created_at DESC LIMIT 1',
        (user_id,)
    ).fetchone()

    # Fetch only tweets newer than since_id
    new_tweets = client.get_users_tweets(
        id=user_id,
        since_id=since_id[0] if since_id else None,
        max_results=100,
        tweet_fields=["created_at", "public_metrics"]
    )

    # Batch insert with automatic deduplication
    if new_tweets:
        conn.executemany('''
            INSERT OR IGNORE INTO tweets
            (tweet_id, user_id, text, created_at, like_count, retweet_count, reply_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', [(t['id'], user_id, t['text'], t['created_at'],
               t['public_metrics'].get('like_count', 0),
               t['public_metrics'].get('retweet_count', 0),
               t['public_metrics'].get('reply_count', 0))
              for t in new_tweets])
        conn.commit()

    return new_tweets
```

### Read Flow (Embedding Generation)

```python
def get_cached_tweets(user_id: str, cache_db: Path, limit: int = 100) -> list[dict]:
    """Get cached tweets for embedding generation."""
    conn = sqlite3.connect(cache_db)
    rows = conn.execute('''
        SELECT tweet_id, text, created_at
        FROM tweets
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, limit)).fetchall()
    return [{'id': r[0], 'text': r[1], 'created_at': r[2]} for r in rows]
```

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `aiosqlite` | 15x slower for sequential ops; no benefit for sync code | `sqlite3` (built-in) |
| `sqlalchemy` | ORM overhead for simple key-value access | Direct `sqlite3` queries |
| Redis | Overkill for local file-based cache; adds deployment complexity | SQLite |
| Parquet for tweets | Not append-friendly; requires rewriting entire file | SQLite for accumulation |
| DuckDB | Overkill for single-table cache; slower for simple point lookups | SQLite |
| Embed tweets in account JSON | Inefficient deduplication, file bloat, no indexing | Separate SQLite DB |

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| SQLite | Parquet per account | If you need columnar analytics on all tweets at once |
| SQLite | DuckDB | If you need complex analytical queries across all users |
| `since_id` | `until_id` pagination | `until_id` is for historical backfill; `since_id` for incremental fetch |
| Separate DB | Embed in account JSON | Only if total tweets per account is bounded (e.g., always 50) |

## Performance Characteristics

| Operation | Expected Performance |
|-----------|---------------------|
| Insert 100 tweets | ~5ms (batch insert) |
| Deduplication check | O(1) via PRIMARY KEY |
| Fetch 100 tweets by user_id | ~1ms (indexed) |
| Database size | ~500 bytes per tweet (uncompressed) |
| Max practical size | 10M+ tweets on single server |

**From 2025 benchmarks:** SQLite handles 500K+ records daily without optimization. The bottleneck is API fetching, not storage.

## Version Compatibility

| Package | Version | Notes |
|---------|---------|-------|
| Python sqlite3 | 3.9+ | Built-in, no installation needed |
| tweepy | 4.14+ | Already in pyproject.toml |
| pandas | 2.0+ | For optional DataFrame export |

## Migration Path

**Phase 1: Add SQLite cache alongside existing JSON**
- Create `data/tweets.db` with schema
- Modify `get_recent_tweets()` to write to SQLite
- Keep `recent_tweets` in JSON for backward compatibility

**Phase 2: Read from SQLite**
- Update `store_tweet_embedding()` to read from SQLite
- Remove `recent_tweets` field from account JSON

**Phase 3: Cleanup**
- Remove duplicate storage in JSON files
- Add migration script for existing `recent_tweets` data

## Sources

- [twitter-to-sqlite v0.22](https://pypi.org/project/twitter-to-sqlite/) — Schema patterns for tweet storage
- [SQLite Performance Benchmarks 2025](https://toxigon.com/sqlite-performance-benchmarks-2025-edition) — WAL mode, batch inserts, indexing strategies
- [aiosqlite Performance Issue #97](https://github.com/omnilib/aiosqlite/issues/97) — 15x slower for sequential, 4x faster for concurrent
- [Tweepy Pagination Docs](https://docs.tweepy.org/en/v4.6.0/pagination.html) — `since_id` and `until_id` patterns
- [Stack Overflow: Retrieve 100+ tweets](https://stackoverflow.com/questions/76620198/how-to-retrieve-more-than-a-100-tweets-on-twitter-api-v2-using-python) — Pagination implementation examples
- [Prep: Tweet Storage Design](https://deprep.substack.com/p/prep-16-designing-a-simple-social) — Schema design principles

---
*Stack research for: Tweet caching with accumulation*
*Researched: 2026-04-12*