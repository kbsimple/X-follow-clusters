"""Shared test fixtures for Phase 6 tests.

Provides mock_auth, mock_registry, mock_tweepy_client,
temp_enrichment_cache, and temp_export_dir fixtures.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.auth.x_auth import XAuth
from src.review.registry import ApprovalRegistry


@pytest.fixture
def mock_auth() -> XAuth:
    """Return an XAuth with test credential strings."""
    return XAuth(
        api_key="test_api_key",
        api_secret="test_api_secret",
        access_token="test_access_token",
        access_token_secret="test_access_token_secret",
        bearer_token="test_bearer_token",
    )


@pytest.fixture
def mock_registry() -> ApprovalRegistry:
    """Return an ApprovalRegistry with sample approved and deferred clusters."""
    approved_clusters = [
        {
            "cluster_id": 1,
            "cluster_name": "Test Cluster 1",
            "size": 10,
            "silhouette": 0.65,
            "members": [
                {"username": f"user{i}", "cluster_id": 1}
                for i in range(10)
            ],
            "round_approved": 1,
        },
        {
            "cluster_id": 2,
            "cluster_name": "Test Cluster 2",
            "size": 15,
            "silhouette": 0.72,
            "members": [
                {"username": f"member{i}", "cluster_id": 2}
                for i in range(15)
            ],
            "round_approved": 1,
        },
    ]
    deferred_clusters = [
        {
            "cluster_id": 3,
            "cluster_name": "Deferred Cluster",
            "size": 7,
            "silhouette": 0.45,
            "members": [
                {"username": f"deferred_user{i}", "cluster_id": 3}
                for i in range(7)
            ],
        },
    ]
    return ApprovalRegistry(
        version=1,
        automation_enabled=False,
        clusters={
            "approved": approved_clusters,
            "deferred": deferred_clusters,
            "rejected": [],
        },
    )


class MockListData:
    """Mock list data object."""

    def __init__(self, name: str, id: str = "123"):
        self.id = id
        self.name = name
        self.description = f"Description for {name}"


class MockOwnedListsResponse:
    """Mock tweepy Response for get_owned_lists."""

    def __init__(self, data: list[MockListData] | None = None):
        self.data = data or []


class MockCreateListResponse:
    """Mock tweepy Response for create_list."""

    def __init__(self, name: str, id: str = "456"):
        self.data = {"id": id, "name": name}


class MockAddMembersResponse:
    """Mock tweepy Response for add_list_members."""

    def __init__(self):
        self.data = {}


@pytest.fixture
def mock_tweepy_client() -> MagicMock:
    """Return a mock tweepy Client with create_list, add_list_members, get_owned_lists."""
    client = MagicMock()

    # Default: no existing lists
    client.get_owned_lists.return_value = MockOwnedListsResponse([])

    # Default: successful list creation
    client.create_list.return_value = MockCreateListResponse(name="Test List")

    # Default: successful member add
    client.add_list_members.return_value = MockAddMembersResponse()

    return client


@pytest.fixture
def temp_enrichment_cache(tmp_path: Path) -> Path:
    """Create a temp enrichment cache directory with sample JSON files."""
    cache_dir = tmp_path / "enrichment"
    cache_dir.mkdir()

    # Create sample enrichment files
    for i in range(5):
        data = {
            "id": f"{1000 + i}",
            "username": f"testuser{i}",
            "description": f"Test bio for user {i}",
            "location": f"City {i}",
            "followers_count": 100 * i,
            "following_count": 50 * i,
            "verified": i % 2 == 0,
            "protected": False,
            "pinned_tweet_text": f"Pinned tweet {i}",
            "cluster_id": 1,
            "cluster_name": "Test Cluster 1",
            "silhouette_score": 0.65,
            "is_seed_category": True,
            "central_member_usernames": ["user0", "user1"],
        }
        (cache_dir / f"{1000 + i}.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    # Create special files that should be skipped
    (cache_dir / "suspended.json").write_text(
        json.dumps({"id": "999", "username": "suspended"}), encoding="utf-8"
    )
    (cache_dir / "protected.json").write_text(
        json.dumps({"id": "998", "username": "protected"}), encoding="utf-8"
    )
    (cache_dir / "errors.json").write_text(
        json.dumps({"errors": []}), encoding="utf-8"
    )

    return cache_dir


@pytest.fixture
def temp_export_dir(tmp_path: Path) -> Path:
    """Create a temp data/export directory."""
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    return export_dir
