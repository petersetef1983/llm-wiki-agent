#!/usr/bin/env python3
"""Context and inventory collection for deterministic synthesis."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from kb_synthesize_common import DEFAULT_MAX_CHARS, STOPWORDS, clean_theme_path, read_text, title_from_markdown


def page_payload(root: Path, rel_path: str, max_chars: int) -> dict[str, Any] | None:
    path = root / rel_path
    if not path.is_file():
        return None
    content = read_text(path, max_chars=max_chars)
    return {
        "path": rel_path,
        "title": title_from_markdown(content, path),
        "content": content,
        "truncated": path.stat().st_size > len(content.encode("utf-8")),
    }


def collect_existing_pages(root: Path, rel_paths: list[str], max_chars: int) -> list[dict[str, Any]]:
    pages = []
    seen = set()
    for rel in rel_paths:
        if rel in seen:
            continue
        seen.add(rel)
        payload = page_payload(root, rel, max_chars)
        if payload:
            pages.append(payload)
    return pages


def collect_markdown_under(root: Path, base_rel: str, *, max_files: int, max_chars: int) -> list[dict[str, Any]]:
    base = root / base_rel
    if not base.is_dir():
        return []
    pages = []
    for path in sorted(base.glob("*.md"), key=lambda item: item.name.lower()):
        if path.name.lower() == "readme.md":
            continue
        rel = path.relative_to(root).as_posix()
        content = read_text(path, max_chars=max_chars)
        pages.append({"path": rel, "title": title_from_markdown(content, path), "content": content})
        if len(pages) >= max_files:
            break
    return pages


def collect_reuse_candidates(root: Path, max_chars: int) -> list[dict[str, Any]]:
    pages = []
    for path in sorted(root.glob("themes/*/*/outputs/reuse-candidates.md"), key=lambda item: item.as_posix().lower()):
        content = read_text(path, max_chars=max_chars)
        pages.append(
            {
                "path": path.relative_to(root).as_posix(),
                "theme": path.relative_to(root).parts[0:3],
                "content": content,
                "rows": parse_reuse_candidate_rows(content),
            }
        )
    return pages


def collect_historical_project_pages(root: Path, target_theme: str, max_chars: int) -> list[dict[str, Any]]:
    pages = []
    for path in sorted(root.glob("themes/project/*/**/*.md"), key=lambda item: item.as_posix().lower()):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(f"{target_theme}/") or "/sources/" in f"/{rel}/" or "/outputs/document-intake/" in f"/{rel}/":
            continue
        if len(pages) >= 120:
            break
        content = read_text(path, max_chars=max_chars // 2)
        pages.append({"path": rel, "title": title_from_markdown(content, path), "content": content})
    return pages


def collect_open_source_evidence(root: Path, max_chars: int) -> list[dict[str, Any]]:
    evidence = []
    for path in sorted(root.glob("themes/*/*/outputs/document-intake/project-reverse-analysis.json"), key=lambda item: item.as_posix().lower()):
        try:
            payload = json.loads(read_text(path, max_chars=max_chars * 4))
        except json.JSONDecodeError:
            continue
        license_signals = payload.get("license_signals") or {}
        vulnerabilities = payload.get("vulnerability_signals") or {}
        subset = {
            "path": path.relative_to(root).as_posix(),
            "theme": "/".join(path.relative_to(root).parts[:3]),
            "repo": payload.get("repo"),
            "license_type": payload.get("license_type") or license_signals.get("primary_license"),
            "license_signals": license_signals,
            "open_source_signals": payload.get("open_source_signals"),
            "community_health": payload.get("community_health"),
            "known_vulnerabilities": payload.get("known_vulnerabilities")
            if "known_vulnerabilities" in payload
            else vulnerabilities.get("vulnerabilities"),
            "vulnerability_signals": vulnerabilities,
            "modules": payload.get("modules", [])[:40],
            "reuse_assessment": payload.get("reuse_assessment", [])[:40],
            "warnings": payload.get("warnings", [])[:20],
        }
        evidence.append(subset)
    return evidence


def collect_synthesis_context(root: Path, target_theme: str, max_chars: int = DEFAULT_MAX_CHARS) -> dict[str, Any]:
    root = root.resolve()
    theme = clean_theme_path(target_theme)
    if not theme:
        raise ValueError("target theme must be under themes/<category>/<theme>")
    theme_dir = root / theme
    if not theme_dir.is_dir():
        raise FileNotFoundError(f"target theme does not exist: {theme}")

    target_pages = collect_existing_pages(
        root,
        [
            f"{theme}/README.md",
            f"{theme}/meta.md",
            f"{theme}/wiki/overview.md",
            f"{theme}/wiki/architecture.md",
            f"{theme}/wiki/open-questions.md",
            f"{theme}/outputs/requirement-analysis.md",
            f"{theme}/outputs/asset-match-brief.md",
            f"{theme}/outputs/engineering-brief.md",
            f"{theme}/outputs/implementation-guide.md",
            f"{theme}/outputs/decision-brief.md",
            f"{theme}/outputs/backlog.md",
            "outputs/requirement-analysis.md",
        ],
        max_chars,
    )
    return {
        "root": str(root),
        "target_theme": theme,
        "target_pages": target_pages,
        "technical_assets_index": page_payload(root, "index/technical-assets.md", max_chars),
        "cross_theme_map": page_payload(root, "index/cross-theme-map.md", max_chars),
        "shared_assets": collect_markdown_under(root, "shared/assets", max_files=80, max_chars=max_chars),
        "shared_patterns": collect_markdown_under(root, "shared/patterns", max_files=80, max_chars=max_chars // 2),
        "historical_project_pages": collect_historical_project_pages(root, theme, max_chars=max_chars),
        "reuse_candidates": collect_reuse_candidates(root, max_chars=max_chars),
        "open_source_evidence": collect_open_source_evidence(root, max_chars=max_chars),
    }


def requirement_analysis_path(root: Path, target_theme: str) -> Path:
    theme = clean_theme_path(target_theme)
    if not theme:
        raise ValueError("target theme must be under themes/<category>/<theme>")
    local = root / theme / "outputs" / "requirement-analysis.md"
    if local.is_file():
        return local
    fallback = root / "outputs" / "requirement-analysis.md"
    if fallback.is_file():
        return fallback
    return local


def parse_requirements(root: Path, target_theme: str) -> list[dict[str, Any]]:
    path = requirement_analysis_path(root, target_theme)
    if not path.is_file():
        return []
    rel = path.relative_to(root).as_posix()
    content = read_text(path, max_chars=60_000)
    rows = parse_requirement_table(content)
    if rows:
        return rows
    return parse_requirement_bullets(content, rel)


def parse_requirement_table(content: str) -> list[dict[str, Any]]:
    requirements = []
    header: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = split_markdown_table_row(stripped)
        lowered = [cell.lower() for cell in cells]
        if "id" in lowered and any("requirement" in cell or "constraint" in cell for cell in lowered):
            header = lowered
            continue
        if not header or len(cells) < 3 or not re.match(r"^(REQ|NFR|TECH|AC)-\d+", cells[0].strip(), flags=re.IGNORECASE):
            continue
        item = {header[idx]: cells[idx].strip() for idx in range(min(len(header), len(cells)))}
        requirements.append(
            {
                "id": item.get("id") or cells[0].strip(),
                "type": item.get("type") or "functional",
                "text": item.get("requirement") or item.get("constraint") or cells[2].strip(),
                "priority": item.get("priority") or "medium",
                "confidence": item.get("confidence") or "tentative",
                "evidence": item.get("evidence") or "",
                "related": item.get("related modules/entities") or item.get("related") or "",
            }
        )
    return requirements


def parse_requirement_bullets(content: str, rel_path: str) -> list[dict[str, Any]]:
    requirements = []
    current_type = "functional"
    for line_no, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        heading = stripped.lower().strip("#: ")
        if any(term in heading for term in ("non-functional", "non functional", "非功能")):
            current_type = "non-functional"
            continue
        if any(term in heading for term in ("technical", "constraint", "技术约束")):
            current_type = "technical"
            continue
        if any(term in heading for term in ("acceptance", "验收")):
            current_type = "acceptance"
            continue
        if any(term in heading for term in ("functional", "功能需求", "requirements")):
            current_type = "functional"
            continue
        match = re.match(r"^(?:[-*]|\d+[.)])\s+(.*)$", stripped)
        if not match:
            continue
        text = match.group(1).strip()
        if len(text) < 4:
            continue
        prefix = {"non-functional": "NFR", "technical": "TECH", "acceptance": "AC"}.get(current_type, "REQ")
        count = 1 + sum(1 for item in requirements if str(item["id"]).startswith(prefix))
        requirements.append(
            {
                "id": f"{prefix}-{count:03d}",
                "type": current_type,
                "text": text,
                "priority": priority_for_text(text),
                "confidence": "high" if current_type in {"functional", "non-functional", "technical", "acceptance"} else "medium",
                "evidence": f"{rel_path}#L{line_no}",
                "related": "",
            }
        )
    return requirements


def priority_for_text(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("p0", "must", "critical", "blocker", "必须", "强制", "关键")):
        return "high"
    if any(term in lowered for term in ("p2", "could", "nice", "optional", "可选", "建议")):
        return "low"
    return "medium"


def split_markdown_table_row(row: str) -> list[str]:
    text = row.strip().strip("|")
    cells: list[str] = []
    current: list[str] = []
    in_wikilink = 0
    idx = 0
    while idx < len(text):
        if text.startswith("[[", idx):
            in_wikilink += 1
            current.append("[[")
            idx += 2
            continue
        if text.startswith("]]", idx) and in_wikilink:
            in_wikilink -= 1
            current.append("]]")
            idx += 2
            continue
        char = text[idx]
        if char == "|" and not in_wikilink:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        idx += 1
    cells.append("".join(current).strip())
    return cells


def parse_reuse_candidate_rows(content: str) -> list[dict[str, Any]]:
    rows = []
    header: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = split_markdown_table_row(stripped)
        lowered = [cell.lower() for cell in cells]
        if any(cell in {"asset", "candidate", "module"} for cell in lowered):
            header = lowered
            continue
        if not header or len(cells) < 2:
            continue
        item = {header[idx]: cells[idx].strip() for idx in range(min(len(header), len(cells)))}
        rows.append(item)
    return rows


def first_present(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def build_candidate_inventory(context: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for page in context.get("shared_assets") or []:
        candidates.append({"kind": "shared_asset", "path": page["path"], "title": page.get("title"), "content": page.get("content", "")})
    for page in context.get("shared_patterns") or []:
        candidates.append({"kind": "shared_pattern", "path": page["path"], "title": page.get("title"), "content": page.get("content", "")})
    index_page = context.get("technical_assets_index")
    if index_page:
        candidates.append(
            {
                "kind": "technical_assets_index",
                "path": index_page["path"],
                "title": index_page.get("title"),
                "content": index_page.get("content", ""),
            }
        )
    for page in context.get("historical_project_pages") or []:
        candidates.append({"kind": "historical_project_page", "path": page["path"], "title": page.get("title"), "content": page.get("content", "")})
    for reuse_file in context.get("reuse_candidates") or []:
        for row in reuse_file.get("rows") or []:
            asset = first_present(row, ("asset", "candidate", "module", "capability", "name", "title")) or str(row)
            candidates.append(
                {
                    "kind": "reuse_candidate",
                    "path": reuse_file["path"],
                    "title": asset,
                    "content": json.dumps(row, ensure_ascii=False),
                    "source_theme": "/".join(reuse_file.get("theme") or []),
                    "reuse_level": first_present(row, ("reuse level", "reuse_level", "reuse mode", "reuse_mode", "level", "mode")),
                    "reuse_cost": first_present(row, ("reuse cost", "reuse_cost", "cost", "effort")),
                }
            )
    for evidence in context.get("open_source_evidence") or []:
        repo = evidence.get("repo") or {}
        repo_name = repo.get("name") or repo.get("remote_url") or evidence.get("path")
        for module in evidence.get("reuse_assessment") or evidence.get("modules") or []:
            module_name = module.get("module") or module.get("name") or repo_name
            candidates.append(
                {
                    "kind": "open_source_module",
                    "path": evidence["path"],
                    "title": module_name,
                    "content": json.dumps(module, ensure_ascii=False),
                    "source_theme": evidence.get("theme", ""),
                    "repo": repo,
                    "license_type": evidence.get("license_type"),
                    "license_signals": evidence.get("license_signals") or {},
                    "community_health": evidence.get("community_health") or {},
                    "known_vulnerabilities": evidence.get("known_vulnerabilities") or [],
                    "vulnerability_signals": evidence.get("vulnerability_signals") or {},
                }
            )
    return candidates
