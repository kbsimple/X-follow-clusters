"""Unit tests for review registry module (Phase 5 plan success criteria).

Tests cover:
- load_registry() returns empty ApprovalRegistry when file is missing
- save_registry() + load_registry() round-trip preserves data
- is_new_approval() returns True for cluster not yet approved
- is_new_approval() returns False for already-approved cluster
- rounds_completed defaults to 0 on fresh registry
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.review.registry import (
    ApprovalRegistry,
    is_new_approval,
    load_registry,
    save_registry,
)


class TestLoadRegistry:
    """Tests for load_registry()."""

    def test_returns_empty_registry_when_file_missing(self, tmp_path: Path) -> None:
        """load_registry returns a fresh ApprovalRegistry when the file does not exist."""
        path = tmp_path / "approved.json"
        result = load_registry(path)

        assert isinstance(result, ApprovalRegistry)
        assert result.rounds_completed == 0
        assert result.clusters["approved"] == []
        assert result.clusters["deferred"] == []
        assert result.clusters["rejected"] == []

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """save_registry then load_registry preserves all fields."""
        path = tmp_path / "approved.json"
        reg = ApprovalRegistry(
            version=1,
            rounds_completed=3,
            automation_enabled=True,
        )
        reg.clusters["approved"].append({
            "cluster_id": 42,
            "cluster_name": "AI Researchers",
            "size": 10,
        })

        save_registry(reg, path)
        loaded = load_registry(path)

        assert loaded.rounds_completed == 3
        assert loaded.automation_enabled is True
        assert len(loaded.clusters["approved"]) == 1
        assert loaded.clusters["approved"][0]["cluster_id"] == 42

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        """save_registry creates parent directories if they don't exist."""
        path = tmp_path / "nested" / "deep" / "approved.json"
        reg = ApprovalRegistry()

        save_registry(reg, path)

        assert path.exists()


class TestIsNewApproval:
    """Tests for is_new_approval() — rounds_completed gating."""

    def test_returns_true_for_new_cluster(self) -> None:
        """is_new_approval returns True when cluster_id has never been approved."""
        reg = ApprovalRegistry()
        # No approvals yet
        assert is_new_approval(reg, cluster_id=1) is True

    def test_returns_false_for_already_approved_cluster(self) -> None:
        """is_new_approval returns False when cluster_id is already approved."""
        reg = ApprovalRegistry()
        reg.clusters["approved"].append({
            "cluster_id": 5,
            "cluster_name": "Existing",
            "size": 8,
        })

        assert is_new_approval(reg, cluster_id=5) is False

    def test_different_cluster_ids_are_independent(self) -> None:
        """is_new_approval only matches exact cluster_id, not others."""
        reg = ApprovalRegistry()
        reg.clusters["approved"].append({"cluster_id": 1, "cluster_name": "A", "size": 5})

        assert is_new_approval(reg, cluster_id=2) is True
        assert is_new_approval(reg, cluster_id=1) is False


class TestRoundsCompleted:
    """Tests for rounds_completed field on ApprovalRegistry."""

    def test_rounds_completed_defaults_to_zero(self) -> None:
        """Fresh ApprovalRegistry starts with rounds_completed = 0."""
        reg = ApprovalRegistry()
        assert reg.rounds_completed == 0

    def test_rounds_completed_persists_through_save_load(self, tmp_path: Path) -> None:
        """rounds_completed is preserved after save/load cycle."""
        path = tmp_path / "approved.json"
        reg = ApprovalRegistry(rounds_completed=7)

        save_registry(reg, path)
        loaded = load_registry(path)

        assert loaded.rounds_completed == 7
