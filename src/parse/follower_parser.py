"""Parser for X data archive's follower.js file.

Extracts account IDs and usernames from the JavaScript-wrapped JSON format:
    window.YTD.follower.part0 = [...]

Usage:
    from src.parse import parse_follower_js, FollowerRecord
    records = parse_follower_js("data/follower.js")
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

# Pattern to strip: window.YTD.follower.part0 = (with optional whitespace)
_JS_PREFIX_PATTERN = re.compile(
    r'^\s*window\.YTD\.follower\.part0\s*=\s*',
    re.ASCII
)


class ParseError(Exception):
    """Raised when follower.js has structural issues (not JSON, wrong type, etc)."""

    def __init__(self, message: str, file_path: str = "", line_number: int = 0):
        super().__init__(message)
        self.file_path = file_path
        self.line_number = line_number

    def __str__(self) -> str:
        return super().__str__()


@dataclass
class FollowerRecord:
    """Represents a parsed follower entry from follower.js.

    Attributes:
        account_id: The X account ID (numeric string).
        username: The X username (handle, without @).
        raw_entry: The original dict entry for debugging.
    """

    account_id: str
    username: str
    raw_entry: dict


def parse_follower_js(path: Union[str, Path]) -> list[FollowerRecord]:
    """Parse follower.js, returning list of FollowerRecord objects.

    Args:
        path: Path to the follower.js file.

    Returns:
        List of FollowerRecord sorted by username (case-insensitive).

    Raises:
        ParseError: If the file structure is invalid (not JSON, not a list).
    """
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")

    # Strip the JS prefix
    stripped = _JS_PREFIX_PATTERN.sub("", content)

    # Strip trailing semicolon if present
    stripped = stripped.rstrip().rstrip(";")

    # Attempt to parse as JSON
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ParseError(
            f"Invalid JSON in {file_path}: {e.msg} at line {e.lineno}, column {e.colno}. "
            f"Expected: JavaScript-wrapped JSON array (window.YTD.follower.part0 = [...]).",
            file_path=str(file_path),
            line_number=e.lineno,
        ) from e

    # Structural check: must be a list
    if not isinstance(data, list):
        raise ParseError(
            f"Expected JSON array in {file_path}, got {type(data).__name__}. "
            f"Check that the file is a valid follower.js export.",
            file_path=str(file_path),
            line_number=0,
        )

    records: list[FollowerRecord] = []

    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            # Skip non-dict entries (malformed)
            logger.warning("Skipping entry %d: not a dict (type=%s)", index, type(entry).__name__)
            continue

        try:
            account_id = entry["accountId"]
            username = entry["username"]
        except KeyError as e:
            # Missing required field - likely a renamed/deleted account
            logger.warning("Skipping entry %d: missing field '%s'", index, e.args[0])
            continue

        # Validate types (accountId and username should be strings)
        if not isinstance(account_id, str) or not isinstance(username, str):
            logger.warning(
                "Skipping entry %d: accountId or username not a string "
                "(accountId=%s type=%s, username=%s type=%s)",
                index,
                repr(account_id),
                type(account_id).__name__,
                repr(username),
                type(username).__name__,
            )
            continue

        records.append(FollowerRecord(
            account_id=account_id,
            username=username,
            raw_entry=entry,
        ))

    # Sort by username case-insensitive
    records.sort(key=lambda r: r.username.lower())

    return records
