#!/usr/bin/env python3
"""Shared utilities for deterministic synthesis helpers."""

from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_MAX_CHARS = 8_000
CONFIRM_WRITE = "WRITE-KB"
OUTPUT_NAMES = [
    "asset-match-brief.md",
    "engineering-brief.md",
    "implementation-guide.md",
    "decision-brief.md",
    "backlog.md",
]
STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "must", "should",
    "have", "will", "can", "able", "use", "using", "requirement", "functional", "non",
    "技术", "需求", "功能", "项目", "系统", "可以", "需要", "支持",
}
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")

COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "shared" / "scripts"
INGEST_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "ingest" / "scripts"
for script_dir in (COMMON_SCRIPTS_DIR, INGEST_SCRIPTS_DIR):
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

try:
    from kb_activity_log import append_activity_log
except Exception:  # pragma: no cover - copied helpers may run without shared scripts.
    append_activity_log = None  # type: ignore[assignment]

try:
    from kb_ingest_core import build_wikilink
except Exception:  # pragma: no cover - fallback for standalone execution.

    def build_wikilink(reference: str, label: str | None = None) -> str:
        label = label or reference
        return f"[[{reference}|{label}]]"


def read_text(path: Path, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    return text[:max_chars] if max_chars and len(text) > max_chars else text


def clean_theme_path(value: str) -> str:
    text = (value or "").strip().replace("\\", "/").strip("/")
    if text.endswith("/README.md"):
        text = text.removesuffix("/README.md")
    elif text.endswith("/README"):
        text = text.removesuffix("/README")
    elif text.endswith(".md"):
        text = text.removesuffix(".md")
    try:
        rel = PurePosixPath(text)
    except ValueError:
        return ""
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        return ""
    if len(rel.parts) < 3 or rel.parts[0] != "themes":
        return ""
    return rel.as_posix()


def title_from_markdown(content: str, path: Path) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def extract_tokens(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z0-9][a-z0-9_-]{2,}", lowered))
    words.update(re.findall(r"[\u4e00-\u9fff]{2,}", lowered))
    return {word for word in words if word not in STOPWORDS}


def unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def infer_theme_from_path(path: str) -> str:
    parts = PurePosixPath(path).parts
    if len(parts) >= 3 and parts[0] == "themes":
        return "/".join(parts[:3])
    return ""


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.lower()).strip("-._")
    return slug or "asset"


def table_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def validate_wikilinks(root: Path, proposed_changes: list[dict[str, Any]], planned_paths: list[str] | None = None) -> dict[str, Any]:
    planned = {normalize_ref(path) for path in (planned_paths or [])}
    missing = []
    checked = 0
    for change in proposed_changes:
        content = str(change.get("content") or "")
        source = str(change.get("path") or "")
        for target in WIKILINK_RE.findall(content):
            checked += 1
            normalized = normalize_ref(target)
            if normalized in planned:
                continue
            if not (root / f"{normalized}.md").exists() and not (root / normalized).exists():
                missing.append({"source": source, "target": target, "normalized": normalized})
    return {
        "status": "ok" if not missing else "missing_links",
        "checked": checked,
        "missing": missing,
    }


def normalize_ref(value: str) -> str:
    text = value.strip().replace("\\", "/")
    if text.endswith(".md"):
        text = text[:-3]
    return text.strip("/")


def safe_write_path(root: Path, rel_path: str) -> Path | None:
    try:
        rel = PurePosixPath(rel_path.replace("\\", "/"))
    except ValueError:
        return None
    if rel.is_absolute() or rel.drive or not rel.parts or any(part in {"", ".", ".."} for part in rel.parts):
        return None
    if is_protected_sources_path(rel) or rel.parts[0].startswith("."):
        return None
    target = (root / Path(*rel.parts)).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def is_protected_sources_path(rel: PurePosixPath) -> bool:
    parts = rel.parts
    if not parts:
        return False
    if parts[0] == "sources":
        return True
    return len(parts) >= 4 and parts[0] == "themes" and parts[3] == "sources"


def log_synthesize_operation(root: Path, target_theme: str, *, action: str, status: str, details: list[str] | None = None) -> None:
    if append_activity_log is None:
        return
    append_activity_log(
        root,
        skill="synthesize",
        action=action,
        summary=f"Generated synthesis outputs for `{target_theme}`.",
        status=status,
        details=details or [],
    )
