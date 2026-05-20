#!/usr/bin/env python3
"""Compatibility wrapper for platform skill mirror sync."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def add_local_package_root() -> None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "llm_wiki" / "__init__.py").exists():
            sys.path.insert(0, str(parent))
            return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync LLM Wiki platform instruction files and skill mirrors.")
    parser.add_argument("--check", action="store_true", help="Check drift only; exit non-zero on drift.")
    parser.add_argument("--kb-root", default=".", help="Knowledge-base root. Defaults to current directory.")
    parser.add_argument("--platform", default="all", help="Comma-separated platforms or all.")
    return parser.parse_args()


def main() -> int:
    add_local_package_root()
    try:
        from llm_wiki.core.manifest import parse_platforms
        from llm_wiki.core.mirror import sync_platforms
    except ModuleNotFoundError:
        print("llm_wiki package is required. Install with `pipx install llm-wiki-agent`.", file=sys.stderr)
        return 2

    args = parse_args()
    return sync_platforms(
        Path(args.kb_root),
        platforms=parse_platforms(args.platform),
        check=args.check,
    )


if __name__ == "__main__":
    raise SystemExit(main())
