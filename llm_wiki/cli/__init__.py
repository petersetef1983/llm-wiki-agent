from __future__ import annotations

import argparse
import sys

from .doctor import register_doctor
from .init import register_init
from .serve import register_serve
from .sync import register_sync
from .upgrade import register_upgrade


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llm-wiki", description="Initialize and maintain LLM Wiki agent assets.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_init(subparsers)
    register_sync(subparsers)
    register_doctor(subparsers)
    register_upgrade(subparsers)
    register_serve(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.error(f"unknown command: {args.command}")
    try:
        return int(handler(args))
    except Exception as exc:  # noqa: BLE001 - CLI should produce compact user-facing failures.
        print(f"error: {exc}", file=sys.stderr)
        return 2
