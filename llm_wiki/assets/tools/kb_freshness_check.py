#!/usr/bin/env python3
"""Batch freshness checks for project-reverse-backed project themes."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_REVERSE = Path(".agents/skills/project-reverse/scripts/project_reverse_helper.py")


def parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS, help="Knowledge-base root. Defaults to current directory.")

    parser = argparse.ArgumentParser(description="Run project-reverse freshness checks across project themes.")
    parser.add_argument("--root", default=".", help="Knowledge-base root. Defaults to current directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", parents=[common], help="Check project themes for source freshness.")
    check.add_argument("--theme", action="append", default=[], help="Theme path to check. Repeatable.")
    check.add_argument("--write-report", help="Write JSON report to this path, relative to root unless absolute.")
    check.add_argument("--write-markdown", help="Write a readable Markdown report to this path.")
    check.add_argument("--write-diffs", action="store_true", help="For stale projects, also write project-reverse diff evidence.")
    check.add_argument("--timeout", type=int, default=45, help="Seconds per freshness or diff subprocess.")
    check.add_argument("--git-timeout", type=int, default=30, help="Seconds per remote git freshness operation.")
    check.add_argument("--format", choices=["text", "json"], default="text")

    report = subparsers.add_parser("report", parents=[common], help="Render an existing JSON freshness report as Markdown.")
    report.add_argument("--input", default="outputs/freshness/latest.json")
    report.add_argument("--output", default="outputs/freshness/latest.md")

    return parser.parse_args()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def extract_backtick_value(content: str, key: str) -> str | None:
    match = re.search(rf"(?m)^-\s+{re.escape(key)}:\s+`([^`]+)`", content)
    if match:
        value = match.group(1).strip()
        return None if value in {"unknown", "none", "default/current"} else value
    return None


def iter_project_themes(root: Path, explicit: list[str]) -> list[Path]:
    if explicit:
        result = []
        for item in explicit:
            path = Path(item)
            if not path.is_absolute():
                path = root / path
            result.append(path.resolve())
        return result
    project_dir = root / "themes" / "project"
    if not project_dir.is_dir():
        return []
    return sorted((path for path in project_dir.iterdir() if path.is_dir()), key=lambda item: item.name.lower())


def newest_anchor(theme_dir: Path) -> Path | None:
    sources = theme_dir / "sources"
    if not sources.is_dir():
        return None
    anchors = sorted(sources.glob("project-reverse-source-anchor*.md"), key=lambda item: item.stat().st_mtime, reverse=True)
    return anchors[0] if anchors else None


def run_helper(root: Path, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / PROJECT_REVERSE), *args],
        cwd=str(root),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def check_theme(root: Path, theme_dir: Path, timeout: int, git_timeout: int, write_diffs: bool) -> dict[str, Any]:
    anchor = newest_anchor(theme_dir)
    item: dict[str, Any] = {
        "theme": theme_dir.relative_to(root).as_posix() if theme_dir.is_relative_to(root) else str(theme_dir),
        "source_anchor": None,
        "repo": None,
        "analyzed_commit": None,
        "status": "not_configured",
        "latest_checked_commit": None,
        "check_error": None,
        "diff": None,
    }
    if anchor is None:
        item["check_error"] = "No project-reverse source anchor found."
        return item

    content = read_text(anchor)
    repo = extract_backtick_value(content, "input")
    analyzed_commit = extract_backtick_value(content, "analyzed_commit")
    item.update(
        {
            "source_anchor": anchor.relative_to(root).as_posix() if anchor.is_relative_to(root) else str(anchor),
            "repo": repo,
            "analyzed_commit": analyzed_commit,
        }
    )
    if not repo or not analyzed_commit:
        item["status"] = "unknown"
        item["check_error"] = "Source anchor is missing repo input or analyzed_commit."
        return item

    try:
        completed = run_helper(
            root,
            [
                "check-freshness",
                "--repo",
                repo,
                "--analyzed-commit",
                analyzed_commit,
                "--git-timeout",
                str(git_timeout),
            ],
            timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        item["status"] = "unknown"
        item["check_error"] = str(exc)
        return item
    item["freshness_exit_code"] = completed.returncode
    item["freshness_stderr"] = completed.stderr.strip()
    if completed.returncode != 0:
        item["status"] = "unknown"
        item["check_error"] = completed.stderr.strip() or completed.stdout.strip()
        return item

    try:
        payload = json.loads(completed.stdout)
        freshness = payload.get("freshness") or {}
        item["status"] = freshness.get("status") or "unknown"
        item["latest_checked_commit"] = freshness.get("latest_checked_commit")
        item["check_error"] = freshness.get("check_error")
    except json.JSONDecodeError:
        item["status"] = "unknown"
        item["check_error"] = completed.stdout.strip() or "Freshness output was not valid JSON."
        return item

    if write_diffs and item["status"] == "stale" and item["latest_checked_commit"]:
        diff_output = theme_dir / "outputs" / "document-intake" / "project-reverse-diff.json"
        sync_output = theme_dir / "outputs" / "document-intake" / "sync-diff.json"
        diff_output.parent.mkdir(parents=True, exist_ok=True)
        try:
            diff = run_helper(
                root,
                [
                    "diff",
                    "--repo",
                    repo,
                    "--old-commit",
                    analyzed_commit,
                    "--new-commit",
                    str(item["latest_checked_commit"]),
                    "--output",
                    diff_output.relative_to(root).as_posix(),
                    "--sync-diff-output",
                    sync_output.relative_to(root).as_posix(),
                    "--git-timeout",
                    str(git_timeout),
                ],
                timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            item["diff"] = {"exit_code": None, "error": str(exc)}
            return item
        item["diff"] = {
            "exit_code": diff.returncode,
            "output": diff_output.relative_to(root).as_posix(),
            "sync_output": sync_output.relative_to(root).as_posix(),
            "stdout": diff.stdout.strip(),
            "stderr": diff.stderr.strip(),
        }
    return item


def build_report(root: Path, themes: list[str], timeout: int, git_timeout: int, write_diffs: bool) -> dict[str, Any]:
    items = [check_theme(root, theme_dir, timeout, git_timeout, write_diffs) for theme_dir in iter_project_themes(root, themes)]
    return {
        "schema_version": "kb-freshness.v1",
        "root": str(root),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timeout_seconds": timeout,
        "git_timeout_seconds": git_timeout,
        "items": items,
        "summary": {
            "current": sum(1 for item in items if item.get("status") == "current"),
            "stale": sum(1 for item in items if item.get("status") == "stale"),
            "unknown": sum(1 for item in items if item.get("status") == "unknown"),
            "not_configured": sum(1 for item in items if item.get("status") == "not_configured"),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Freshness Report",
        "",
        f"- checked_at: `{report.get('checked_at')}`",
        f"- root: `{report.get('root')}`",
        "",
        "## Summary",
        "",
    ]
    summary = report.get("summary") or {}
    for key in ["current", "stale", "unknown", "not_configured"]:
        lines.append(f"- {key}: `{summary.get(key, 0)}`")
    lines.extend(["", "## Projects", ""])
    for item in report.get("items", []):
        lines.append(f"### {item.get('theme')}")
        lines.append("")
        lines.append(f"- status: `{item.get('status')}`")
        lines.append(f"- repo: `{item.get('repo') or 'unknown'}`")
        lines.append(f"- analyzed_commit: `{item.get('analyzed_commit') or 'unknown'}`")
        lines.append(f"- latest_checked_commit: `{item.get('latest_checked_commit') or 'unknown'}`")
        if item.get("check_error"):
            lines.append(f"- check_error: `{item.get('check_error')}`")
        if item.get("status") == "stale":
            lines.append("- next_action: run project-reverse diff evidence review, then ingest only affected durable pages.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_json_report(root: Path, target: str, report: dict[str, Any]) -> Path:
    path = Path(target)
    if not path.is_absolute():
        path = root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    if args.command == "check":
        report = build_report(root, args.theme, args.timeout, args.git_timeout, args.write_diffs)
        if args.write_report:
            json_path = write_json_report(root, args.write_report, report)
            markdown_target = args.write_markdown
            if not markdown_target and json_path.suffix.lower() == ".json":
                markdown_target = str(json_path.with_suffix(".md"))
            if markdown_target:
                md_path = Path(markdown_target)
                if not md_path.is_absolute():
                    md_path = root / md_path
                md_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.write_text(render_markdown(report), encoding="utf-8")
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            summary = report["summary"]
            print(
                "freshness "
                + " ".join(f"{key}={summary.get(key, 0)}" for key in ["current", "stale", "unknown", "not_configured"])
            )
            for item in report["items"]:
                print(f"- {item['theme']}: {item['status']}")
        return 0

    if args.command == "report":
        input_path = Path(args.input)
        if not input_path.is_absolute():
            input_path = root / input_path
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = root / output_path
        report = json.loads(read_text(input_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"Wrote freshness report to {output_path}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
