# Architecture Research: Tweet Caching Integration

**Domain:** Tweet caching with accumulation for X Following Organizer
**Researched:** 2026-04-12
**Confidence:** HIGH (existing codebase analysis)

## Current Architecture Overview

```
                                    ENRICHMENT FLOW (Current)
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API Layer                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐           │
│  │ XEnrichmentClient│  │ get_users()      │  │ get_recent_tweets│           │
│  │                  │  │                  │  │ ()               │           │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘           │
│           │                     │                     │                      │
├───────────┴─────────────────────┴─────────────────────┴──────────────────────┤
│                              Cache Layer                                     │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ data/enrichment/{account_id}.json                                     │  │
│  │ {                                                                      │  │
│  │   "id": "...", "username": "...",                                     │  │
│  │   "recent_tweets": [...],          // OVERWRITTEN each run            │  │
│  │   "recent_tweets_text": "...",     // Concatenated for embedding     │  │
│  │   "tweet_embedding": [...]         // 384-dim vector                  │  │
│  │ }                                                                      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│                          Consumer Layer                                      │
│  ┌──────────────────┐  ┌──────────────────┐                                 │
│  │ embed.py         │  │ entities.py      │                                 │
│  │ store_tweet_     │  │ extract_entities()│                                 │
│  │ embedding()      │  │                  │                                 │
│  └──────────────────┘  └──────────────────┘                                 │
│  Reads: recent_tweets_text  Reads: recent_tweets_text (chunked)             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Proposed Architecture (Tweet Cache with Accumulation)

```
                                    NEW ARCHITECTURE
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API Layer                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐           │
│  │ XEnrichmentClient│  │ get_users()      │  │ get_recent_tweets│           │
│  │   (modified)     │  │   (unchanged)    │  │    (modified)    │           │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘           │
│           │                     │                     │                      │
│           │                     │                     ▼                      │
│           │                     │         ┌─────────────────────┐           │
│           │                     │         │ TweetCache (NEW)    │           │
│           │                     │         │ - load_cached()     │           │
│           │                     │         │ - fetch_new()       │           │
│           │                     │         │ - merge_and_dedupe()│           │
│           │                     │         │ - persist()         │           │
│           │                     │         └─────────────────────┘           │
├───────────┴─────────────────────┴───────────────────────────────────────────┤
│                              Cache Layer                                     │
│                                                                              │
│  Account JSON (modified structure):                                         │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ {                                                                      │  │
│  │   "id": "...", "username": "...",                                     │  │
│  │   "recent_tweets": [...],          // ACCUMULATED across runs         │  │
│  │   "recent_tweets_text": "...",     // Rebuilt from accumulated        │  │
│  │   "tweet_ids_cached": [...],       // NEW: Set of known tweet IDs     │  │
│  │   "last_tweet_fetch": "ISO-TS",    // NEW: Last fetch timestamp      │  │
│  │   "tweet_embedding": [...]         // Rebuilt when tweets change      │  │
│  │ }                                                                      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                          Consumer Layer (Unchanged)                          │
│  ┌──────────────────┐  ┌──────────────────┐                                 │
│  │ embed.py         │  │ entities.py      │                                 │
│  │ (unchanged)      │  │ (unchanged)      │                                 │
│  └──────────────────┘  └──────────────────┘                                 │
│  Still reads: recent_tweets_text (now from accumulated tweets)              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Status |
|-----------|----------------|--------|
| `XEnrichmentClient` | Tweepy wrapper with rate limiting | Modified (use TweetCache) |
| `TweetCache` | Cache-first tweet fetching with accumulation | **NEW** |
| `api_client.py::get_recent_tweets()` | Fetch tweets from API | Modified (delegate to TweetCache) |
| `embed.py::store_tweet_embedding()` | Create tweet embeddings | Unchanged |
| `entities.py::extract_entities()` | Extract ORG/LOC/TITLE from text | Unchanged |
| `test_enrich.py` | End-to-end enrichment driver | Modified (cache-aware flow) |

## Integration Points

### 1. `api_client.py::get_recent_tweets()` (MODIFIED)

**Current behavior:**
```python
def get_recent_tweets(self, user_id: str, max_tweets: int = 50) -> list[dict]:
    # Always fetches fresh from API
    # Returns up to max_tweets
    # No cache integration
```

**New behavior:**
```python
def get_recent_tweets(
    self,
    user_id: str,
    max_tweets: int = 50,
    cache_dir: Path = Path("data/enrichment"),
) -> list[dict]:
    # 1. Load existing cached tweets for user_id
    # 2. Determine newest cached tweet ID
    # 3. Fetch only tweets newer than that (up to max_tweets)
    # 4. Merge new tweets with cached (dedupe by ID)
    # 5. Persist merged set back to cache
    # 6. Return merged list
```

### 2. Account JSON Structure (MODIFIED)

**Current structure:**
```json
{
  "id": "12345",
  "username": "example",
  "recent_tweets": [...],
  "recent_tweets_text": "concatenated text",
  "tweet_embedding": [0.1, 0.2, ...]
}
```

**New structure:**
```json
{
  "id": "12345",
  "username": "example",
  "recent_tweets": [...],
  "recent_tweets_text": "concatenated text",
  "tweet_embedding": [0.1, 0.2, ...],
  "tweet_ids_cached": ["123", "124", ...],
  "last_tweet_fetch": "2026-04-12T14:00:00Z"
}
```

### 3. Consumer Components (UNCHANGED)

`embed.py` and `entities.py` continue to read `recent_tweets_text`. The TweetCache ensures this field is rebuilt whenever tweets are accumulated.

## New Component: TweetCache

### Design

```python
# src/enrich/tweet_cache.py (NEW FILE)

@dataclass
class TweetCacheResult:
    """Result of cache-aware tweet fetching."""
    tweets: list[dict]          # All accumulated tweets
    new_count: int              # Count of newly fetched tweets
    total_count: int            # Total tweets in cache
    fetched_at: str             # ISO timestamp

class TweetCache:
    """Cache-first tweet fetching with accumulation."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir

    def load_cached(self, user_id: str) -> tuple[list[dict], set[str]]:
        """Load existing cached tweets for a user.

        Returns:
            (tweets, tweet_ids) - tweets list and set of known IDs
        """

    def fetch_new(
        self,
        user_id: str,
        known_ids: set[str],
        api_client: XEnrichmentClient,
        max_new: int = 50,
    ) -> list[dict]:
        """Fetch tweets newer than known_ids.

        Uses 'since_id' parameter to only fetch new tweets.
        """

    def merge_and_dedupe(
        self,
        cached: list[dict],
        new: list[dict],
    ) -> list[dict]:
        """Merge cached and new tweets, dedupe by ID.

        New tweets take precedence (updated metrics).
        Sorts by created_at descending.
        """

    def persist(
        self,
        user_id: str,
        tweets: list[dict],
        account_data: dict,
    ) -> None:
        """Write accumulated tweets back to account JSON.

        Updates:
        - recent_tweets
        - recent_tweets_text (rebuilt from merged tweets)
        - tweet_ids_cached
        - last_tweet_fetch
        """
```

### Key Implementation Details

1. **Deduplication Strategy:**
   - Use tweet `id` field as unique key
   - New tweets replace cached tweets with same ID (fresh metrics)
   - Sort by `created_at` descending after merge

2. **API Efficiency:**
   - Use `since_id` parameter to fetch only tweets newer than newest cached
   - Avoids re-fetching the same 50 tweets every run
   - Respects rate limits (900 requests/15min per endpoint)

3. **Cache Size:**
   - **No limit** on stored tweets (CACHE-03)
   - `recent_tweets_text` still uses only most recent for embedding
   - Full history kept for future analysis

4. **`recent_tweets_text` Generation:**
   - Rebuild from accumulated tweets on each cache update
   - Use top N by `created_at` (configurable, default 50)
   - Truncate to avoid GLiNER max length (chunked in entities.py)

## Data Flow

### Cache-First Tweet Fetching Flow

```
User triggers enrichment for account
            │
            ▼
┌─────────────────────────────────────┐
│ Load account JSON from cache        │
│ data/enrichment/{account_id}.json   │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ Extract cached tweet IDs            │
│ tweet_ids_cached: ["123", "124"...] │
└────────────────┬────────────────────┘
                 │
                 ▼
        ┌────────┴────────┐
        │ Any cached IDs? │
        └────────┬────────┘
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
   [YES]               [NO]
       │                   │
       ▼                   ▼
┌──────────────┐  ┌──────────────────────┐
│ Use since_id │  │ Fetch first 50 tweets │
│ = newest ID  │  │ (no since_id)         │
└──────┬───────┘  └──────────┬───────────┘
       │                     │
       └──────────┬──────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ Merge new tweets with cached        │
│ Dedupe by ID (new wins)             │
│ Sort by created_at descending       │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ Update account JSON:                │
│ - recent_tweets = merged list       │
│ - recent_tweets_text = top N text   │
│ - tweet_ids_cached = all IDs        │
│ - last_tweet_fetch = now()          │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ Rebuild tweet_embedding             │
│ (if tweets changed)                 │
└─────────────────────────────────────┘
```

## Build Order

### Phase 1: Core TweetCache (New Component)

```
src/enrich/tweet_cache.py       # NEW - TweetCache class with all methods
tests/test_tweet_cache.py       # NEW - Unit tests for TweetCache
```

**Dependencies:** None (pure utility)

### Phase 2: API Client Integration (Modified Component)

```
src/enrich/api_client.py        # MODIFIED - get_recent_tweets() uses TweetCache
```

**Dependencies:** Phase 1 (TweetCache)

### Phase 3: Test Driver Update (Modified Component)

```
src/enrich/test_enrich.py       # MODIFIED - Use cache-aware flow
```

**Dependencies:** Phase 2 (modified api_client)

### Phase 4: Integration Tests

```
tests/test_enrichment_flow.py   # NEW - End-to-end cache accumulation test
```

**Dependencies:** Phases 1-3

## No Changes Required

| Component | Reason |
|-----------|--------|
| `embed.py` | Reads `recent_tweets_text` which TweetCache maintains |
| `entities.py` | Reads `recent_tweets_text` which TweetCache maintains |
| `cluster/*.py` | Consumes embeddings, not raw tweets |
| `scrape/*.py` | Profile scraping, not tweet-related |

## Anti-Patterns to Avoid

### Anti-Pattern 1: Over-fetching from API

**What people do:** Always fetch 50 tweets, ignoring cached tweets.

**Why it's wrong:** Wastes API quota, hits rate limits faster, slow for large following lists.

**Do this instead:** Use `since_id` to fetch only new tweets. If 48 tweets are cached, fetch 2 new ones.

### Anti-Pattern 2: Stale Tweet Metrics

**What people do:** Cache tweets forever without updating engagement metrics.

**Why it's wrong:** `public_metrics` (likes, retweets) become stale over time.

**Do this instead:** When a tweet is re-fetched, update the cached version with fresh metrics (new wins on dedupe).

### Anti-Pattern 3: Unbounded `recent_tweets_text`

**What people do:** Concatenate ALL cached tweets for embedding.

**Why it's wrong:** SentenceTransformer and GLiNER have max sequence lengths. 500+ tweets will truncate unpredictably.

**Do this instead:** Use only top N by `created_at` for `recent_tweets_text`. Full history kept separately.

## Testing Strategy

| Test Type | Focus |
|-----------|-------|
| Unit | TweetCache.load_cached(), merge_and_dedupe() |
| Unit | Deduplication by tweet ID |
| Unit | since_id parameter construction |
| Integration | First fetch (no cache) vs subsequent fetch (with cache) |
| Integration | Embedding rebuild on tweet accumulation |
| Regression | Existing embed.py and entities.py still work |

## Sources

- Codebase analysis: `src/enrich/api_client.py`, `src/enrich/test_enrich.py`, `src/cluster/embed.py`, `src/scrape/entities.py`
- Sample cache file: `data/enrichment/1000591.json`
- Project requirements: `.planning/PROJECT.md` (CACHE-01, CACHE-02, CACHE-03)

---

*Architecture research for: Tweet caching with accumulation*
*Researched: 2026-04-12*