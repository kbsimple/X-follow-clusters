"""CLI entry point for the parse module."""

import argparse
import logging
import sys

from src.parse import parse_following_js

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse X data archive's following.js file."
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="data/following.js",
        help="Path to following.js (default: data/following.js)",
    )
    args = parser.parse_args()

    try:
        records = parse_following_js(args.file)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Parsed {len(records)} accounts")
    if records:
        print("\nFirst 5 accounts:")
        for r in records[:5]:
            print(f"  {r.account_id}  ({r.user_link})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
