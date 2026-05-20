#!/usr/bin/env python3
"""Shared activity log helpers for ingest/query/lint operations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def append_activity_log(
    root: Path,
    *,
    skill: str,
    action: str,
    summary: str,
    status: str = "completed",
    details: list[str] | None = None,
) -> Path:
    """Append a structured activity record to `log.md` under the KB root."""
    log_path = root / "log.md"
    timestamp = datetime.now()
    day_heading = f"## {timestamp.strftime('%Y-%m-%d')}"
    time_label = timestamp.strftime("%H:%M:%S")

    entry_lines = [
        f"- `{time_label}` | skill=`{skill}` | action=`{action}` | status=`{status}` | {summary}"
    ]
    for detail in details or []:
        entry_lines.append(f"  - {detail}")
    entry = "\n".join(entry_lines)

    if not log_path.exists():
        content = "# Knowledge Base Log\n\n" + day_heading + "\n\n" + entry + "\n"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            print(f"Warning: could not append activity log at {log_path}: {exc}", file=sys.stderr)
        return log_path

    content = read_text(log_path).rstrip()
    if day_heading in content:
        content += "\n" + entry + "\n"
    else:
        content += "\n\n" + day_heading + "\n\n" + entry + "\n"
    try:
        log_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        print(f"Warning: could not append activity log at {log_path}: {exc}", file=sys.stderr)
    return log_path
