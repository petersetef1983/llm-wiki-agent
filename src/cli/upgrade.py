from __future__ import annotations

import argparse
from pathlib import Path

from ..core.upgrade import CONFIRM_UPGRADE, upgrade_kb


def register_upgrade(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("upgrade", help="Check or apply bundled runtime asset upgrades.")
    parser.add_argument("--root", default=".", help="Knowledge base root.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned upgrade actions without writing files.")
    parser.add_argument("--confirm", default="", help=f"Required write confirmation token: {CONFIRM_UPGRADE}.")
    parser.add_argument("--force-conflicts", action="store_true", help="Overwrite conflicting canonical skill files.")
    parser.set_defaults(handler=run_upgrade)


def run_upgrade(args: argparse.Namespace) -> int:
    return upgrade_kb(
        Path(args.root),
        dry_run=args.dry_run,
        confirm=args.confirm,
        force_conflicts=args.force_conflicts,
    )
