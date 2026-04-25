"""Tests for EmbeddingCache class with SQLite storage.

These tests verify:
1. EmbeddingCache() creates database file at specified path with proper schema
2. EmbeddingCache() creates table with account_id TEXT PRIMARY KEY column
3. EmbeddingCache() creates index on model_version column
4. get_cached_embedding() returns None for non-existent account
5. save_embedding() persists embedding and metadata
6. get_cached_embedding() returns embedding after save
7. load_all_embeddings() returns numpy array with correct shape (n, 384)
8. Model version invalidation works correctly
9. Text hash invalidation works correctly
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.cluster.embedding_cache import (
    EMBEDDING_DIM,
    EmbeddingCache,
    compute_text_hash,
    get_model_version,
)


# Sample account matching data/enrichment structure
SAMPLE_ACCOUNT: dict[str, Any] = {
    "id": "12345",
    "username": "testuser",
    "description": "AI researcher",
    "location": "San Francisco",
}

SAMPLE_ACCOUNT_2: dict[str, Any] = {
    "id": "67890",
    "username": "otheruser",
    "description": "Software engineer",
    "location": "New York",
}

# Sample embedding (384-dimensional)
SAMPLE_EMBEDDING = np.random.randn(384).astype(np.float32)
SAMPLE_EMBEDDING_2 = np.random.randn(384).astype(np.float32)


class TestEmbeddingCacheInit:
    """Test EmbeddingCache initialization and schema creation."""

    def test_init_creates_database_file(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Test that EmbeddingCache instantiation creates database file."""
        db_path = temp_embedding_cache.db_path
        assert db_path.exists()
        assert db_path.is_file()

    def test_init_creates_schema_with_text_account_id(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Test that account_id column is TEXT type PRIMARY KEY."""
        conn = sqlite3.connect(temp_embedding_cache.db_path)
        cursor = conn.cursor()

        # Query table info to get column types
        cursor.execute("PRAGMA table_info(embeddings)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        assert "account_id" in columns
        assert columns["account_id"] == "TEXT"

    def test_init_creates_model_version_index(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Test that index on model_version column exists for efficient queries."""
        conn = sqlite3.connect(temp_embedding_cache.db_path)
        cursor = conn.cursor()

        # Query indexes
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='embeddings'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "idx_embeddings_model" in indexes

    def test_init_sets_wal_mode(self, temp_embedding_cache: EmbeddingCache) -> None:
        """Test that WAL mode is enabled for concurrent reads."""
        conn = sqlite3.connect(temp_embedding_cache.db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()

        assert mode.lower() == "wal"


class TestEmbeddingCacheMethods:
    """Test EmbeddingCache CRUD methods."""

    def test_get_cached_embedding_returns_none_for_missing(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Test get_cached_embedding returns None for non-existent account."""
        result = temp_embedding_cache.get_cached_embedding("nonexistent", SAMPLE_ACCOUNT)
        assert result is None

    def test_save_embedding_persists_data(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Test save_embedding persists embedding and metadata to database."""
        account_id = "12345"
        temp_embedding_cache.save_embedding(account_id, SAMPLE_EMBEDDING, SAMPLE_ACCOUNT)

        # Verify data was persisted by querying directly
        conn = sqlite3.connect(temp_embedding_cache.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT account_id, embedding, text_hash, model_version FROM embeddings WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["account_id"] == account_id
        assert row["embedding"] is not None
        assert row["text_hash"] is not None
        assert row["model_version"] is not None

    def test_get_cached_embedding_returns_after_save(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Test get_cached_embedding returns embedding after save."""
        account_id = "12345"
        temp_embedding_cache.save_embedding(account_id, SAMPLE_EMBEDDING, SAMPLE_ACCOUNT)

        result = temp_embedding_cache.get_cached_embedding(account_id, SAMPLE_ACCOUNT)

        assert result is not None
        assert result.shape == (EMBEDDING_DIM,)
        np.testing.assert_array_almost_equal(result, SAMPLE_EMBEDDING)

    def test_load_all_embeddings_returns_correct_shape(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Test load_all_embeddings returns numpy array with shape (n, 384)."""
        # Save two embeddings
        temp_embedding_cache.save_embedding("12345", SAMPLE_EMBEDDING, SAMPLE_ACCOUNT)
        temp_embedding_cache.save_embedding("67890", SAMPLE_EMBEDDING_2, SAMPLE_ACCOUNT_2)

        embeddings, account_ids = temp_embedding_cache.load_all_embeddings()

        assert embeddings.shape == (2, EMBEDDING_DIM)
        assert len(account_ids) == 2
        assert "12345" in account_ids
        assert "67890" in account_ids

    def test_load_all_embeddings_empty_cache(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Test load_all_embeddings returns empty array for empty cache."""
        embeddings, account_ids = temp_embedding_cache.load_all_embeddings()

        assert embeddings.shape == (0, EMBEDDING_DIM)
        assert account_ids == []


class TestEmbeddingCacheInvalidation:
    """Test cache invalidation via model version and text hash."""

    def test_get_cached_embedding_none_on_model_version_mismatch(
        self, temp_embedding_cache: EmbeddingCache, monkeypatch
    ) -> None:
        """Test get_cached_embedding returns None when model version changes."""
        account_id = "12345"
        temp_embedding_cache.save_embedding(account_id, SAMPLE_EMBEDDING, SAMPLE_ACCOUNT)

        # Mock a different model version
        monkeypatch.setattr(
            "src.cluster.embedding_cache.get_model_version",
            lambda: "different-model|st-1.0.0"
        )

        result = temp_embedding_cache.get_cached_embedding(account_id, SAMPLE_ACCOUNT)
        assert result is None

    def test_get_cached_embedding_none_on_text_hash_mismatch(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Test get_cached_embedding returns None when account text changes."""
        account_id = "12345"
        temp_embedding_cache.save_embedding(account_id, SAMPLE_EMBEDDING, SAMPLE_ACCOUNT)

        # Modify the account text (different description)
        modified_account = {**SAMPLE_ACCOUNT, "description": "Different bio text"}

        result = temp_embedding_cache.get_cached_embedding(account_id, modified_account)
        assert result is None

    def test_load_all_embeddings_filters_by_model_version(
        self, temp_embedding_cache: EmbeddingCache, monkeypatch
    ) -> None:
        """Test load_all_embeddings only returns embeddings with current model version."""
        # Save with current model version
        temp_embedding_cache.save_embedding("12345", SAMPLE_EMBEDDING, SAMPLE_ACCOUNT)

        # Mock a different model version and save another embedding
        monkeypatch.setattr(
            "src.cluster.embedding_cache.get_model_version",
            lambda: "old-model|st-1.0.0"
        )
        temp_embedding_cache.save_embedding("67890", SAMPLE_EMBEDDING_2, SAMPLE_ACCOUNT_2)

        # Reset to current model version
        monkeypatch.undo()

        # Should only return the first embedding (current model version)
        embeddings, account_ids = temp_embedding_cache.load_all_embeddings()

        assert embeddings.shape[0] == 1
        assert account_ids == ["12345"]


class TestHelperFunctions:
    """Test get_model_version and compute_text_hash helper functions."""

    def test_get_model_version_returns_string_with_model_name(self) -> None:
        """Test get_model_version returns string containing EMBEDDING_MODEL."""
        version = get_model_version()

        assert "sentence-transformers/all-MiniLM-L6-v2" in version

    def test_get_model_version_returns_string_with_st_prefix(self) -> None:
        """Test get_model_version returns string containing 'st-' prefix."""
        version = get_model_version()

        assert "st-" in version

    def test_compute_text_hash_returns_64_char_hex(self) -> None:
        """Test compute_text_hash returns 64-char hex string (SHA-256)."""
        hash_result = compute_text_hash(SAMPLE_ACCOUNT)

        assert len(hash_result) == 64
        # Verify it's a valid hex string
        int(hash_result, 16)  # Raises ValueError if not hex

    def test_compute_text_hash_same_for_same_text(self) -> None:
        """Test compute_text_hash returns same hash for same account text."""
        hash1 = compute_text_hash(SAMPLE_ACCOUNT)
        hash2 = compute_text_hash(SAMPLE_ACCOUNT)

        assert hash1 == hash2

    def test_compute_text_hash_different_for_different_text(self) -> None:
        """Test compute_text_hash returns different hash for different text."""
        hash1 = compute_text_hash(SAMPLE_ACCOUNT)
        hash2 = compute_text_hash(SAMPLE_ACCOUNT_2)

        assert hash1 != hash2


class TestEmbeddingCacheIntegration:
    """Integration tests for embed_accounts() with EmbeddingCache.

    These tests verify:
    1. First run computes and caches all embeddings
    2. Second run loads all embeddings from cache (no model call)
    3. Model version change causes re-computation
    4. Text change causes re-computation for that account only
    5. New account added causes computation only for new account
    """

    @staticmethod
    def _make_test_accounts(count: int, start_id: int = 1) -> list[dict]:
        """Create test accounts with unique IDs and descriptions.

        MIN_TEXT_ACCOUNTS is 10, so tests need at least 10 accounts.
        """
        return [
            {
                "id": f"user_{start_id + i}",
                "username": f"user{start_id + i}",
                "description": f"Test description {i} for embedding",
            }
            for i in range(count)
        ]

    def test_first_run_computes_and_caches_all(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """First run: no cache -> compute all embeddings -> save to cache."""
        from src.cluster.embed import embed_accounts

        accounts = self._make_test_accounts(12)

        embeddings, valid = embed_accounts(accounts, embedding_cache=temp_embedding_cache)

        assert len(valid) == 12
        assert embeddings.shape == (12, 384)

        # Verify saved to cache
        cached = temp_embedding_cache.load_all_embeddings()
        assert cached[0].shape[0] == 12

    def test_second_run_loads_from_cache(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Second run: cache exists -> load from cache, no re-computation."""
        from src.cluster.embed import embed_accounts
        from unittest.mock import patch

        accounts = self._make_test_accounts(10)

        # First run - compute
        embeddings_1, _ = embed_accounts(accounts, embedding_cache=temp_embedding_cache)

        # Second run - should load from cache (no model call)
        with patch("src.cluster.embed.SentenceTransformer") as mock_model:
            embeddings_2, _ = embed_accounts(accounts, embedding_cache=temp_embedding_cache)
            # Model should not be instantiated
            mock_model.assert_not_called()

        # Same embeddings
        np.testing.assert_array_almost_equal(embeddings_1, embeddings_2)

    def test_model_version_change_invalidates_cache(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Model version change causes cache invalidation."""
        from src.cluster.embed import embed_accounts

        accounts = self._make_test_accounts(10)

        # First run - save with current model version
        embeddings_1, _ = embed_accounts(accounts, embedding_cache=temp_embedding_cache)

        # Manually update model_version in cache to simulate model change
        conn = sqlite3.connect(temp_embedding_cache.db_path)
        conn.execute(
            "UPDATE embeddings SET model_version = ?",
            ("old-model-version",),
        )
        conn.commit()
        conn.close()

        # Second run - should recompute due to model version mismatch
        embeddings_2, _ = embed_accounts(accounts, embedding_cache=temp_embedding_cache)

        # Should have recomputed (can't compare values, just verify cache updated)
        cached = temp_embedding_cache.load_all_embeddings()
        assert cached[0].shape[0] == 10

    def test_text_change_causes_recomputation(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Text change (bio/location) causes re-computation for that account."""
        from src.cluster.embed import embed_accounts

        accounts = self._make_test_accounts(10)

        # First run
        embeddings_1, _ = embed_accounts(accounts, embedding_cache=temp_embedding_cache)

        # Change the first account's text
        accounts[0]["description"] = "Updated bio with completely new content for testing"

        # Second run - should recompute due to text hash mismatch
        embeddings_2, _ = embed_accounts(accounts, embedding_cache=temp_embedding_cache)

        # First embedding should be different (text changed)
        assert not np.allclose(embeddings_1[0], embeddings_2[0])

    def test_new_account_added_computes_only_new(
        self, temp_embedding_cache: EmbeddingCache
    ) -> None:
        """Adding new account only computes embedding for new account."""
        from src.cluster.embed import embed_accounts
        from unittest.mock import patch, MagicMock

        # First run with 10 accounts
        accounts_1 = self._make_test_accounts(10)
        embeddings_1, _ = embed_accounts(accounts_1, embedding_cache=temp_embedding_cache)

        # Second run with 11 accounts (10 cached, 1 new)
        accounts_2 = accounts_1 + self._make_test_accounts(1, start_id=100)

        # Track model encode calls
        with patch("src.cluster.embed.SentenceTransformer") as mock_model_class:
            mock_model = MagicMock()
            mock_model_class.return_value = mock_model
            mock_model.encode.return_value = np.random.randn(1, 384).astype(np.float32)

            embeddings_2, _ = embed_accounts(accounts_2, embedding_cache=temp_embedding_cache)

            # Model encode should only be called once (for the new account)
            # Note: encode is called with a list, so we check the batch size
            if mock_model.encode.called:
                call_args = mock_model.encode.call_args
                assert len(call_args[0][0]) == 1  # Only 1 text to encode

        assert embeddings_2.shape[0] == 11