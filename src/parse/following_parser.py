"""Parser for X data archive's following.js file.

Extracts account IDs from the JavaScript-wrapped JSON format:
    window.YTD.following.part0 = [...]

Each entry has the structure:
    {"following": {"accountId": "...", "userLink": "https://twitter.com/intent/user?user_id=..."}}

Usage:
    from src.parse import parse_following_js, FollowingRecord
    records = parse_following_js("data/following.js")
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

# Pattern to strip: window.YTD.following.part0 = (with optional whitespace)
_JS_PREFIX_PATTERN = re.compile(
    r'^\s*window\.YTD\.following\.part0\s*=\s*',
    re.ASCII
)


class ParseError(Exception):
    """Raised when following.js has structural issues (not JSON, wrong type, etc)."""

    def __init__(self, message: str, file_path: str = "", line_number: int = 0):
        super().__init__(message)
        self.file_path = file_path
        self.line_number = line_number

    def __str__(self) -> str:
        return super().__str__()


@dataclass
class FollowingRecord:
    """Represents a parsed following entry from following.js.

    Attributes:
        account_id: The X account ID (numeric string).
        user_link: The X profile URL for this account.
        raw_entry: The original dict entry for debugging.
    """

    account_id: str
    user_link: str
    raw_entry: dict


def parse_following_js(path: Union[str, Path]) -> list[FollowingRecord]:
    """Parse following.js, returning list of FollowingRecord objects.

    Args:
        path: Path to the following.js file.

    Returns:
        List of FollowingRecord sorted by account_id.

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
            f"Expected: JavaScript-wrapped JSON array (window.YTD.following.part0 = [...]).",
            file_path=str(file_path),
            line_number=e.lineno,
        ) from e

    # Structural check: must be a list
    if not isinstance(data, list):
        raise ParseError(
            f"Expected JSON array in {file_path}, got {type(data).__name__}. "
            f"Check that the file is a valid following.js export.",
            file_path=str(file_path),
            line_number=0,
        )

    records: list[FollowingRecord] = []

    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            # Skip non-dict entries (malformed)
            logger.warning("Skipping entry %d: not a dict (type=%s)", index, type(entry).__name__)
            continue

        following = entry.get("following")
        if following is None:
            logger.warning("Skipping entry %d: missing 'following' key", index)
            continue

        if not isinstance(following, dict):
            logger.warning("Skipping entry %d: 'following' is not a dict", index)
            continue

        account_id = following.get("accountId")
        user_link = following.get("userLink")

        if not account_id:
            logger.warning("Skipping entry %d: missing 'accountId' in 'following'", index)
            continue

        if not isinstance(account_id, str):
            logger.warning(
                "Skipping entry %d: 'accountId' is not a string (type=%s)",
                index,
                type(account_id).__name__,
            )
            continue

        records.append(FollowingRecord(
            account_id=account_id,
            user_link=user_link or "",
            raw_entry=entry,
        ))

    # Sort by account_id
    records.sort(key=lambda r: r.account_id)

    return records
