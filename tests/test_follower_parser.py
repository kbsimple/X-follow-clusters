"""Tests for follower.js parser.

Run with: python -m pytest tests/test_follower_parser.py -v
"""

import json
import logging
import re
from pathlib import Path

import pytest

from src.parse.follower_parser import (
    FollowerRecord,
    ParseError,
    parse_follower_js,
)


# =============================================================================
# Test 1: Valid follower.js with 2 entries parses correctly
# =============================================================================
def test_valid_follower_js_parses_two_entries(tmp_path):
    """Test that a valid follower.js with 2 entries parses to 2 FollowerRecord objects."""
    content = 'window.YTD.follower.part0 = [{"accountId": "123", "username": "alice"}, {"accountId": "456", "username": "bob"}]'
    follower_file = tmp_path / "follower.js"
    follower_file.write_text(content, encoding="utf-8")

    records = parse_follower_js(follower_file)

    assert len(records) == 2
    assert records[0].account_id == "123"
    assert records[0].username == "alice"
    assert records[1].account_id == "456"
    assert records[1].username == "bob"


# =============================================================================
# Test 2: JS prefix stripping
# =============================================================================
def test_js_prefix_stripping(tmp_path):
    """Test that JS prefix 'window.YTD.follower.part0 = ' is stripped correctly."""
    content = 'window.YTD.follower.part0 = [{"accountId": "999", "username": "testuser"}]'
    follower_file = tmp_path / "follower.js"
    follower_file.write_text(content, encoding="utf-8")

    records = parse_follower_js(follower_file)

    assert len(records) == 1
    assert records[0].account_id == "999"
    assert records[0].username == "testuser"


# =============================================================================
# Test 3: Invalid JSON structure raises ParseError with file path
# =============================================================================
def test_invalid_json_structure_raises_parse_error(tmp_path):
    """Test that invalid JSON structure raises ParseError with file path in message."""
    # Not valid JSON at all - missing quotes around key
    content = 'window.YTD.follower.part0 = [{bad json}]'
    follower_file = tmp_path / "follower.js"
    follower_file.write_text(content, encoding="utf-8")

    with pytest.raises(ParseError) as exc_info:
        parse_follower_js(follower_file)

    assert "follower.js" in str(exc_info.value)
    assert exc_info.value.file_path == str(follower_file)


# =============================================================================
# Test 4: Per-entry malformed entry logs warning and skips
# =============================================================================
def test_per_entry_malformed_entry_skipped_with_warning(tmp_path, caplog):
    """Test that malformed entry logs warning and skips, returning valid entries."""
    # Second entry is missing 'username'
    content = (
        'window.YTD.follower.part0 = ['
        '{"accountId": "111", "username": "good"},'
        '{"accountId": "222"}'  # missing username
        ']'
    )
    follower_file = tmp_path / "follower.js"
    follower_file.write_text(content, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        records = parse_follower_js(follower_file)

    assert len(records) == 1
    assert records[0].account_id == "111"
    assert records[0].username == "good"

    # Check that a warning was logged about the skipped entry
    assert any("Skipping entry" in record and "1" in record for record in caplog.messages), \
        f"Expected skip warning for entry 1, got: {caplog.messages}"


# =============================================================================
# Test 5: Escaped Unicode in username handled correctly
# =============================================================================
def test_escaped_unicode_in_username(tmp_path):
    """Test that escaped Unicode in username (e.g., '\\u4e2d\\u6587') is handled correctly."""
    # "\u4e2d\u6587" is Chinese characters "中文"
    content = r'window.YTD.follower.part0 = [{"accountId": "789", "username": "\u4e2d\u6587"}]'
    follower_file = tmp_path / "follower.js"
    follower_file.write_text(content, encoding="utf-8")

    records = parse_follower_js(follower_file)

    assert len(records) == 1
    assert records[0].account_id == "789"
    assert records[0].username == "中文"


# =============================================================================
# Test 6: Empty array returns empty list (not an error)
# =============================================================================
def test_empty_array_returns_empty_list(tmp_path):
    """Test that empty array returns empty list, not an error."""
    content = 'window.YTD.follower.part0 = []'
    follower_file = tmp_path / "follower.js"
    follower_file.write_text(content, encoding="utf-8")

    records = parse_follower_js(follower_file)

    assert records == []


# =============================================================================
# Test 7: Entry with extra fields is accepted (future-proofing)
# =============================================================================
def test_entry_with_extra_fields_accepted(tmp_path):
    """Test that entries with extra fields are accepted (future-proofing)."""
    content = (
        'window.YTD.follower.part0 = [{'
        '"accountId": "555", '
        '"username": "extra", '
        '"bio": "This is a bio", '
        '"followers": 100, '
        '"joined": "2020-01-01"'
        '}]'
    )
    follower_file = tmp_path / "follower.js"
    follower_file.write_text(content, encoding="utf-8")

    records = parse_follower_js(follower_file)

    assert len(records) == 1
    assert records[0].account_id == "555"
    assert records[0].username == "extra"


# =============================================================================
# Additional edge case: renamed/deleted account (missing accountId)
# =============================================================================
def test_renamed_deleted_account_missing_account_id_skipped(tmp_path, caplog):
    """Test that entry missing accountId is logged and skipped (renamed/deleted account)."""
    content = (
        'window.YTD.follower.part0 = ['
        '{"accountId": "111", "username": "good"},'
        '{"username": "orphaned"}'  # missing accountId
        ']'
    )
    follower_file = tmp_path / "follower.js"
    follower_file.write_text(content, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        records = parse_follower_js(follower_file)

    assert len(records) == 1
    assert records[0].account_id == "111"


# =============================================================================
# Edge case: trailing semicolon
# =============================================================================
def test_trailing_semicolon_stripped(tmp_path):
    """Test that trailing semicolon after JSON array is stripped."""
    content = 'window.YTD.follower.part0 = [{"accountId": "123", "username": "alice"}];'
    follower_file = tmp_path / "follower.js"
    follower_file.write_text(content, encoding="utf-8")

    records = parse_follower_js(follower_file)

    assert len(records) == 1
    assert records[0].account_id == "123"
    assert records[0].username == "alice"


# =============================================================================
# Edge case: whitespace before JS prefix
# =============================================================================
def test_whitespace_before_js_prefix(tmp_path):
    """Test that whitespace before JS prefix is handled."""
    content = '   window.YTD.follower.part0 = [{"accountId": "123", "username": "alice"}]'
    follower_file = tmp_path / "follower.js"
    follower_file.write_text(content, encoding="utf-8")

    records = parse_follower_js(follower_file)

    assert len(records) == 1
    assert records[0].account_id == "123"
    assert records[0].username == "alice"


# =============================================================================
# Edge case: result is not a list (structural error)
# =============================================================================
def test_result_not_a_list_raises_parse_error(tmp_path):
    """Test that if stripped content parses to non-list, ParseError is raised."""
    # Even though this is valid JSON, it's not a list - structural error
    content = 'window.YTD.follower.part0 = {"accountId": "123", "username": "alice"}'
    follower_file = tmp_path / "follower.js"
    follower_file.write_text(content, encoding="utf-8")

    with pytest.raises(ParseError) as exc_info:
        parse_follower_js(follower_file)

    assert "follower.js" in str(exc_info.value)
    assert exc_info.value.file_path == str(follower_file)
