# Phase 12: SQLite Embedding Cache - Research

**Researched:** 2026-04-24
**Domain:** SQLite embedding cache with incremental updates and model versioning
**Confidence:** HIGH

## Summary

This phase migrates the embedding cache from numpy `.npy` files to a SQLite database with WAL mode, following the established `TweetCache` pattern. The key challenges are: (1) storing 384-dimensional float32 embeddings as BLOBs efficiently, (2) detecting text changes via SHA-256 hashing, and (3) invalidating cache when the embedding model changes.

**Primary recommendation:** Follow the TweetCache pattern exactly. Use `np.save()`/`np.load()` with BytesIO for BLOB serialization, SHA-256 hexdigest for text hashing, and store the model identifier string for version tracking.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlite3 | stdlib | Database storage | Standard library, zero dependencies, proven pattern in TweetCache |
| hashlib | stdlib | Text hashing | Standard SHA-256 for change detection |
| numpy | 2.0.2 | Embedding storage | Already in use, efficient BLOB serialization via BytesIO |
| sentence-transformers | 5.1.2 | Embedding model | Already in use, `all-MiniLM-L6-v2` produces 384-dim vectors |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | Result types | For `EmbeddingCacheResult` dataclass |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLite BLOB | Parquet files | Parquet is better for analytics but doesn't support row-level incremental updates |
| SHA-256 hash | MD5/fingerprint | SHA-256 is cryptographically sound, negligible performance difference for short text |
| Model name string | Git revision SHA | Git SHA is more precise but requires HuggingFace Hub API calls; model name is sufficient for this use case |

**Installation:** No new dependencies required. All libraries are stdlib or already installed.

## Architecture Patterns

### Recommended Project Structure
```
src/
├── cluster/
│   ├── embed.py              # Modified to use EmbeddingCache
│   └── embedding_cache.py    # NEW: EmbeddingCache class
└── enrich/
    └── tweet_cache.py        # EXISTING: Pattern to follow

data/
├── embeddings.db             # NEW: SQLite embedding cache
├── embeddings.db-wal         # WAL journal
├── embeddings.db-shm         # Shared memory
├── embeddings.npy            # LEGACY: Migrate and delete
└── embeddings.sidecar.json   # LEGACY: Migrate and delete
```

### Pattern 1: EmbeddingCache Class (Follow TweetCache Exactly)
**What:** SQLite-backed cache with PRIMARY KEY deduplication and WAL mode
**When to use:** All embedding operations in `embed_accounts()`
**Example:**
```python
# Pattern from src/enrich/tweet_cache.py (VERIFIED: codebase)
class EmbeddingCache:
    """SQLite-backed embedding cache with incremental updates.

    Stores embeddings in SQLite with:
    - TEXT PRIMARY KEY for account_id
    - BLOB for embedding (serialized via np.save/BytesIO)
    - TEXT for text_hash (SHA-256 hexdigest)
    - TEXT for model_version (model identifier string)
    - WAL mode for concurrent reads
    """

    def __init__(self, db_path: Path | str = Path("data/embeddings.db")) -> None:
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create database with schema if not exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            CREATE TABLE IF NOT EXISTS embeddings (
                account_id    TEXT PRIMARY KEY,
                embedding     BLOB NOT NULL,
                text_hash     TEXT NOT NULL,
                model_version TEXT NOT NULL,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model_version);
        """)
        conn.commit()
        conn.close()
```

### Pattern 2: Numpy BLOB Serialization
**What:** Serialize numpy arrays to BLOB using `np.save()`/`np.load()` with BytesIO
**When to use:** Storing and loading embeddings from SQLite
**Example:**
```python
# Source: [VERIFIED: Stack Overflow best practices]
import io
import numpy as np
import sqlite3

def serialize_embedding(embedding: np.ndarray) -> bytes:
    """Serialize numpy array to BLOB for SQLite storage.

    Uses np.save() to preserve shape and dtype metadata.
    """
    out = io.BytesIO()
    np.save(out, embedding)
    out.seek(0)
    return out.read()

def deserialize_embedding(blob: bytes) -> np.ndarray:
    """Deserialize BLOB back to numpy array."""
    out = io.BytesIO(blob)
    out.seek(0)
    return np.load(out)
```

### Pattern 3: Text Hash for Change Detection
**What:** SHA-256 hash of text fields to detect bio/location changes
**When to use:** Checking if embedding needs recomputation
**Example:**
```python
# Source: [VERIFIED: Python docs]
import hashlib

def compute_text_hash(account: dict) -> str:
    """Compute SHA-256 hash of text used for embedding.

    Hashes the same text that get_text_for_embedding() produces.
    """
    text = get_text_for_embedding(account)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def needs_recompute(cached_hash: str, account: dict) -> bool:
    """Check if account text has changed since last embedding."""
    current_hash = compute_text_hash(account)
    return cached_hash != current_hash
```

### Pattern 4: Model Version Tracking
**What:** Store model identifier string; invalidate cache on mismatch
**When to use:** Checking if cached embeddings are from the same model
**Example:**
```python
# Source: [VERIFIED: codebase EMBEDDING_MODEL constant]
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

def get_model_version() -> str:
    """Get current model version identifier.

    Uses model name + library version for invalidation.
    Model name change = different model = invalidate.
    """
    import sentence_transformers
    return f"{EMBEDDING_MODEL}|st-{sentence_transformers.__version__}"

def is_model_version_current(cached_version: str) -> bool:
    """Check if cached embedding is from current model version."""
    return cached_version == get_model_version()
```

### Anti-Patterns to Avoid
- **Storing embeddings as JSON arrays:** Inefficient (10x larger), loses numpy efficiency
- **Using `tobytes()` for serialization:** Loses shape/dtype metadata, breaks on reshape
- **MD5 for hashing:** Cryptographically broken, SHA-256 is standard
- **Not using WAL mode:** Concurrent reads block during writes
- **Storing model revision SHA:** Overkill; model name is sufficient for invalidation

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|------|
| Numpy BLOB serialization | Custom pickle/JSON | `np.save()`/`np.load()` with BytesIO | Preserves shape, dtype, endianness |
| Text change detection | Custom diff algorithm | SHA-256 hash comparison | O(1) comparison, standard library |
| Model version tracking | Custom versioning system | Model name string + library version | Simple, sufficient for invalidation |
| Database access | Raw SQL everywhere | TweetCache pattern methods | Consistent interface, testable |

**Key insight:** The TweetCache pattern already solves SQLite WAL mode, PRIMARY KEY deduplication, and indexed queries. Copy it exactly.

## Common Pitfalls

### Pitfall 1: Forgetting to Seek BytesIO After Write
**What goes wrong:** `np.save()` leaves the BytesIO position at the end; `out.read()` returns empty bytes
**Why it happens:** BytesIO position isn't automatically reset after write
**How to avoid:** Always call `out.seek(0)` before reading, or use `out.getvalue()`
**Warning signs:** Embeddings deserialize as empty or corrupted arrays

### Pitfall 2: Hashing Account JSON Instead of Embedding Text
**What goes wrong:** Hash doesn't match because JSON serialization is non-deterministic
**Why it happens:** Using `json.dumps(account)` instead of `get_text_for_embedding(account)`
**How to avoid:** Always hash the exact text string that gets embedded
**Warning signs:** All embeddings recomputed on every run despite no text changes

### Pitfall 3: Not Handling Empty Text Accounts
**What goes wrong:** Empty text produces empty hash, all empty-text accounts share same cache key
**Why it happens:** SHA-256 of empty string is valid, but all empty strings have same hash
**How to avoid:** Skip caching entirely for accounts with empty text (they can't be embedded anyway)
**Warning signs:** Cache hits for different accounts with empty bios

### Pitfall 4: Model Version False Positives
**What goes wrong:** Cache invalidated on every run due to version format inconsistency
**Why it happens:** Version string format changes between runs (e.g., trailing whitespace)
**How to avoid:** Use deterministic version format, strip whitespace, test version comparison
**Warning signs:** `load_embeddings()` always returns empty despite valid cache

## Code Examples

### Complete EmbeddingCache Implementation
```python
# Source: [VERIFIED: TweetCache pattern + Stack Overflow BLOB serialization]
from __future__ import annotations

import hashlib
import io
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from src.cluster.embed import EMBEDDING_MODEL, get_text_for_embedding

EMBEDDING_DIM = 384


@dataclass
class EmbeddingCacheResult:
    """Result of loading embeddings from cache."""
    account_ids: list[str]
    embeddings: np.ndarray  # shape (n, 384)
    count: int
    missing_account_ids: list[str]  # accounts not in cache or need recompute


def get_model_version() -> str:
    """Get current embedding model version identifier."""
    import sentence_transformers
    return f"{EMBEDDING_MODEL}|st-{sentence_transformers.__version__}"


class EmbeddingCache:
    """SQLite-backed embedding cache with incremental updates."""

    def __init__(self, db_path: Path | str = Path("data/embeddings.db")) -> None:
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create database and schema if not exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            CREATE TABLE IF NOT EXISTS embeddings (
                account_id    TEXT PRIMARY KEY,
                embedding     BLOB NOT NULL,
                text_hash     TEXT NOT NULL,
                model_version TEXT NOT NULL,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        conn.close()

    def get_cached_embedding(
        self,
        account_id: str,
        account: dict,
    ) -> np.ndarray | None:
        """Get cached embedding if valid (correct model version and text hash)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT embedding, text_hash, model_version FROM embeddings WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        conn.close()

        if row is None:
            return None

        # Check model version
        if row["model_version"] != get_model_version():
            return None

        # Check text hash
        current_hash = hashlib.sha256(
            get_text_for_embedding(account).encode("utf-8")
        ).hexdigest()
        if row["text_hash"] != current_hash:
            return None

        # Deserialize embedding
        return np.load(io.BytesIO(row["embedding"]))

    def save_embedding(
        self,
        account_id: str,
        embedding: np.ndarray,
        account: dict,
    ) -> None:
        """Save embedding to cache with metadata."""
        text_hash = hashlib.sha256(
            get_text_for_embedding(account).encode("utf-8")
        ).hexdigest()
        model_version = get_model_version()

        # Serialize embedding
        out = io.BytesIO()
        np.save(out, embedding)
        blob = out.getvalue()

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO embeddings
            (account_id, embedding, text_hash, model_version)
            VALUES (?, ?, ?, ?)
            """,
            (account_id, blob, text_hash, model_version),
        )
        conn.commit()
        conn.close()

    def load_all_embeddings(self) -> tuple[np.ndarray, list[str]]:
        """Load all valid embeddings as numpy array.

        Returns embeddings for accounts with current model version only.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT account_id, embedding FROM embeddings WHERE model_version = ?",
            (get_model_version(),),
        ).fetchall()
        conn.close()

        if not rows:
            return np.empty((0, EMBEDDING_DIM)), []

        embeddings = []
        account_ids = []
        for row in rows:
            emb = np.load(io.BytesIO(row["embedding"]))
            embeddings.append(emb)
            account_ids.append(row["account_id"])

        return np.vstack(embeddings), account_ids
```

### Migration Script (One-Time)
```python
# Source: [VERIFIED: codebase analysis]
"""Migrate from embeddings.npy to embeddings.db."""

import json
from pathlib import Path

import numpy as np

from src.cluster.embedding_cache import EmbeddingCache, get_model_version


def migrate_npy_to_sqlite():
    """One-time migration from numpy cache to SQLite."""
    npy_path = Path("data/embeddings.npy")
    sidecar_path = Path("data/embeddings.sidecar.json")

    if not npy_path.exists():
        print("No numpy cache to migrate")
        return

    # Load existing cache
    embeddings = np.load(npy_path)
    with open(sidecar_path) as f:
        usernames = json.load(f)

    print(f"Migrating {len(usernames)} embeddings...")

    # Create SQLite cache
    cache = EmbeddingCache()

    # Load enrichment data to get account IDs
    enrichment_dir = Path("data/enrichment")
    username_to_id = {}
    for f in enrichment_dir.glob("*.json"):
        if f.stem in ("suspended", "protected", "errors"):
            continue
        data = json.load(open(f))
        username_to_id[data.get("username")] = data.get("id")

    # Migrate each embedding
    for i, username in enumerate(usernames):
        account_id = username_to_id.get(username)
        if account_id is None:
            print(f"  Warning: No account ID for {username}, skipping")
            continue

        # Load account for text hash
        account_path = enrichment_dir / f"{account_id}.json"
        if not account_path.exists():
            print(f"  Warning: No enrichment file for {username}, skipping")
            continue

        account = json.load(open(account_path))
        cache.save_embedding(account_id, embeddings[i], account)

    print(f"Migration complete: {len(usernames)} embeddings migrated")

    # Rename old files (don't delete immediately)
    npy_path.rename(npy_path.with_suffix(".npy.migrated"))
    sidecar_path.rename(sidecar_path.with_suffix(".json.migrated"))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Numpy `.npy` + sidecar JSON | SQLite with BLOB | Phase 12 | Incremental updates, model versioning, text change detection |
| No cache invalidation | Model version + text hash | Phase 12 | Automatic re-embedding on model change or bio update |
| Whole-cache replacement | Per-account upsert | Phase 12 | Only compute changed embeddings |

**Deprecated/outdated:**
- `embeddings.npy` / `embeddings.sidecar.json`: Replaced by SQLite-based cache

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Model name string is sufficient for version tracking | Model Version Tracking | If model weights change without name change, stale embeddings used |
| A2 | SHA-256 hash of embedding text is stable across runs | Text Hash | If text format changes (e.g., field order), cache unnecessarily invalidated |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed.

## Open Questions

1. **Should migration delete or rename old numpy files?**
   - What we know: Migration script renames to `.migrated` suffix
   - What's unclear: Whether to auto-delete after successful migration
   - Recommendation: Rename first, delete manually after verification

2. **Should `get_model_version()` include embedding dimension?**
   - What we know: Current approach uses model name + library version
   - What's unclear: Whether to include `EMBEDDING_DIM` in version string
   - Recommendation: Not needed — dimension is implied by model name

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| sqlite3 | EmbeddingCache | ✓ | stdlib | — |
| hashlib | Text hashing | ✓ | stdlib | — |
| numpy | Embedding serialization | ✓ | 2.0.2 | — |
| sentence-transformers | Embedding model | ✓ | 5.1.2 | — |
| Python | Runtime | ✓ | 3.9 | — |

**Missing dependencies with no fallback:** None

**Missing dependencies with fallback:** None

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A |
| V5 Input Validation | yes | SQLite parameterized queries (prevent SQL injection) |
| V6 Cryptography | yes | SHA-256 for text hashing (stdlib hashlib) |

### Known Threat Patterns for SQLite

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection | Tampering | Parameterized queries via `?` placeholders |
| Path traversal | Tampering | Validate `db_path` doesn't escape data directory |

## Sources

### Primary (HIGH confidence)
- [Stack Overflow: Python insert numpy array into sqlite3 database](https://stackoverflow.com/questions/18621513/python-insert-numpy-array-into-sqlite3-database) - BLOB serialization pattern
- [Python docs: hashlib](https://docs.python.org/3/library/hashlib.html) - SHA-256 hashing
- Codebase: `src/enrich/tweet_cache.py` - TweetCache pattern (WAL mode, PRIMARY KEY, indexed queries)
- Codebase: `src/cluster/embed.py` - Current embedding implementation

### Secondary (MEDIUM confidence)
- [sentence-transformers GitHub: Model loading issues](https://github.com/UKPLab/sentence-transformers/issues/2523) - Cache invalidation patterns

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries are stdlib or already in use
- Architecture: HIGH - TweetCache pattern is proven in this codebase
- Pitfalls: HIGH - Based on common SQLite/numpy patterns and codebase experience

**Research date:** 2026-04-24
**Valid until:** 30 days (stable Python/SQLite patterns)