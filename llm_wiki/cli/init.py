from __future__ import annotations

import argparse
from pathlib import Path

from llm_wiki.core.bootstrap import CONFIRM_CREATE, init_kb
from llm_wiki.core.manifest import parse_platforms


def register_init(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("init", help="Initialize a new LLM Wiki knowledge base.")
    parser.add_argument("target_pos", nargs="?", help="Target directory, kept for short CLI compatibility.")
    parser.add_argument("--target", help="Target directory for the knowledge base.")
    parser.add_argument("--platform", default="all", help="Comma-separated platforms or all.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without writing files.")
    parser.add_argument("--confirm", default="", help=f"Required write confirmation token: {CONFIRM_CREATE}.")
    parser.add_argument("--adopt-existing", action="store_true", help="Add agent metadata/platform files to an existing KB.")
    parser.set_defaults(handler=run_init)


def run_init(args: argparse.Namespace) -> int:
    target_arg = args.target or args.target_pos
    if not target_arg:
        raise ValueError("init requires --target or positional target")
    return init_kb(
        Path(target_arg),
        platforms=parse_platforms(args.platform),
        dry_run=args.dry_run,
        confirm=args.confirm,
        adopt_existing=args.adopt_existing,
    )
