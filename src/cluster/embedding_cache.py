"""SQLite-backed embedding cache with incremental updates.

Provides EmbeddingCache class for persisting embeddings with automatic
invalidation via model version tracking and text hash comparison.

Usage:
    from src.cluster.embedding_cache import EmbeddingCache

    cache = EmbeddingCache()  # Creates data/embeddings.db

    # Save embedding with metadata
    cache.save_embedding("account_123", embedding, account_dict)

    # Get cached embedding (returns None if invalid or missing)
    embedding = cache.get_cached_embedding("account_123", account_dict)

    # Load all valid embeddings as numpy array
    embeddings, account_ids = cache.load_all_embeddings()
"""

from __future__ import annotations

import hashlib
import io
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from src.cluster.embed import EMBEDDING_MODEL, EMBEDDING_DIM, get_text_for_embedding


@dataclass
class EmbeddingCacheResult:
    """Result of loading embeddings from cache.

    Attributes:
        account_ids: List of account IDs with valid cached embeddings.
        embeddings: Numpy array of shape (n, 384) with embedding vectors.
        count: Number of embeddings in the result.
        missing_account_ids: Accounts not in cache or needing recompute.
    """

    account_ids: list[str]
    embeddings: np.ndarray  # shape (n, EMBEDDING_DIM)
    count: int
    missing_account_ids: list[str]


def get_model_version() -> str:
    """Get current embedding model version identifier.

    Uses model name + library version for invalidation.
    Model name change = different model = invalidate.

    Returns:
        Version string like "sentence-transformers/all-MiniLM-L6-v2|st-3.0.0"
    """
    import sentence_transformers
    return f"{EMBEDDING_MODEL}|st-{sentence_transformers.__version__}"


def compute_text_hash(account: dict) -> str:
    """Compute SHA-256 hash of text used for embedding.

    Hashes the same text that get_text_for_embedding() produces.
    This allows detecting when an account's bio/location changes.

    Args:
        account: Account dict with description, location, etc.

    Returns:
        64-character hex string (SHA-256 hash).
    """
    text = get_text_for_embedding(account)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        """Initialize EmbeddingCache with database path.

        Creates the database file and schema if they don't exist.

        Args:
            db_path: Path to SQLite database file. Defaults to data/embeddings.db.
        """
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create database file and schema if they don't exist.

        Creates:
        - Parent directories if needed
        - embeddings table with TEXT account_id PRIMARY KEY
        - Index on model_version for efficient filtering
        - WAL journal mode for concurrent reads
        """
        # Create parent directories
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
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
        """
        )
        conn.commit()
        conn.close()

    def get_cached_embedding(
        self,
        account_id: str,
        account: dict,
    ) -> np.ndarray | None:
        """Get cached embedding if valid (correct model version and text hash).

        Args:
            account_id: X account ID.
            account: Account dict with description, location, etc.

        Returns:
            Cached embedding as numpy array of shape (384,), or None if:
            - No cached embedding exists
            - Model version has changed
            - Account text has changed (hash mismatch)
        """
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
        current_model_version = get_model_version()
        if row["model_version"] != current_model_version:
            return None

        # Check text hash
        current_hash = compute_text_hash(account)
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
        """Save embedding to cache with metadata.

        Uses INSERT OR REPLACE to handle updates (upsert behavior).

        Args:
            account_id: X account ID.
            embedding: Numpy array of shape (384,) with embedding vector.
            account: Account dict with description, location, etc.
        """
        text_hash = compute_text_hash(account)
        model_version = get_model_version()

        # Serialize embedding to BLOB
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
        Stale embeddings (old model version) are excluded.

        Returns:
            Tuple of (embeddings array, account_ids list).
            Array has shape (n, EMBEDDING_DIM).
            Empty cache returns shape (0, EMBEDDING_DIM) and empty list.
        """
        current_model_version = get_model_version()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT account_id, embedding FROM embeddings WHERE model_version = ?",
            (current_model_version,),
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