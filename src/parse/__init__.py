"""Parse module for X data archive files."""

from src.parse.following_parser import (
    FollowingRecord,
    ParseError,
    parse_following_js,
)

# Backward compatibility aliases
FollowerRecord = FollowingRecord
parse_follower_js = parse_following_js

__all__ = [
    "FollowingRecord",
    "FollowerRecord",  # backward compat
    "ParseError",
    "parse_following_js",
    "parse_follower_js",  # backward compat
]
