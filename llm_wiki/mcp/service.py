from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

from llm_wiki.core.assets import assets_root
from llm_wiki.core.manifest import (
    SUPPORTED_PLATFORMS,
    is_existing_kb_root,
    read_manifest_text,
    validate_manifest,
)
from llm_wiki.core.mirror import check_one_platform


CONFIRM_WRITE = "WRITE-KB"
DEFAULT_MAX_CHARS = 20_000
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
DENIED_READ_PARTS = {
    ".agents",
    ".claude",
    ".codex",
    ".data-sources",
    ".hermes",
    ".obsidian",
    ".openclaw",
    ".opencode",
    ".qmd",
    ".query-index",
    ".trae",
    "__pycache__",
}
DENIED_INDEX_PARTS = DENIED_READ_PARTS | {"inbox"}


@dataclass
class LLMWikiService:
    root: Path
    readonly: bool = False

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        if not self.root.exists():
            raise FileNotFoundError(f"knowledge base root does not exist: {self.root}")
        if not is_existing_kb_root(self.root):
            raise ValueError(f"not an LLM Wiki knowledge base root: {self.root}")

    def manifest_text(self) -> str:
        text = read_manifest_text(self.root)
        return text or "# llm-wiki.yaml missing\n"

    def manifest_summary(self) -> dict[str, Any]:
        text = read_manifest_text(self.root)
        platforms = self.enabled_platforms()
        return {
            "status": "ok" if text else "missing",
            "root": str(self.root),
            "manifest_path": str(self.root / "llm-wiki.yaml"),
            "platforms": platforms,
            "issues": validate_manifest(self.root, platforms) if text else ["missing llm-wiki.yaml"],
            "text": text,
        }

    def index_home_text(self) -> str:
        return self._read_text_resource("index/home.md")

    def page_text(self, path: str) -> str:
        page = self.read_page(path, max_chars=0)
        if page.get("status") != "ok":
            return json.dumps(page, ensure_ascii=False, indent=2)
        return str(page["content"])

    def status(self, *, include_platform_drift: bool = True, include_search_status: bool = True) -> dict[str, Any]:
        platforms = self.enabled_platforms()
        issues: list[str] = []
        manifest_issues = validate_manifest(self.root, platforms)
        issues.extend(f"manifest: {item}" for item in manifest_issues)

        platform_drift: dict[str, list[str]] = {}
        if include_platform_drift:
            for platform in platforms:
                drift = check_one_platform(self.root, platform)
                platform_drift[platform] = drift
                issues.extend(f"{platform}: {item}" for item in drift)

        payload: dict[str, Any] = {
            "status": "ok" if not issues else "issues",
            "root": str(self.root),
            "readonly": self.readonly,
            "platforms": platforms,
            "manifest_issues": manifest_issues,
            "platform_drift": platform_drift,
            "issues": issues,
            "checked_at": _utc_now(),
        }
        if include_search_status:
            payload["search_status"] = self.search_status()
        return payload

    def search_status(self) -> dict[str, Any]:
        return self._run_search_bridge(["status"])

    def search(self, *, query: str, mode: str = "auto", top: int = 10, allow_fallback: bool = True) -> dict[str, Any]:
        if not query.strip():
            return {"status": "error", "error": "query is required"}
        top = _clamp_int(top, 1, MAX_LIMIT)
        args = ["search", "--query", query, "--mode", mode, "--top", str(top), "--json-output"]
        if allow_fallback:
            args.append("--allow-fallback")
        return self._run_search_bridge(args)

    def list_pages(
        self,
        *,
        prefix: str = "",
        node_type: str = "",
        theme: str = "",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = _clamp_int(limit, 1, MAX_LIMIT)
        offset = max(0, offset)
        entries = self._index_entries()
        if prefix:
            clean_prefix = prefix.strip().replace("\\", "/").lstrip("/")
            entries = [item for item in entries if str(item.get("path", "")).startswith(clean_prefix)]
        if node_type:
            entries = [item for item in entries if (item.get("frontmatter") or {}).get("node_type") == node_type]
        if theme:
            query_index = _load_query_index_module()
            entries = [
                item
                for item in entries
                if query_index.field_matches(item.get("frontmatter") or {}, "themes", theme)
            ]
        return {
            "status": "ok",
            "root": str(self.root),
            "count": len(entries),
            "offset": offset,
            "limit": limit,
            "entries": [_entry_summary(item) for item in entries[offset : offset + limit]],
        }

    def read_page(self, path: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> dict[str, Any]:
        resolved = self._resolve_read_path(path)
        if isinstance(resolved, dict):
            return resolved
        page_path, rel = resolved
        if not page_path.exists() or not page_path.is_file():
            return {"status": "not_found", "path": rel}
        content = _read_text(page_path)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        truncated = False
        if max_chars and max_chars > 0 and len(content) > max_chars:
            content = content[:max_chars]
            truncated = True
        stat = page_path.stat()
        return {
            "status": "ok",
            "path": rel,
            "title": _title_from_content(content, page_path),
            "sha256": digest,
            "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
            "truncated": truncated,
            "content": content,
        }

    def filter_pages(self, *, filters: dict[str, str] | None = None, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
        filters = {str(key): str(value) for key, value in (filters or {}).items() if value not in (None, "")}
        limit = _clamp_int(limit, 1, MAX_LIMIT)
        query_index = _load_query_index_module()
        entries = query_index.apply_filters(self._index_entries(), filters)
        return {
            "status": "ok",
            "root": str(self.root),
            "filters": filters,
            "count": len(entries),
            "limit": limit,
            "entries": [_entry_summary(item) for item in entries[:limit]],
        }

    def aggregate(self, *, field: str, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
        if not field.strip():
            return {"status": "error", "error": "field is required"}
        limit = _clamp_int(limit, 1, MAX_LIMIT)
        query_index = _load_query_index_module()
        groups: dict[str, list[str]] = {}
        for entry in self._index_entries():
            values = query_index.flatten_values((entry.get("frontmatter") or {}).get(field))
            for value in values or ["[missing]"]:
                groups.setdefault(str(value), []).append(str(entry["path"]))
        ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))[:limit]
        return {
            "status": "ok",
            "field": field,
            "groups": [
                {"value": value, "count": len(paths), "sample_paths": paths[:10]}
                for value, paths in ordered
            ],
        }

    def record_query(
        self,
        *,
        question: str,
        summary: str = "",
        themes: list[str] | None = None,
        answer_status: str = "",
        writeback_candidate: str = "",
        writeback_target: str = "",
        gaps: list[str] | None = None,
        status: str = "completed",
        confirm: str = "",
    ) -> dict[str, Any]:
        write_check = self._write_check(confirm)
        if write_check:
            return write_check
        if not question.strip():
            return {"status": "error", "error": "question is required"}
        themes = themes or []
        gaps = gaps or []
        details = [f"question={_one_line(question)}"]
        if themes:
            details.append(f"themes={', '.join(_one_line(item) for item in themes)}")
        if answer_status:
            details.append(f"answer_status={_one_line(answer_status)}")
        if writeback_candidate:
            details.append(f"writeback_candidate={_one_line(writeback_candidate)}")
        if writeback_target:
            details.append(f"writeback_target={_one_line(writeback_target)}")
        if gaps:
            details.append(f"gaps={', '.join(_one_line(item) for item in gaps)}")
        log_path = self._append_activity_log(
            skill="query",
            action="query",
            summary=summary.strip() or f"Completed query: {_one_line(question)}",
            status=status or "completed",
            details=details,
        )
        return {
            "status": "ok",
            "log_path": str(log_path),
            "question": question,
            "summary": summary,
            "themes": themes,
            "answer_status": answer_status,
            "writeback_candidate": writeback_candidate,
            "writeback_target": writeback_target,
            "gaps": gaps,
        }

    def create_inbox_note(
        self,
        *,
        title: str,
        content: str,
        source: str = "",
        tags: list[str] | None = None,
        confirm: str = "",
    ) -> dict[str, Any]:
        write_check = self._write_check(confirm)
        if write_check:
            return write_check
        title = _one_line(title)
        if not title:
            return {"status": "error", "error": "title is required"}
        tags = [_one_line(tag) for tag in (tags or []) if _one_line(tag)]
        inbox = self.root / "inbox" / "to-be-filed"
        inbox.mkdir(parents=True, exist_ok=True)
        base = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{_slugify(title)}"
        target = _unique_path(inbox / f"{base}.md")
        tag_lines = "\n".join(f"  - {_yaml_quote(tag)}" for tag in tags) if tags else "  - inbox"
        note = "\n".join(
            [
                "---",
                f"title: {_yaml_quote(title)}",
                "node_type: inbox-note",
                "status: to-be-filed",
                f"source: {_yaml_quote(source)}",
                f"created_at: {_yaml_quote(_utc_now())}",
                "tags:",
                tag_lines,
                "---",
                "",
                f"# {title}",
                "",
                content.rstrip(),
                "",
            ]
        )
        target.write_text(note, encoding="utf-8")
        return {
            "status": "ok",
            "path": target.relative_to(self.root).as_posix(),
            "title": title,
            "tags": tags,
        }

    def enabled_platforms(self) -> list[str]:
        text = read_manifest_text(self.root)
        if not text:
            return list(SUPPORTED_PLATFORMS)
        platforms = [platform for platform in SUPPORTED_PLATFORMS if f"  {platform}:" in text]
        return platforms or list(SUPPORTED_PLATFORMS)

    def _index_entries(self) -> list[dict[str, Any]]:
        query_index = _load_query_index_module()
        payload = query_index.build_index(self.root)
        entries = []
        for entry in payload.get("entries", []):
            parts = PurePosixPath(str(entry.get("path", ""))).parts
            if any(part in DENIED_INDEX_PARTS for part in parts):
                continue
            entries.append(entry)
        return entries

    def _read_text_resource(self, rel_path: str) -> str:
        page = self.read_page(rel_path, max_chars=0)
        if page.get("status") != "ok":
            return json.dumps(page, ensure_ascii=False, indent=2)
        return str(page["content"])

    def _resolve_read_path(self, value: str) -> tuple[Path, str] | dict[str, str]:
        if not value or "\x00" in value:
            return {"status": "denied", "error": "path is required"}
        cleaned = value.strip().replace("\\", "/").lstrip("/")
        rel = PurePosixPath(cleaned)
        if rel.is_absolute() or rel.drive or any(part in {"", ".", ".."} for part in rel.parts):
            return {"status": "denied", "error": "path traversal is not allowed", "path": value}
        if any(part in DENIED_READ_PARTS for part in rel.parts):
            return {"status": "denied", "error": "runtime directories are not readable through MCP", "path": rel.as_posix()}
        if rel.suffix.lower() != ".md":
            return {"status": "denied", "error": "only markdown pages can be read", "path": rel.as_posix()}
        candidate = (self.root / Path(*rel.parts)).resolve()
        if not _is_relative_to(candidate, self.root):
            return {"status": "denied", "error": "path escapes knowledge base root", "path": rel.as_posix()}
        return candidate, rel.as_posix()

    def _run_search_bridge(self, command_args: list[str]) -> dict[str, Any]:
        root_tool = self.root / "tools" / "kb_search_bridge.py"
        if root_tool.exists():
            return _run_search_bridge_script(self.root, root_tool, command_args)
        tool_asset = assets_root() / "tools" / "kb_search_bridge.py"
        with resources.as_file(tool_asset) as tool_path:
            return _run_search_bridge_script(self.root, tool_path, command_args)

    def _write_check(self, confirm: str) -> dict[str, str] | None:
        if self.readonly:
            return {"status": "disabled", "error": "server is running in readonly mode"}
        if confirm != CONFIRM_WRITE:
            return {
                "status": "needs_confirmation",
                "error": f'write tools require confirm="{CONFIRM_WRITE}"',
            }
        return None

    def _append_activity_log(
        self,
        *,
        skill: str,
        action: str,
        summary: str,
        status: str,
        details: list[str],
    ) -> Path:
        log_path = self.root / "log.md"
        timestamp = datetime.now()
        day_heading = f"## {timestamp.strftime('%Y-%m-%d')}"
        time_label = timestamp.strftime("%H:%M:%S")
        entry_lines = [f"- `{time_label}` | skill=`{skill}` | action=`{action}` | status=`{status}` | {_one_line(summary)}"]
        entry_lines.extend(f"  - {_one_line(detail)}" for detail in details)
        entry = "\n".join(entry_lines)
        if log_path.exists():
            content = _read_text(log_path).rstrip()
            if day_heading in content:
                content += "\n" + entry + "\n"
            else:
                content += "\n\n" + day_heading + "\n\n" + entry + "\n"
        else:
            content = "# Knowledge Base Log\n\n" + day_heading + "\n\n" + entry + "\n"
        log_path.write_text(content, encoding="utf-8")
        return log_path


def _load_query_index_module() -> ModuleType:
    tool_asset = assets_root() / "tools" / "kb_query_index.py"
    with resources.as_file(tool_asset) as path:
        spec = importlib.util.spec_from_file_location("llm_wiki_mcp_kb_query_index", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not load query index helper: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def _run_search_bridge_script(root: Path, script: Path, command_args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(script), "--root", str(root), "--format", "json", *command_args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    stdout = proc.stdout.strip()
    payload: dict[str, Any]
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        payload = {"stdout": stdout}
    payload.setdefault("schema_version", "llm-wiki-mcp-search.v1")
    payload["exit_code"] = proc.returncode
    if proc.stderr.strip():
        payload["stderr"] = proc.stderr.strip()
    if proc.returncode != 0 and "status" not in payload:
        payload["status"] = "error"
    return payload


def _entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    frontmatter = entry.get("frontmatter") or {}
    return {
        "path": entry.get("path"),
        "title": entry.get("title"),
        "node_type": entry.get("node_type"),
        "mtime_utc": entry.get("mtime_utc"),
        "frontmatter": frontmatter,
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _title_from_content(content: str, path: Path) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(int(value), upper))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _one_line(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "-", value.lower()).strip("-._")
    return slug or "note"


def _yaml_quote(value: str) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for idx in range(2, 10_000):
        candidate = path.with_name(f"{stem}-{idx}{suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"could not allocate unique inbox note path for {path}")
