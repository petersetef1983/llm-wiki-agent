from __future__ import annotations

import argparse
from pathlib import Path

from ..core.doctor import doctor
from ..core.manifest import parse_platforms


def register_doctor(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("doctor", help="Run agent-kit health checks.")
    parser.add_argument("--root", default=".", help="Knowledge base root.")
    parser.add_argument("--platform", default="all", help="Comma-separated platforms or all.")
    parser.set_defaults(handler=run_doctor)


def run_doctor(args: argparse.Namespace) -> int:
    return doctor(Path(args.root), platforms=parse_platforms(args.platform))
