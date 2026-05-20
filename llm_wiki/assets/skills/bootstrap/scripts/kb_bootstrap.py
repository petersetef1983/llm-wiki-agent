#!/usr/bin/env python3
"""Compatibility wrapper for the packaged LLM Wiki initializer."""

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
    parser = argparse.ArgumentParser(description="Create a new LLM Wiki knowledge base.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Bootstrap a new knowledge base.")
    create_parser.add_argument("--root", required=True, help="Target directory for the new knowledge base.")
    create_parser.add_argument("--platform", default="all", help="Comma-separated platforms or all.")
    create_parser.add_argument("--dry-run", action="store_true", help="Print planned actions without writing files.")
    create_parser.add_argument("--confirm", default="", help="Required creation confirmation token: CREATE-KB.")

    check_parser = subparsers.add_parser(
        "check-skeleton",
        help="Deprecated; use `python -m llm_wiki upgrade --dry-run`.",
    )
    check_parser.add_argument("--root", default="kb", help="Knowledge base root directory.")

    sync_parser = subparsers.add_parser(
        "sync-skeleton",
        help="Deprecated; use `python -m llm_wiki upgrade`.",
    )
    sync_parser.add_argument("--root", default="kb", help="Knowledge base root directory.")
    sync_parser.add_argument("--dry-run", action="store_true", help="Accepted for compatibility.")
    sync_parser.add_argument("--confirm", default="", help="Accepted for compatibility.")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    add_local_package_root()
    try:
        from llm_wiki.core.bootstrap import init_kb
        from llm_wiki.core.manifest import parse_platforms
    except ModuleNotFoundError:
        print("llm_wiki package is required. Install with `pipx install llm-wiki-agent`.", file=sys.stderr)
        return 2

    if args.command == "create":
        return init_kb(
            Path(args.root),
            platforms=parse_platforms(args.platform),
            dry_run=args.dry_run,
            confirm=args.confirm,
            adopt_existing=False,
        )

    print("Bootstrap skeleton maintenance moved into the packaged agent kit.", file=sys.stderr)
    print("Use `python -m llm_wiki upgrade --root <kb-root> --dry-run`.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
