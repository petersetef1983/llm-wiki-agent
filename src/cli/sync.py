from __future__ import annotations

import argparse
from pathlib import Path

from ..core.manifest import parse_platforms
from ..core.mirror import sync_platforms


def register_sync(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("sync", help="Sync platform instruction files and skill mirrors.")
    parser.add_argument("--root", default=".", help="Knowledge base root.")
    parser.add_argument("--platform", default="all", help="Comma-separated platforms or all.")
    parser.add_argument("--check", action="store_true", help="Check drift only.")
    parser.set_defaults(handler=run_sync)


def run_sync(args: argparse.Namespace) -> int:
    return sync_platforms(Path(args.root), platforms=parse_platforms(args.platform), check=args.check)
