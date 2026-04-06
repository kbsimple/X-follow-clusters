"""Unit tests for src.list.exporter module.

Tests cover EXPORT-01 and EXPORT-02:
- export_clusters_to_csv: creates CSV with approved and deferred rows
- export_clusters_to_csv: creates empty CSV with headers when no clusters
- export_followers_to_parquet: creates valid Parquet with correct columns
- export_followers_to_parquet: skips suspended/protected/errors files
- export_all: runs both and returns paths and row counts
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.list.exporter import (
    export_clusters_to_csv,
    export_followers_to_parquet,
    export_all,
)


class TestExportClustersToCsv:
    """Tests for export_clusters_to_csv function."""

    def test_approved_and_deferred(
        self,
        mock_registry,
        tmp_path,
    ) -> None:
        """Creates CSV with both approved and deferred rows."""
        csv_path = tmp_path / "clusters.csv"

        with patch("src.list.exporter.EXPORT_DIR", tmp_path), \
             patch("src.list.exporter.CLUSTERS_CSV", csv_path), \
             patch("src.list.exporter.load_registry", return_value=mock_registry):

            path = export_clusters_to_csv()

        assert csv_path.exists()

        df = pd.read_csv(csv_path)
        # 2 approved + 1 deferred = 3 rows
        assert len(df) == 3
        assert "cluster_id" in df.columns
        assert "cluster_name" in df.columns
        assert "status" in df.columns
        assert "size" in df.columns
        assert "member_handles" in df.columns

        # Check status values
        approved_rows = df[df["status"] == "approved"]
        deferred_rows = df[df["status"] == "deferred"]
        assert len(approved_rows) == 2
        assert len(deferred_rows) == 1

    def test_empty_clusters(self, tmp_path) -> None:
        """Creates empty CSV with headers when no clusters exist."""
        from src.review.registry import ApprovalRegistry

        csv_path = tmp_path / "clusters.csv"
        empty_reg = ApprovalRegistry(
            clusters={"approved": [], "deferred": [], "rejected": []}
        )

        with patch("src.list.exporter.EXPORT_DIR", tmp_path), \
             patch("src.list.exporter.CLUSTERS_CSV", csv_path), \
             patch("src.list.exporter.load_registry", return_value=empty_reg):

            export_clusters_to_csv()

        assert csv_path.exists()
        df = pd.read_csv(csv_path)
        assert len(df) == 0
        # Headers still present
        assert list(df.columns) == [
            "cluster_id",
            "cluster_name",
            "status",
            "size",
            "silhouette",
            "member_handles",
            "central_member_usernames",
        ]


class TestExportFollowersToParquet:
    """Tests for export_followers_to_parquet function."""

    def test_schema(self, temp_enrichment_cache: Path, tmp_path: Path) -> None:
        """Creates valid Parquet with correct columns from enrichment cache."""
        parquet_path = tmp_path / "followers.parquet"

        with patch("src.list.exporter.EXPORT_DIR", tmp_path), \
             patch("src.list.exporter.FOLLOWERS_PARQUET", parquet_path), \
             patch("src.list.exporter.ENRICHMENT_DIR", temp_enrichment_cache):

            exp_module = __import__("src.list.exporter", fromlist=["export_followers_to_parquet"])
            # Re-call with patched module-level vars
            # Since the function uses ENRICHMENT_DIR at call time, the patch works
            from src.list.exporter import export_followers_to_parquet as func
            func()

        assert parquet_path.exists()
        df = pd.read_parquet(parquet_path)
        # 5 regular files (excluding 3 special files: suspended, protected, errors)
        assert len(df) == 5
        assert "username" in df.columns
        assert "cluster_id" in df.columns
        assert "cluster_name" in df.columns
        assert "silhouette_score" in df.columns

    def test_skips_special_files(self, temp_enrichment_cache: Path, tmp_path: Path) -> None:
        """Skips suspended.json, protected.json, errors.json files."""
        parquet_path = tmp_path / "followers.parquet"

        with patch("src.list.exporter.EXPORT_DIR", tmp_path), \
             patch("src.list.exporter.FOLLOWERS_PARQUET", parquet_path), \
             patch("src.list.exporter.ENRICHMENT_DIR", temp_enrichment_cache):

            from src.list.exporter import export_followers_to_parquet as func
            func()

        df = pd.read_parquet(parquet_path)
        # Should not contain entries from suspended, protected, or errors files
        usernames = df["username"].tolist()
        assert "suspended" not in usernames
        assert "protected" not in usernames


class TestExportAll:
    """Tests for export_all function."""

    def test_runs_both(
        self,
        mock_registry,
        temp_enrichment_cache: Path,
        tmp_path: Path,
    ) -> None:
        """export_all() calls both functions and returns both paths and row counts."""
        csv_path = tmp_path / "clusters.csv"
        parquet_path = tmp_path / "followers.parquet"

        with patch("src.list.exporter.EXPORT_DIR", tmp_path), \
             patch("src.list.exporter.CLUSTERS_CSV", csv_path), \
             patch("src.list.exporter.FOLLOWERS_PARQUET", parquet_path), \
             patch("src.list.exporter.ENRICHMENT_DIR", temp_enrichment_cache), \
             patch("src.list.exporter.load_registry", return_value=mock_registry):

            result = export_all()

        assert "clusters_csv" in result
        assert "followers_parquet" in result
        assert "clusters_rows" in result
        assert "followers_rows" in result
        assert result["clusters_rows"] == 3  # 2 approved + 1 deferred
        assert result["followers_rows"] == 5  # 5 regular files
