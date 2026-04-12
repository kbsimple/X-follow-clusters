"""X Following Organizer — top-level entry point.

Run with: python -m src

Orchestrates the full pipeline. Use --help to see available phases.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from src.auth import ensure_authenticated


def _load_env() -> None:
    """Load .env file from project root into environment variables.

    Ignores lines starting with # and empty lines.
    Does not override already-set environment variables.
    """
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


def _underscore_to_hyphen(args: list[str]) -> list[str]:
    """Allow both --auth-only and --auth_only argument forms."""
    return [a.replace("--auth_only", "--auth-only") for a in args]


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description="X Following Organizer")
    parser.add_argument(
        "--auth-only",
        action="store_true",
        help="Run only the OAuth 2.0 authorization flow and exit",
    )
    args = parser.parse_args(args=_underscore_to_hyphen(sys.argv[1:]))

    if args.auth_only:
        auth = ensure_authenticated()
        print(f"Authenticated as: {auth.client_id}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())