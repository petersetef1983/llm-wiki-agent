#!/usr/bin/env python3
"""Helpers for query workflows that need deterministic write-back such as activity logging."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from kb_activity_log import append_activity_log


def parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS, help="Knowledge base root directory")

    parser = argparse.ArgumentParser(description="Helpers for query workflows.")
    parser.add_argument("--root", default=".", help="Knowledge base root directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record-query", parents=[common], help="Record a query operation in log.md")
    record.add_argument("--question", required=True, help="The user question or a short query title")
    record.add_argument("--summary", help="Short answer or outcome summary")
    record.add_argument("--theme", action="append", default=[], help="Relevant theme name or path. Repeatable.")
    record.add_argument(
        "--answer-status",
        choices=["confirmed", "inferred", "insufficient"],
        help="Grounding status for the answer.",
    )
    record.add_argument(
        "--writeback-candidate",
        choices=["yes", "no"],
        help="Whether the answer should be considered for durable wiki write-back.",
    )
    record.add_argument("--writeback-target", help="Existing or proposed wiki/output page for write-back.")
    record.add_argument("--gap", action="append", default=[], help="Reported gap, such as graph_gap, output_gap, or evidence_gap. Repeatable.")
    record.add_argument("--status", default="completed", help="Query status, for example completed/incomplete/follow-up-needed")
    record.add_argument("--format", choices=["text", "json"], default="text")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    if args.command == "record-query":
        summary = args.summary or f"完成问题检索：{args.question}"
        details = [f"question={args.question}"]
        if args.theme:
            details.append(f"themes={', '.join(args.theme)}")
        if args.answer_status:
            details.append(f"answer_status={args.answer_status}")
        if args.writeback_candidate:
            details.append(f"writeback_candidate={args.writeback_candidate}")
        if args.writeback_target:
            details.append(f"writeback_target={args.writeback_target}")
        if args.gap:
            details.append(f"gaps={', '.join(args.gap)}")
        log_path = append_activity_log(
            root,
            skill="query",
            action="query",
            summary=summary,
            status=args.status,
            details=details,
        )
        payload = {
            "root": str(root),
            "log_path": str(log_path),
            "question": args.question,
            "summary": summary,
            "themes": args.theme,
            "answer_status": args.answer_status,
            "writeback_candidate": args.writeback_candidate,
            "writeback_target": args.writeback_target,
            "gaps": args.gap,
            "status": args.status,
        }
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Recorded query activity at {log_path}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
