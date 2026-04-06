"""Unit tests for src.list.creator module.

Tests cover LIST-01 through LIST-05:
- precheck_conflicts: no conflicts and with conflicts
- create_list_from_cluster: successful creation
- add_members_chunked: correctly chunks 250 members into 3 batches
- list_size_validation: valid sizes, too small, too large, account limit
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.list.creator import (
    precheck_conflicts,
    create_list_from_cluster,
    add_members_chunked,
    list_size_validation,
    ListCreationError,
)


class TestPrecheckConflicts:
    """Tests for precheck_conflicts function."""

    def test_no_conflicts(
        self,
        mock_tweepy_client: MagicMock,
    ) -> None:
        """precheck_conflicts returns empty dict when no names match."""
        mock_tweepy_client.get_owned_lists.return_value.data = []
        clusters = [
            {"cluster_name": "Cluster A"},
            {"cluster_name": "Cluster B"},
        ]
        result = precheck_conflicts(mock_tweepy_client, clusters)
        assert result == {}

    def test_with_conflicts(
        self,
        mock_tweepy_client: MagicMock,
    ) -> None:
        """precheck_conflicts returns dict with conflicting names."""
        from tests.conftest import MockListData

        mock_tweepy_client.get_owned_lists.return_value.data = [
            MockListData(name="Cluster A"),
            MockListData(name="Existing List"),
        ]
        clusters = [
            {"cluster_name": "Cluster A"},
            {"cluster_name": "Cluster B"},
            {"cluster_name": "Existing List"},
        ]
        result = precheck_conflicts(mock_tweepy_client, clusters)
        assert result == {"Cluster A": "exists", "Existing List": "exists"}


class TestCreateListFromCluster:
    """Tests for create_list_from_cluster function."""

    def test_success(
        self,
        mock_tweepy_client: MagicMock,
    ) -> None:
        """create_list_from_cluster calls client.create_list with correct args."""
        from tests.conftest import MockCreateListResponse

        cluster = {
            "cluster_name": "My Cluster",
            "size": 25,
        }
        mock_tweepy_client.create_list.return_value = MockCreateListResponse(
            name="My Cluster", id="789"
        )

        list_id = create_list_from_cluster(mock_tweepy_client, cluster)

        assert list_id == "789"
        mock_tweepy_client.create_list.assert_called_once_with(
            name="My Cluster",
            description="Created by X Following Organizer - My Cluster",
            mode="private",
        )


class TestAddMembersChunked:
    """Tests for add_members_chunked function."""

    def test_chunks_250_members_into_3_batches(
        self,
        mock_tweepy_client: MagicMock,
    ) -> None:
        """add_members_chunked correctly chunks 250 members into 3 batches."""
        usernames = [f"user{i}" for i in range(250)]

        count = add_members_chunked(mock_tweepy_client, "list123", usernames)

        assert count == 250
        assert mock_tweepy_client.add_list_members.call_count == 3

    def test_chunks_100_members_into_1_batch(
        self,
        mock_tweepy_client: MagicMock,
    ) -> None:
        """100 members = exactly 1 batch."""
        usernames = [f"user{i}" for i in range(100)]
        count = add_members_chunked(mock_tweepy_client, "list123", usernames)
        assert count == 100
        assert mock_tweepy_client.add_list_members.call_count == 1

    def test_chunks_50_members_into_1_batch(
        self,
        mock_tweepy_client: MagicMock,
    ) -> None:
        """50 members = 1 batch."""
        usernames = [f"user{i}" for i in range(50)]
        count = add_members_chunked(mock_tweepy_client, "list123", usernames)
        assert count == 50
        assert mock_tweepy_client.add_list_members.call_count == 1


class TestListSizeValidation:
    """Tests for list_size_validation function."""

    def test_valid_sizes(
        self,
        mock_tweepy_client: MagicMock,
    ) -> None:
        """Clusters with size 5-50 pass validation."""
        from tests.conftest import MockOwnedListsResponse

        mock_tweepy_client.get_owned_lists.return_value = MockOwnedListsResponse(
            data=[]
        )
        clusters = [
            {"cluster_name": "Small", "size": 5},
            {"cluster_name": "Medium", "size": 25},
            {"cluster_name": "Large", "size": 50},
        ]
        result = list_size_validation(mock_tweepy_client, clusters)
        assert len(result) == 3

    def test_too_small(
        self,
        mock_tweepy_client: MagicMock,
    ) -> None:
        """Clusters with size < 5 are filtered out."""
        from tests.conftest import MockOwnedListsResponse

        mock_tweepy_client.get_owned_lists.return_value = MockOwnedListsResponse(
            data=[]
        )
        clusters = [
            {"cluster_name": "Tiny", "size": 3},
            {"cluster_name": "Valid", "size": 10},
        ]
        result = list_size_validation(mock_tweepy_client, clusters)
        assert len(result) == 1
        assert result[0]["cluster_name"] == "Valid"

    def test_too_large(
        self,
        mock_tweepy_client: MagicMock,
    ) -> None:
        """Clusters with size > 50 are filtered out."""
        from tests.conftest import MockOwnedListsResponse

        mock_tweepy_client.get_owned_lists.return_value = MockOwnedListsResponse(
            data=[]
        )
        clusters = [
            {"cluster_name": "Huge", "size": 51},
            {"cluster_name": "Valid", "size": 30},
        ]
        result = list_size_validation(mock_tweepy_client, clusters)
        assert len(result) == 1
        assert result[0]["cluster_name"] == "Valid"

    def test_account_limit(
        self,
        mock_tweepy_client: MagicMock,
    ) -> None:
        """Account with >= 1000 lists raises ListCreationError."""
        from tests.conftest import MockListData, MockOwnedListsResponse

        mock_tweepy_client.get_owned_lists.return_value = MockOwnedListsResponse(
            data=[MockListData(name=f"list{i}") for i in range(1000)]
        )
        clusters = [{"cluster_name": "Any", "size": 10}]

        with pytest.raises(ListCreationError) as exc_info:
            list_size_validation(mock_tweepy_client, clusters)
        assert "1,000" in str(exc_info.value.message)
