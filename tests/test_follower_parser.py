"""Tests for following.js parser.

Run with: python -m pytest tests/test_follower_parser.py -v
"""

import json
import logging
import re
from pathlib import Path

import pytest

from src.parse.following_parser import (
    FollowingRecord,
    ParseError,
    parse_following_js,
)


# =============================================================================
# Test 1: Valid following.js with 2 entries parses correctly
# =============================================================================
def test_valid_following_js_parses_two_entries(tmp_path):
    """Test that a valid following.js with 2 entries parses to 2 FollowingRecord objects."""
    content = (
        'window.YTD.following.part0 = ['
        '{"following": {"accountId": "123", "userLink": "https://twitter.com/intent/user?user_id=123"}},'
        '{"following": {"accountId": "456", "userLink": "https://twitter.com/intent/user?user_id=456"}}'
        ']'
    )
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    records = parse_following_js(following_file)

    assert len(records) == 2
    assert records[0].account_id == "123"
    assert records[1].account_id == "456"


# =============================================================================
# Test 2: JS prefix stripping
# =============================================================================
def test_js_prefix_stripping(tmp_path):
    """Test that JS prefix 'window.YTD.following.part0 = ' is stripped correctly."""
    content = (
        'window.YTD.following.part0 = ['
        '{"following": {"accountId": "999", "userLink": "https://twitter.com/intent/user?user_id=999"}}'
        ']'
    )
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    records = parse_following_js(following_file)

    assert len(records) == 1
    assert records[0].account_id == "999"
    assert records[0].user_link == "https://twitter.com/intent/user?user_id=999"


# =============================================================================
# Test 3: Invalid JSON structure raises ParseError with file path
# =============================================================================
def test_invalid_json_structure_raises_parse_error(tmp_path):
    """Test that invalid JSON structure raises ParseError with file path in message."""
    content = 'window.YTD.following.part0 = [{bad json}]'
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    with pytest.raises(ParseError) as exc_info:
        parse_following_js(following_file)

    assert "following.js" in str(exc_info.value)
    assert exc_info.value.file_path == str(following_file)


# =============================================================================
# Test 4: Per-entry malformed entry logs warning and skips
# =============================================================================
def test_per_entry_malformed_entry_skipped_with_warning(tmp_path, caplog):
    """Test that malformed entry logs warning and skips, returning valid entries."""
    # Second entry is missing 'following' key entirely
    content = (
        'window.YTD.following.part0 = ['
        '{"following": {"accountId": "111", "userLink": "https://twitter.com/intent/user?user_id=111"}},'
        '{"other": {"accountId": "222"}}'
        ']'
    )
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        records = parse_following_js(following_file)

    assert len(records) == 1
    assert records[0].account_id == "111"
    assert any("Skipping entry" in msg and "1" in msg for msg in caplog.messages)


# =============================================================================
# Test 5: userLink is optional
# =============================================================================
def test_user_link_is_optional(tmp_path):
    """Test that userLink is optional — entry without it is still accepted."""
    content = (
        'window.YTD.following.part0 = ['
        '{"following": {"accountId": "222"}}'
        ']'
    )
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    records = parse_following_js(following_file)

    assert len(records) == 1
    assert records[0].account_id == "222"
    assert records[0].user_link == ""


# =============================================================================
# Test 6: Empty array returns empty list (not an error)
# =============================================================================
def test_empty_array_returns_empty_list(tmp_path):
    """Test that empty array returns empty list, not an error."""
    content = 'window.YTD.following.part0 = []'
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    records = parse_following_js(following_file)

    assert records == []


# =============================================================================
# Test 7: Entry with extra fields is accepted (future-proofing)
# =============================================================================
def test_entry_with_extra_fields_accepted(tmp_path):
    """Test that entries with extra fields are accepted (future-proofing)."""
    content = (
        'window.YTD.following.part0 = [{'
        '"following": {"accountId": "555", "userLink": "https://twitter.com/intent/user?user_id=555"}, '
        '"extraField": "ignored"'
        '}]'
    )
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    records = parse_following_js(following_file)

    assert len(records) == 1
    assert records[0].account_id == "555"


# =============================================================================
# Additional edge case: missing 'following' key
# =============================================================================
def test_missing_following_key_skipped(tmp_path, caplog):
    """Test that entry missing 'following' key is logged and skipped."""
    content = (
        'window.YTD.following.part0 = ['
        '{"following": {"accountId": "111", "userLink": "https://twitter.com/intent/user?user_id=111"}},'
        '{"other": {"accountId": "orphaned"}}'
        ']'
    )
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        records = parse_following_js(following_file)

    assert len(records) == 1
    assert records[0].account_id == "111"


# =============================================================================
# Edge case: trailing semicolon
# =============================================================================
def test_trailing_semicolon_stripped(tmp_path):
    """Test that trailing semicolon after JSON array is stripped."""
    content = (
        'window.YTD.following.part0 = ['
        '{"following": {"accountId": "123", "userLink": "https://twitter.com/intent/user?user_id=123"}}'
        '];'
    )
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    records = parse_following_js(following_file)

    assert len(records) == 1
    assert records[0].account_id == "123"


# =============================================================================
# Edge case: whitespace before JS prefix
# =============================================================================
def test_whitespace_before_js_prefix(tmp_path):
    """Test that whitespace before JS prefix is handled."""
    content = (
        '   window.YTD.following.part0 = ['
        '{"following": {"accountId": "123", "userLink": "https://twitter.com/intent/user?user_id=123"}}'
        ']'
    )
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    records = parse_following_js(following_file)

    assert len(records) == 1
    assert records[0].account_id == "123"


# =============================================================================
# Edge case: result is not a list (structural error)
# =============================================================================
def test_result_not_a_list_raises_parse_error(tmp_path):
    """Test that if stripped content parses to non-list, ParseError is raised."""
    content = (
        'window.YTD.following.part0 = '
        '{"following": {"accountId": "123", "userLink": "https://twitter.com/intent/user?user_id=123"}}'
    )
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    with pytest.raises(ParseError) as exc_info:
        parse_following_js(following_file)

    assert "following.js" in str(exc_info.value)
    assert exc_info.value.file_path == str(following_file)


# =============================================================================
# Edge case: missing accountId in following block
# =============================================================================
def test_missing_account_id_skipped(tmp_path, caplog):
    """Test that entry with missing accountId is logged and skipped."""
    content = (
        'window.YTD.following.part0 = ['
        '{"following": {"accountId": "111", "userLink": "https://twitter.com/intent/user?user_id=111"}},'
        '{"following": {"userLink": "https://twitter.com/intent/user?user_id=999"}}'
        ']'
    )
    following_file = tmp_path / "following.js"
    following_file.write_text(content, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        records = parse_following_js(following_file)

    assert len(records) == 1
    assert records[0].account_id == "111"


# =============================================================================
# Integration test: actual data/following.js file
# =============================================================================
def test_actual_following_js_file():
    """Test parsing the actual data/following.js file from X export."""
    records = parse_following_js("data/following.js")

    assert len(records) == 867
    # Verify sorted by account_id
    for i in range(len(records) - 1):
        assert records[i].account_id <= records[i+1].account_id
    # Verify all have account_id
    assert all(r.account_id for r in records)
