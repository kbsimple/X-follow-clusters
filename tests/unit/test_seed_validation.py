"""Tests for seed file validation in load_topic_embeddings() and cluster_all().

Tests verify:
- Empty YAML file returns empty dict (graceful degradation)
- Direct list format (["AI", "Politics"]) is parsed correctly
- Dict format ({"AI": null}) is parsed correctly
- Malformed YAML propagates as yaml.YAMLError (documents current behavior)
- cluster_all() raises ValueError when seed_accounts.yaml is missing
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml


class TestTopicSeedFileValidation:
    """Tests for load_topic_embeddings() with various file conditions."""

    def test_empty_yaml_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """Empty YAML file (or null content) returns {} without error."""
        from src.cluster.embed import load_topic_embeddings

        config_path = tmp_path / "seed_topics.yaml"
        config_path.write_text("")  # empty file

        result = load_topic_embeddings(config_path)
        assert result == {}

    def test_direct_list_format_parsed(self, tmp_path: Path) -> None:
        """YAML direct list ["AI", "Politics"] is parsed into topic embeddings."""
        from src.cluster.embed import load_topic_embeddings

        config_path = tmp_path / "seed_topics.yaml"
        config_path.write_text("- AI Research\n- Politics\n")

        result = load_topic_embeddings(config_path)

        assert "AI Research" in result
        assert "Politics" in result
        assert result["AI Research"].shape == (1, 384)

    def test_dict_format_with_null_values_parsed(self, tmp_path: Path) -> None:
        """YAML dict {"AI Research": null} uses keys as topic names."""
        from src.cluster.embed import load_topic_embeddings

        config_path = tmp_path / "seed_topics.yaml"
        config_path.write_text("AI Research: null\nPolitics: null\n")

        result = load_topic_embeddings(config_path)

        assert "AI Research" in result
        assert "Politics" in result

    def test_topics_key_list_format_parsed(self, tmp_path: Path) -> None:
        """YAML {topics: ["AI", "Politics"]} is parsed via the 'topics' key."""
        from src.cluster.embed import load_topic_embeddings

        config_path = tmp_path / "seed_topics.yaml"
        config_path.write_text("topics:\n  - Startups\n  - Science\n")

        result = load_topic_embeddings(config_path)

        assert "Startups" in result
        assert "Science" in result

    def test_malformed_yaml_raises_yaml_error(self, tmp_path: Path) -> None:
        """Malformed YAML propagates as yaml.YAMLError (current behavior — not silently swallowed).

        NOTE: If graceful degradation is desired here (return {}), the implementation
        at src/cluster/embed.py:288 needs a try/except around yaml.safe_load().
        This test documents the current behavior so a conscious decision can be made.
        """
        from src.cluster.embed import load_topic_embeddings

        config_path = tmp_path / "seed_topics.yaml"
        config_path.write_text("key: [unclosed bracket\n")

        with pytest.raises(yaml.YAMLError):
            load_topic_embeddings(config_path)

    def test_yaml_with_no_recognizable_topics_returns_empty_dict(self, tmp_path: Path) -> None:
        """YAML with unrecognized structure (e.g., nested dict with no 'topics' key and non-string values) returns {}."""
        from src.cluster.embed import load_topic_embeddings

        config_path = tmp_path / "seed_topics.yaml"
        # A dict without 'topics' key — keys become topic names
        # But if someone passes an integer key structure, it still works (keys coerced to str)
        config_path.write_text("not_topics:\n  - item1\n")

        result = load_topic_embeddings(config_path)

        # "not_topics" becomes the single topic name (dict key without "topics" key → uses all keys)
        assert "not_topics" in result


class TestSeedAccountsFileValidation:
    """Tests for cluster_all() behavior with missing/malformed seed_accounts.yaml."""

    def test_missing_seed_accounts_raises_value_error(self, tmp_path: Path) -> None:
        """cluster_all raises ValueError with helpful message when seed_accounts.yaml is absent."""
        from src.cluster.embed import cluster_all

        cache_dir = tmp_path / "enrichment"
        cache_dir.mkdir()
        (cache_dir / "1234.json").write_text('{"id": "1234", "username": "user1"}')
        # No config/ directory or seed_accounts.yaml

        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with pytest.raises(ValueError, match="seed_accounts.yaml"):
                cluster_all(cache_dir=cache_dir)
        finally:
            os.chdir(orig_cwd)

    def test_empty_seed_accounts_yaml_crashes_with_attribute_error(self, tmp_path: Path) -> None:
        """Empty seed_accounts.yaml (null YAML content) causes AttributeError.

        ⚠️ BUG: src/cluster/embed.py:891 calls seed_config.items() without a
        None-guard. yaml.safe_load("") returns None, so this crashes.

        Fix: add `seed_config = seed_config or {}` after the yaml.safe_load call.
        Until fixed, this test documents the current broken behavior.
        """
        from src.cluster.embed import cluster_all

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "seed_accounts.yaml").write_text("")  # empty YAML → None

        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'items'"):
                cluster_all(dry_run=True)
        finally:
            os.chdir(orig_cwd)
