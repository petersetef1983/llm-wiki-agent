from __future__ import annotations

import difflib
from pathlib import Path, PurePosixPath
from typing import Any

from .types import ProposedChange


CONFIRM_WRITE = "WRITE-KB"
DENIED_WRITE_PARTS = {
    ".agents",
    ".claude",
    ".codex",
    ".data-sources",
    ".git",
    ".hermes",
    ".obsidian",
    ".openclaw",
    ".opencode",
    ".qmd",
    ".query-index",
    ".trae",
    "__pycache__",
}
ALLOWED_ACTIONS = {"write", "append"}


def render_change_diffs(root: Path, changes: list[ProposedChange]) -> list[dict[str, Any]]:
    rendered = []
    for change in changes:
        validation = validate_change(root, change)
        if validation.get("status") != "ok":
            rendered.append({"status": "denied", "change": change.to_dict(), "error": validation.get("error")})
            continue
        target = Path(str(validation["path"]))
        before = _read_text(target) if target.exists() else ""
        after = _after_text(before, change)
        diff = "\n".join(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=f"a/{change.path}",
                tofile=f"b/{change.path}",
                lineterm="",
            )
        )
        rendered.append({"status": "ok", "change": change.to_dict(), "diff": diff})
    return rendered


def apply_changes(root: Path, changes: list[ProposedChange], *, confirm: str) -> dict[str, Any]:
    if confirm != CONFIRM_WRITE:
        return {
            "status": "needs_confirmation",
            "error": f'write operations require --confirm {CONFIRM_WRITE}',
            "diffs": render_change_diffs(root, changes),
        }
    applied = []
    denied = []
    for change in changes:
        validation = validate_change(root, change)
        if validation.get("status") != "ok":
            denied.append({"change": change.to_dict(), "error": validation.get("error")})
            continue
        target = Path(str(validation["path"]))
        before = _read_text(target) if target.exists() else ""
        after = _after_text(before, change)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(after, encoding="utf-8")
        applied.append({"path": change.path, "action": change.action})
    return {
        "status": "ok" if not denied else "partial",
        "applied": applied,
        "denied": denied,
    }


def validate_change(root: Path, change: ProposedChange) -> dict[str, Any]:
    if change.action not in ALLOWED_ACTIONS:
        return {"status": "denied", "error": f"unsupported action `{change.action}`"}
    if "\x00" in change.path:
        return {"status": "denied", "error": "path contains NUL byte"}
    cleaned = change.path.strip().replace("\\", "/").lstrip("/")
    rel = PurePosixPath(cleaned)
    if rel.is_absolute() or rel.drive or any(part in {"", ".", ".."} for part in rel.parts):
        return {"status": "denied", "error": "path traversal is not allowed"}
    if any(part in DENIED_WRITE_PARTS for part in rel.parts):
        return {"status": "denied", "error": "runtime/platform paths are not writable through agent CLI"}
    target = (root / Path(*rel.parts)).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError:
        return {"status": "denied", "error": "path escapes knowledge base root"}
    return {"status": "ok", "path": str(target)}


def _after_text(before: str, change: ProposedChange) -> str:
    content = change.content
    if change.action == "append":
        separator = "" if not before or before.endswith("\n") else "\n"
        result = before + separator + content
    else:
        result = content
    return result if result.endswith("\n") else result + "\n"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
