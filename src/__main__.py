"""X Following Organizer — top-level entry point.

Run with: python -m src

Orchestrates the full pipeline. Use --help to see available phases.
"""

from __future__ import annotations

import argparse
import sys

from src.auth import ensure_authenticated


def main() -> int:
    parser = argparse.ArgumentParser(description="X Following Organizer")
    parser.add_argument(
        "--auth-only",
        action="store_true",
        help="Run only the OAuth 2.0 authorization flow and exit",
    )
    args = parser.parse_args()

    if args.auth_only:
        auth = ensure_authenticated()
        print(f"Authenticated as: {auth.client_id}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())