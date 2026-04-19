"""Unit tests for clustering module (Phase 4 plan success criteria).

Tests cover:
- compute_clusters() accepts algorithm parameter ("kmeans" or "hdbscan")
- compute_clusters() raises ValueError for unknown algorithm
- cluster_all() raises ValueError when seed config missing
- cluster_all() raises ValueError when no enrichment files found
- cluster_all(dry_run=True) returns ClusterResult with required fields
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


class TestComputeClusters:
    """Tests for compute_clusters() algorithm parameter (CLUSTER-02)."""

    def _make_embeddings(self, n: int = 30) -> np.ndarray:
        rng = np.random.default_rng(42)
        return rng.standard_normal((n, 384)).astype(np.float32)

    def _make_seeds(self) -> dict[str, np.ndarray]:
        rng = np.random.default_rng(0)
        return {
            "AI": rng.standard_normal((2, 384)).astype(np.float32),
            "Politics": rng.standard_normal((2, 384)).astype(np.float32),
        }

    def test_unknown_algorithm_raises_value_error(self) -> None:
        """compute_clusters raises ValueError for an unknown algorithm string."""
        from src.cluster.embed import compute_clusters

        embeddings = self._make_embeddings()
        seeds = self._make_seeds()

        with pytest.raises(ValueError, match="Unknown algorithm"):
            compute_clusters(embeddings, seeds, algorithm="invalid_algo")

    def test_kmeans_algorithm_returns_four_tuple(self) -> None:
        """compute_clusters with algorithm='kmeans' returns (labels, seed_centroids, final_centroids, category_names)."""
        from src.cluster.embed import compute_clusters

        embeddings = self._make_embeddings(30)
        seeds = self._make_seeds()

        result = compute_clusters(embeddings, seeds, algorithm="kmeans")

        assert isinstance(result, tuple)
        assert len(result) == 4
        labels, seed_centroids, final_centroids, category_names = result

        assert isinstance(labels, np.ndarray)
        assert len(labels) == 30
        assert isinstance(category_names, list)


class TestClusterAll:
    """Tests for cluster_all() pipeline (Phase 4 success criteria)."""

    def test_seed_config_missing_raises_value_error(self, tmp_path: Path) -> None:
        """cluster_all raises ValueError when config/seed_accounts.yaml does not exist."""
        from src.cluster.embed import cluster_all

        cache_dir = tmp_path / "enrichment"
        cache_dir.mkdir()
        # Create a dummy enrichment file so the enrichment check passes
        (cache_dir / "1234.json").write_text('{"id": "1234", "username": "user1"}')

        # No seed_accounts.yaml in the working directory — patch Path to use tmp_path
        import unittest.mock as mock
        with mock.patch("src.cluster.embed.Path") as mock_path_cls:
            # Make only seed_config_path.exists() return False
            real_path = Path
            def fake_path(*args):
                p = real_path(*args)
                return p
            mock_path_cls.side_effect = fake_path

            # Use a cache_dir that exists but no seed config
            # Easier: patch seed_config_path.exists() directly
            pass

        # Simpler approach: use monkeypatching via tmp_path as cwd
        import os
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # No config/seed_accounts.yaml in tmp_path
            with pytest.raises(ValueError, match="seed_accounts.yaml"):
                cluster_all(cache_dir=cache_dir)
        finally:
            os.chdir(orig_cwd)

    def test_no_enrichment_files_raises_value_error(self, tmp_path: Path) -> None:
        """cluster_all raises ValueError when cache_dir has no .json enrichment files."""
        from src.cluster.embed import cluster_all

        cache_dir = tmp_path / "enrichment"
        cache_dir.mkdir()
        # Create seed config so that check passes
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "seed_accounts.yaml").write_text("AI:\n  examples: [user1]\n")

        import os
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with pytest.raises(ValueError, match="No enrichment files"):
                cluster_all(cache_dir=cache_dir)
        finally:
            os.chdir(orig_cwd)

    def test_dry_run_returns_cluster_result(self, tmp_path: Path) -> None:
        """cluster_all(dry_run=True) returns ClusterResult without touching live data."""
        from src.cluster.embed import cluster_all, ClusterResult

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "seed_accounts.yaml").write_text("AI:\n  examples: [user1]\n")

        import os
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = cluster_all(dry_run=True)
        finally:
            os.chdir(orig_cwd)

        assert isinstance(result, ClusterResult)

    def test_cluster_result_has_expected_fields(self, tmp_path: Path) -> None:
        """ClusterResult from dry_run has n_clusters, silhouette_by_cluster, size_histogram."""
        from src.cluster.embed import cluster_all

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "seed_accounts.yaml").write_text("AI:\n  examples: [user1]\n")

        import os
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = cluster_all(dry_run=True)
        finally:
            os.chdir(orig_cwd)

        assert hasattr(result, "n_clusters")
        assert hasattr(result, "silhouette_by_cluster")
        assert hasattr(result, "size_histogram")
        assert hasattr(result, "total_accounts")
        assert isinstance(result.silhouette_by_cluster, dict)
        assert isinstance(result.size_histogram, dict)
