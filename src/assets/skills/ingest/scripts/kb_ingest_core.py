#!/usr/bin/env python3
"""Helpers for ingesting materials into the LLM wiki knowledge base."""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
PACKAGE_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PLACEHOLDER_TEXT = "No text could be extracted."
THEME_CATEGORIES = ("general", "project", "research")
THEME_INDEX_HEADINGS = {
    "general": "通用主题",
    "project": "项目型主题",
    "research": "研究型主题",
}
THEME_HOME_LABELS = {
    "general": "通用主题",
    "project": "项目主题",
    "research": "研究主题",
}
DEFAULT_THEME_TAGS = {
    "general": ["general", "reusable"],
    "project": ["project", "engineering"],
    "research": ["research", "learning"],
}
CANONICAL_NODE_DIRS = {
    "entity": "shared/entities",
    "concept": "shared/concepts",
}
CANONICAL_NODE_TEMPLATES = {
    "entity": "entity-page.template.md",
    "concept": "concept-page.template.md",
}
CANONICAL_BODY_LINK_SECTION = "## 相关页面"
THEME_LINK_SECTION = "## 关联实体与概念"
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
SUGGESTION_GENERIC_TERMS = {
    "readme",
    "overview",
    "主题概览",
    "术语表",
    "open questions",
    "faq",
    "open questions",
    "recent updates",
    "sources",
    "document intake",
    "tools",
    "workflows",
    "architecture",
    "concepts",
    "comparisons",
    "experiments",
    "decisions",
    "modules",
    "playbooks",
    "summary",
    "next steps",
    "weekly summary",
    "knowledge base",
    "shared knowledge",
}
CONCEPT_HINTS = (
    "evaluation",
    "observability",
    "grounded",
    "benchmark",
    "pattern",
    "method",
    "workflow",
    "rubric",
    "metric",
    "architecture",
    "engineering",
    "prompt",
    "prompting",
    "reasoning",
    "planning",
    "alignment",
    "safety",
    "retrieval",
    "memory",
    "orchestration",
    "design",
    "principle",
)
ENTITY_HINTS = ("judge", "agent", "model", "service", "system", "platform", "pipeline", "tool", "framework", "dataset", "protocol", "api", "sdk")
INBOX_TEXT_EXTENSIONS = {
    ".adoc",
    ".csv",
    ".doc",
    ".docx",
    ".json",
    ".md",
    ".mdx",
    ".pdf",
    ".rst",
    ".tex",
    ".tsv",
    ".txt",
    ".xls",
    ".xlsx",
    ".yaml",
    ".yml",
}
INBOX_SOURCE_CODE_EXTENSIONS = {
    ".astro",
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".graphql",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".mjs",
    ".mts",
    ".php",
    ".proto",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".svelte",
    ".ts",
    ".tsx",
    ".vue",
}
INBOX_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tif", ".tiff", ".heic"}
INBOX_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
INBOX_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
INBOX_ARCHIVE_EXTENSIONS = {".zip", ".tar", ".tgz", ".gz", ".7z", ".rar"}
INBOX_MANIFEST_NAMES = {
    "package.json",
    "pyproject.toml",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "requirements.txt",
    "dockerfile",
    "makefile",
}
REQUIREMENT_HINTS = (
    "需求",
    "需求文档",
    "需求说明",
    "需求说明书",
    "产品需求",
    "业务需求",
    "功能需求",
    "非功能",
    "验收",
    "验收标准",
    "验收条件",
    "用户故事",
    "用例",
    "权限矩阵",
    "接口需求",
    "prd",
    "srs",
    "brd",
    "mrd",
    "requirement",
    "requirements",
    "spec",
    "acceptance criteria",
    "user story",
    "user stories",
    "must have",
    "should have",
)
PAPER_HINTS = (
    "abstract",
    "references",
    "doi",
    "arxiv",
    "论文",
    "摘要",
    "参考文献",
    "实验",
    "方法",
)
ARTICLE_HINTS = (
    "article",
    "blog",
    "post",
    "essay",
    "newsletter",
    "文章",
    "博客",
    "专栏",
    "观点",
)
LEARNING_HINTS = (
    "course",
    "tutorial",
    "lesson",
    "slides",
    "study",
    "学习",
    "教程",
    "课程",
    "课件",
    "笔记",
)


COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from kb_activity_log import append_activity_log


@dataclass
class ThemeSummary:
    name: str
    category: str
    relative_path: str
    theme_type: str
    readme_exists: bool
    meta_exists: bool
    overview_exists: bool
    source_file_count: int
    wiki_file_count: int
    stack_file_count: int
    output_file_count: int



def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def normalize_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.replace("\r", "\n").split("\n")]
    collapsed = "\n".join(line for line in lines if line)
    return collapsed.strip()


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def slugify_title(title: str) -> str:
    text = title.strip().lower()
    text = re.sub(r"[ _/]+", "-", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff-]+", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "untitled-theme"


def extract_theme_type(meta_path: Path) -> str:
    if not meta_path.exists():
        return "unknown"
    for line in read_text(meta_path).splitlines():
        if line.startswith("theme_type:"):
            return line.split(":", 1)[1].strip() or "unknown"
    return "unknown"


def theme_dir_name_sort_key(path: Path) -> tuple[int, str]:
    match = re.match(r"^\s*(\d+)[.-]\s*(.+)$", path.name)
    if match:
        return int(match.group(1)), match.group(2).lower()
    return 10_000, path.name.lower()


def parse_theme_sequence(path: Path) -> int | None:
    match = re.match(r"^\s*(\d+)[.-].+$", path.name)
    if not match:
        return None
    return int(match.group(1))


def build_theme_dir_name(root: Path, category: str, title: str) -> str:
    return f"{next_theme_number(root, category):02d}-{slugify_title(title)}"


def theme_slug_from_dir_name(theme_dir_name: str) -> str:
    return re.sub(r"^\d+-", "", theme_dir_name)


def theme_readme_link(category: str, theme_name: str) -> str:
    return f"[[themes/{category}/{theme_name}/README|{theme_name}]]"


def iter_theme_dirs(root: Path) -> list[tuple[str, Path]]:
    themes_dir = root / "themes"
    if not themes_dir.exists():
        return []

    discovered: list[tuple[str, Path]] = []
    for category_dir in sorted((p for p in themes_dir.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        if category_dir.name in THEME_CATEGORIES:
            children = sorted((p for p in category_dir.iterdir() if p.is_dir()), key=theme_dir_name_sort_key)
            for theme_dir in children:
                discovered.append((category_dir.name, theme_dir))
            continue

        # Backward-compatible fallback for unexpected one-level themes.
        discovered.append(("uncategorized", category_dir))

    return discovered


def next_theme_number(root: Path, category: str) -> int:
    base_dir = root / "themes" / category
    if not base_dir.exists():
        return 0
    numbers = [
        number
        for number in (parse_theme_sequence(path) for path in base_dir.iterdir() if path.is_dir())
        if number is not None
    ]
    return (max(numbers) + 1) if numbers else 0


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = value.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def normalize_tag_inputs(tags: list[str]) -> list[str]:
    expanded: list[str] = []
    for item in tags:
        expanded.extend(part.strip() for part in item.split(","))
    return unique_preserve_order(expanded)


def split_frontmatter(document: str) -> tuple[list[str], str]:
    lines = document.splitlines()
    if not lines or lines[0].strip() != "---":
        return [], document.rstrip()
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return lines[1:idx], "\n".join(lines[idx + 1 :]).strip()
    return [], document.rstrip()


def replace_frontmatter_block(frontmatter_lines: list[str], key: str, new_block: list[str]) -> list[str]:
    key_pattern = re.compile(rf"^{re.escape(key)}:")
    next_key_pattern = re.compile(r"^[A-Za-z0-9_-]+:")
    start = None
    for idx, line in enumerate(frontmatter_lines):
        if key_pattern.match(line):
            start = idx
            break

    if start is None:
        return frontmatter_lines + new_block

    end = start + 1
    while end < len(frontmatter_lines) and not next_key_pattern.match(frontmatter_lines[end]):
        end += 1
    return frontmatter_lines[:start] + new_block + frontmatter_lines[end:]


def extract_frontmatter_block(frontmatter_lines: list[str], key: str) -> list[str]:
    key_pattern = re.compile(rf"^{re.escape(key)}:")
    next_key_pattern = re.compile(r"^[A-Za-z0-9_-]+:")
    start = None
    for idx, line in enumerate(frontmatter_lines):
        if key_pattern.match(line):
            start = idx
            break
    if start is None:
        return []
    end = start + 1
    while end < len(frontmatter_lines) and not next_key_pattern.match(frontmatter_lines[end]):
        end += 1
    return frontmatter_lines[start:end]


def parse_frontmatter_list(frontmatter_lines: list[str], key: str) -> list[str]:
    block = extract_frontmatter_block(frontmatter_lines, key)
    if not block:
        return []
    values: list[str] = []
    first = block[0].split(":", 1)[1].strip()
    if first and first != "[]":
        values.append(first)
    for line in block[1:]:
        stripped = line.strip()
        if stripped.startswith("- "):
            values.append(stripped[2:].strip())
    return unique_preserve_order(values)


def parse_frontmatter_scalar(frontmatter_lines: list[str], key: str) -> str | None:
    block = extract_frontmatter_block(frontmatter_lines, key)
    if not block:
        return None
    value = block[0].split(":", 1)[1].strip()
    return value or None


def build_frontmatter_document(frontmatter_lines: list[str], body: str) -> str:
    return "---\n" + "\n".join(frontmatter_lines).rstrip() + "\n---\n\n" + body.rstrip() + "\n"


def build_frontmatter_list_block(key: str, values: list[str]) -> list[str]:
    normalized = unique_preserve_order(values)
    if not normalized:
        return [f"{key}: []"]
    return [f"{key}:", *[f"  - {value}" for value in normalized]]


def normalize_reference(reference: str, root: Path | None = None) -> str:
    raw = reference.strip().replace("\\", "/")
    if not raw:
        return ""
    path = Path(raw)
    if path.is_absolute():
        if root is None:
            raise ValueError("Absolute references require the knowledge base root for normalization.")
        path = path.resolve().relative_to(root.resolve())
        raw = path.as_posix()
    raw = raw.lstrip("./")
    if raw.endswith(".md"):
        raw = raw[:-3]
    return raw.strip("/")


def resolve_markdown_ref(root: Path, reference: str) -> Path:
    normalized = normalize_reference(reference, root)
    path = root / normalized
    if path.suffix.lower() != ".md":
        path = path.with_suffix(".md")
    return path


def infer_theme_readme_ref_from_page(root: Path, reference: str) -> str | None:
    page_path = resolve_markdown_ref(root, reference)
    current = page_path.parent
    for candidate in [current, *current.parents]:
        if candidate == root.parent:
            break
        if (candidate / "README.md").exists() and (candidate / "meta.md").exists():
            return normalize_reference((candidate / "README.md").resolve().relative_to(root.resolve()).as_posix(), root)
        if candidate == root:
            break
    return None


def theme_ref_from_readme_ref(theme_readme_ref: str) -> str:
    normalized = normalize_reference(theme_readme_ref)
    return normalized[:-7] if normalized.endswith("/README") else normalized


def display_name_from_ref(reference: str) -> str:
    normalized = normalize_reference(reference)
    path = Path(normalized)
    if path.name.lower() == "readme" and path.parent.name:
        return path.parent.name
    slug = path.name.replace("-", " ").strip()
    return " ".join(part.upper() if part.isupper() else part.capitalize() for part in slug.split())


def canonical_node_type_from_ref(reference: str) -> str:
    normalized = normalize_reference(reference)
    if normalized.startswith("shared/entities/"):
        return "entity"
    if normalized.startswith("shared/concepts/"):
        return "concept"
    raise ValueError(f"Unsupported canonical ref for B-2 operations: {reference}")


def read_markdown_frontmatter(path: Path) -> tuple[list[str], str]:
    if not path.exists():
        return [], ""
    return split_frontmatter(read_text(path))


def remove_code_fences(text: str) -> str:
    return re.sub(r"```[\s\S]*?```", " ", text)


def strip_wikilinks(text: str) -> str:
    return WIKILINK_RE.sub(" ", text)


def list_canonical_pages(root: Path) -> list[tuple[str, str, Path]]:
    discovered: list[tuple[str, str, Path]] = []
    for node_type, relative_dir in CANONICAL_NODE_DIRS.items():
        base_dir = root / relative_dir
        if not base_dir.exists():
            continue
        for path in sorted(base_dir.glob("*.md"), key=lambda item: item.name.lower()):
            discovered.append((node_type, normalize_reference(path.relative_to(root).as_posix(), root), path))
    return discovered


def build_canonical_registry(root: Path) -> dict[str, dict[str, str]]:
    registry: dict[str, dict[str, str]] = {}
    for node_type, canonical_ref, path in list_canonical_pages(root):
        frontmatter_lines, _ = read_markdown_frontmatter(path)
        title = parse_frontmatter_scalar(frontmatter_lines, "title") or display_name_from_ref(canonical_ref)
        aliases = parse_frontmatter_list(frontmatter_lines, "aliases")
        for name in unique_preserve_order([title] + aliases):
            registry[name.lower()] = {
                "title": title,
                "canonical_ref": canonical_ref,
                "node_type": node_type,
            }
    return registry


def infer_node_type_for_term(term: str) -> str:
    lowered = term.lower()
    concept_score = sum(1 for hint in CONCEPT_HINTS if hint in lowered)
    entity_score = sum(1 for hint in ENTITY_HINTS if hint in lowered)
    words = [part for part in re.split(r"[\s/-]+", lowered) if part]

    # Prefer concept pages for long topical phrases unless the entity signal is clearly stronger.
    if len(words) >= 5:
        concept_score += 1
    if " for " in f" {lowered} ":
        concept_score += 1
    if any(token in {"agent", "model", "service", "system", "platform", "dataset", "tool"} for token in words):
        entity_score += 1

    if concept_score >= entity_score:
        return "concept"
    return "entity"


def preferred_canonical_ref_for_term(node_type: str, term: str) -> str:
    return f"{CANONICAL_NODE_DIRS[node_type]}/{slugify_title(term)}"


def suggest_tags_for_term(node_type: str, term: str) -> list[str]:
    lowered = term.lower()
    tags = [node_type]
    for hint in CONCEPT_HINTS:
        if hint in lowered and hint not in tags:
            tags.append(hint)
    for hint in ENTITY_HINTS:
        if hint in lowered and hint not in tags:
            tags.append(hint)
    tags.append(slugify_title(term))
    return unique_preserve_order(tags)


def normalize_candidate_term(term: str) -> str:
    cleaned = term.strip().strip("`*_\"'()[]{}:;,.")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def is_valid_candidate_term(term: str) -> bool:
    cleaned = normalize_candidate_term(term)
    if not cleaned or len(cleaned) < 4:
        return False
    lowered = cleaned.lower()
    if lowered in SUGGESTION_GENERIC_TERMS:
        return False
    if "/" in cleaned or "\\" in cleaned:
        return False
    if cleaned.endswith(".md") or cleaned.startswith("."):
        return False
    if "<" in cleaned or ">" in cleaned:
        return False
    if cleaned.startswith("themes/") or cleaned.startswith("shared/"):
        return False
    if re.match(r"^\d{2}-", cleaned):
        return False
    if re.fullmatch(r"[0-9 ._-]+", cleaned):
        return False
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", cleaned):
        return False
    if "待补充" in cleaned or "术语" == cleaned:
        return False
    return True


def extract_candidate_terms_from_markdown(text: str) -> list[str]:
    working = remove_code_fences(text)
    working = strip_wikilinks(working)
    patterns = [
        re.compile(r"`([^`\n]{3,80})`"),
        re.compile(r"\b(?:[A-Z]{2,}|[A-Z][a-z]+)(?:[- ][A-Z0-9][A-Za-z0-9]+)+\b"),
        re.compile(r"^#\s+(.+)$", re.MULTILINE),
    ]
    results: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(working):
            candidate = match.group(1) if match.lastindex else match.group(0)
            normalized = normalize_candidate_term(candidate)
            if is_valid_candidate_term(normalized):
                results.append(normalized)
    return results


def discover_theme_markdown_pages(root: Path, theme_readme_ref: str) -> list[str]:
    readme_path = resolve_markdown_ref(root, theme_readme_ref)
    if not readme_path.exists():
        raise FileNotFoundError(f"Theme readme does not exist: {readme_path}")
    theme_dir = readme_path.parent
    pages = [normalize_reference(readme_path.relative_to(root).as_posix(), root)]
    wiki_dir = theme_dir / "wiki"
    if wiki_dir.exists():
        pages.extend(
            normalize_reference(path.relative_to(root).as_posix(), root)
            for path in sorted(wiki_dir.rglob("*.md"), key=lambda item: item.as_posix().lower())
        )
    return unique_preserve_order(pages)


def build_suggestion_command(theme_readme_ref: str | None, page_ref: str, title: str, node_type: str) -> str:
    command = f'promote-{node_type} --title "{title}"'
    if theme_readme_ref:
        command += f" --theme {theme_readme_ref}"
    command += f" --source-page {page_ref} --link-page {page_ref}"
    for tag in suggest_tags_for_term(node_type, title)[1:-1]:
        command += f" --tag {tag}"
    return command


def suggest_canonical_nodes(
    root: Path,
    *,
    theme_ref: str | None,
    page_refs: list[str],
    limit: int,
    include_existing: bool,
) -> dict[str, Any]:
    pages = unique_preserve_order([normalize_reference(item, root) for item in page_refs if normalize_reference(item, root)])
    theme_readme_ref = normalize_reference(theme_ref, root) if theme_ref else None
    if theme_readme_ref and theme_readme_ref not in pages:
        pages = unique_preserve_order(discover_theme_markdown_pages(root, theme_readme_ref) + pages)
    if not pages:
        raise ValueError("Provide --theme or at least one --page for suggest-canonical-nodes.")

    registry = build_canonical_registry(root)
    candidates: dict[str, dict[str, Any]] = {}
    for page_ref in pages:
        page_path = resolve_markdown_ref(root, page_ref)
        if not page_path.exists():
            continue
        _, body = read_markdown_frontmatter(page_path)
        page_text = body or read_text(page_path)
        for term in extract_candidate_terms_from_markdown(page_text):
            key = term.lower()
            info = candidates.setdefault(
                key,
                {
                    "title": term,
                    "pages": [],
                    "hits": 0,
                },
            )
            info["hits"] += 1
            if page_ref not in info["pages"]:
                info["pages"].append(page_ref)

    suggestions: list[dict[str, Any]] = []
    for key, info in candidates.items():
        existing = registry.get(key)
        if existing and not include_existing:
            continue
        node_type = existing["node_type"] if existing else infer_node_type_for_term(info["title"])
        primary_page = info["pages"][0]
        suggestion = {
            "title": info["title"],
            "suggested_node_type": node_type,
            "preferred_canonical_ref": existing["canonical_ref"] if existing else preferred_canonical_ref_for_term(node_type, info["title"]),
            "page_count": len(info["pages"]),
            "hits": info["hits"],
            "pages": info["pages"],
            "existing_canonical_ref": existing["canonical_ref"] if existing else None,
            "recommended_action": "link-existing" if existing else f"promote-{node_type}",
            "suggested_tags": suggest_tags_for_term(node_type, info["title"]),
            "command": (
                f'link-canonical --page {primary_page} --canonical {existing["canonical_ref"]} --label "{existing["title"]}"'
                if existing
                else build_suggestion_command(theme_readme_ref, primary_page, info["title"], node_type)
            ),
        }
        suggestions.append(suggestion)

    suggestions.sort(key=lambda item: (-item["page_count"], -item["hits"], item["title"].lower()))
    return {
        "theme": theme_ref_from_readme_ref(theme_readme_ref) if theme_readme_ref else None,
        "theme_readme": theme_readme_ref,
        "pages_scanned": pages,
        "suggestions": suggestions[:limit],
    }


def extract_canonical_links_from_text(text: str) -> list[tuple[str, str | None]]:
    results: list[tuple[str, str | None]] = []
    for match in WIKILINK_RE.finditer(text):
        target = normalize_reference(match.group(1))
        if target.startswith("shared/entities/") or target.startswith("shared/concepts/"):
            results.append((target, match.group(2)))
    return results


def batch_link_canonical_pages(root: Path, *, page_refs: list[str], canonical_refs: list[str]) -> dict[str, Any]:
    pages = unique_preserve_order([normalize_reference(item, root) for item in page_refs if normalize_reference(item, root)])
    canonicals = unique_preserve_order([normalize_reference(item, root) for item in canonical_refs if normalize_reference(item, root)])
    results: list[dict[str, Any]] = []
    for canonical_ref in canonicals:
        for page_ref in pages:
            results.append(link_canonical_page(root, page_ref=page_ref, canonical_ref=canonical_ref))
    return {
        "pages": pages,
        "canonicals": canonicals,
        "linked_pairs": results,
        "link_count": len(results),
    }


def sync_theme_graph(root: Path, *, theme_readme_ref: str, page_refs: list[str]) -> dict[str, Any]:
    normalized_theme_readme = normalize_reference(theme_readme_ref, root)
    pages = (
        unique_preserve_order([normalize_reference(item, root) for item in page_refs if normalize_reference(item, root)])
        if page_refs
        else discover_theme_markdown_pages(root, normalized_theme_readme)
    )
    if normalized_theme_readme not in pages:
        pages = unique_preserve_order([normalized_theme_readme] + pages)

    found_links: dict[str, dict[str, Any]] = {}
    for page_ref in pages:
        page_path = resolve_markdown_ref(root, page_ref)
        if not page_path.exists():
            continue
        text = read_text(page_path)
        for canonical_ref, label in extract_canonical_links_from_text(text):
            item = found_links.setdefault(canonical_ref, {"label": label, "pages": []})
            if label and not item["label"]:
                item["label"] = label
            if page_ref not in item["pages"]:
                item["pages"].append(page_ref)

    linked_pairs: list[dict[str, Any]] = []
    for canonical_ref, item in sorted(found_links.items()):
        for page_ref in item["pages"]:
            linked_pairs.append(link_canonical_page(root, page_ref=page_ref, canonical_ref=canonical_ref, label=item["label"]))
        if normalized_theme_readme not in item["pages"]:
            linked_pairs.append(link_canonical_page(root, page_ref=normalized_theme_readme, canonical_ref=canonical_ref, label=item["label"]))

    return {
        "theme_readme": normalized_theme_readme,
        "pages_scanned": pages,
        "canonical_refs": sorted(found_links.keys()),
        "linked_pairs": linked_pairs,
        "link_count": len(linked_pairs),
    }


def build_wikilink(reference: str, label: str | None = None) -> str:
    normalized = normalize_reference(reference)
    return f"[[{normalized}|{label or display_name_from_ref(normalized)}]]"


def canonical_link_terms(title: str, aliases: list[str]) -> list[str]:
    return sorted(unique_preserve_order([title] + aliases), key=lambda item: (-len(item), item.lower()))


def replace_first_naked_mention(body: str, *, canonical_ref: str, label: str, aliases: list[str]) -> tuple[str, bool]:
    lines = body.splitlines()
    in_code_fence = False
    replacement = build_wikilink(canonical_ref, label)
    terms = canonical_link_terms(label, aliases)

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence or not stripped or stripped.startswith("#"):
            continue
        if canonical_ref in line or "[[" in line or "`" in line:
            continue
        for term in terms:
            if len(term) < 4:
                continue
            pattern = re.compile(rf"(?<![\w/]){re.escape(term)}(?![\w/])", re.IGNORECASE)
            if pattern.search(line):
                lines[idx] = pattern.sub(replacement, line, count=1)
                return "\n".join(lines), True
    return body, False


def patch_page_with_canonical_link(
    root: Path,
    *,
    page_ref: str,
    canonical_ref: str,
    label: str | None = None,
    aliases: list[str] | None = None,
    add_section_fallback: bool = True,
) -> dict[str, Any]:
    normalized_page = normalize_reference(page_ref, root)
    normalized_canonical = normalize_reference(canonical_ref, root)
    page_path = resolve_markdown_ref(root, normalized_page)
    canonical_path = resolve_markdown_ref(root, normalized_canonical)
    if not page_path.exists():
        raise FileNotFoundError(f"Theme page does not exist: {page_path}")
    if not canonical_path.exists():
        raise FileNotFoundError(f"Canonical page does not exist: {canonical_path}")

    canonical_frontmatter, _ = read_markdown_frontmatter(canonical_path)
    canonical_title = parse_frontmatter_scalar(canonical_frontmatter, "title") or display_name_from_ref(normalized_canonical)
    canonical_status = parse_frontmatter_scalar(canonical_frontmatter, "status") or "active"
    canonical_aliases = parse_frontmatter_list(canonical_frontmatter, "aliases")
    link_label = label or canonical_title

    document = read_text(page_path)
    frontmatter_lines, body = split_frontmatter(document)
    target_body = body if frontmatter_lines else document.rstrip()
    patched_body, replaced_inline = replace_first_naked_mention(
        target_body,
        canonical_ref=normalized_canonical,
        label=link_label,
        aliases=aliases or canonical_aliases,
    )
    added_section_link = False
    if add_section_fallback and normalized_canonical not in patched_body:
        patched_body = ensure_section_bullets(patched_body, THEME_LINK_SECTION, [build_wikilink(normalized_canonical, link_label)])
        added_section_link = True

    if frontmatter_lines:
        updated_document = build_frontmatter_document(frontmatter_lines, patched_body)
    else:
        updated_document = patched_body.rstrip() + "\n"
    if updated_document != document:
        page_path.write_text(updated_document, encoding="utf-8")

    return {
        "page": normalized_page,
        "canonical_ref": normalized_canonical,
        "label": link_label,
        "status": canonical_status,
        "page_path": page_path.relative_to(root).as_posix(),
        "replaced_inline": replaced_inline,
        "added_section_link": added_section_link,
    }


def auto_link_theme_mentions(
    root: Path,
    *,
    theme_readme_ref: str | None,
    canonical_ref: str,
    label: str | None = None,
    aliases: list[str] | None = None,
    exclude_pages: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not theme_readme_ref:
        return []
    excluded = {normalize_reference(item, root) for item in (exclude_pages or []) if item}
    patched: list[dict[str, Any]] = []
    for page_ref in discover_theme_markdown_pages(root, theme_readme_ref):
        if page_ref in excluded:
            continue
        result = patch_page_with_canonical_link(
            root,
            page_ref=page_ref,
            canonical_ref=canonical_ref,
            label=label,
            aliases=aliases,
            add_section_fallback=False,
        )
        if result["replaced_inline"]:
            patched.append(result)
    return patched


def ensure_section_bullets(body: str, heading: str, bullets: list[str]) -> str:
    text = body.rstrip()
    existing_bullets = unique_preserve_order([bullet for bullet in bullets if bullet.strip()])
    if not existing_bullets:
        return text + ("\n" if text else "")

    for bullet in existing_bullets:
        if bullet in text:
            existing_bullets = [item for item in existing_bullets if item != bullet]
    if not existing_bullets:
        return text + ("\n" if text else "")

    lines = text.splitlines() if text else []
    heading_index = next((idx for idx, line in enumerate(lines) if line.strip() == heading), None)
    bullet_lines = [f"- {bullet}" for bullet in existing_bullets]

    if heading_index is None:
        prefix = text + "\n\n" if text else ""
        return prefix + heading + "\n\n" + "\n".join(bullet_lines) + "\n"

    insert_at = len(lines)
    for idx in range(heading_index + 1, len(lines)):
        if lines[idx].startswith("## "):
            insert_at = idx
            break
    insert_lines = []
    if insert_at == heading_index + 1 or lines[heading_index + 1].strip():
        insert_lines.append("")
    insert_lines.extend(bullet_lines)
    if insert_at < len(lines) and lines[insert_at - 1].strip():
        insert_lines.append("")
    lines[insert_at:insert_at] = insert_lines
    return "\n".join(lines).rstrip() + "\n"


def derive_theme_refs(root: Path, theme_refs: list[str], page_refs: list[str]) -> tuple[list[str], list[str]]:
    normalized_theme_readmes = [normalize_reference(item, root) for item in theme_refs if normalize_reference(item, root)]
    inferred_readmes = [
        infer_theme_readme_ref_from_page(root, page_ref)
        for page_ref in page_refs
    ]
    theme_readmes = unique_preserve_order(normalized_theme_readmes + [item for item in inferred_readmes if item])
    themes = unique_preserve_order([theme_ref_from_readme_ref(item) for item in theme_readmes])
    return themes, theme_readmes


def strip_template_preamble(template: str) -> str:
    lines = template.splitlines()
    if lines and lines[0].startswith("# ") and "template" in lines[0].lower():
        for idx, line in enumerate(lines):
            if line.strip() == "---":
                return "\n".join(lines[idx:])
    return template


def render_canonical_page_from_template(
    root: Path,
    *,
    node_type: str,
    title: str,
    slug: str,
    aliases: list[str],
    tags: list[str],
    status: str,
    themes: list[str],
    theme_readmes: list[str],
    related_entities: list[str],
    related_concepts: list[str],
    related_patterns: list[str],
    related_methods: list[str],
    source_pages: list[str],
    evidence_from: list[str],
) -> str:
    template_name = CANONICAL_NODE_TEMPLATES[node_type]
    template_path = root / "schema" / "templates" / template_name
    template = read_text(template_path) if template_path.exists() else f"# {title}\n"
    template = strip_template_preamble(template)
    today = datetime.now().strftime("%Y-%m-%d")

    sample_theme = themes[0] if themes else "themes/general/00-example"
    sample_parts = sample_theme.split("/")
    sample_category = sample_parts[1] if len(sample_parts) > 1 else "general"
    sample_theme_name = sample_parts[2] if len(sample_parts) > 2 else "00-example"

    replacements = {
        "<entity-title>": title,
        "<Entity Title>": title,
        "<concept-title>": title,
        "<Concept Title>": title,
        "<alias-1>": aliases[0] if aliases else slug,
        "<tag-1>": tags[0] if tags else node_type,
        "<category>": sample_category,
        "<nn-theme-name>": sample_theme_name,
        "<related-entity>": Path(related_entities[0]).name if related_entities else "related-entity",
        "<related-concept>": Path(related_concepts[0]).name if related_concepts else "related-concept",
        "<related-pattern>": Path(related_patterns[0]).name if related_patterns else "related-pattern",
        "<related-method>": Path(related_methods[0]).name if related_methods else "related-method",
        "<path-to-source>": Path(evidence_from[0]).name if evidence_from else "path-to-source",
        "<YYYY-MM-DD>": today,
        "<link-to-theme-readme>": build_wikilink(theme_readmes[0]) if theme_readmes else "待补充",
        "<link-to-related-concept>": build_wikilink(related_concepts[0]) if related_concepts else "待补充",
        "<link-to-related-entity>": build_wikilink(related_entities[0]) if related_entities else "待补充",
    }
    document = apply_template_replacements(template, replacements)
    frontmatter_lines, body = split_frontmatter(document)
    if not frontmatter_lines:
        frontmatter_lines = []
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "title", [f"title: {title}"])
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "node_type", [f"node_type: {node_type}"])
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "status", [f"status: {status}"])
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "aliases", build_frontmatter_list_block("aliases", aliases))
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "tags", build_frontmatter_list_block("tags", tags))
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "themes", build_frontmatter_list_block("themes", themes))
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "related_entities", build_frontmatter_list_block("related_entities", related_entities))
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "related_concepts", build_frontmatter_list_block("related_concepts", related_concepts))
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "related_patterns", build_frontmatter_list_block("related_patterns", related_patterns))
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "related_methods", build_frontmatter_list_block("related_methods", related_methods))
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "related_themes", build_frontmatter_list_block("related_themes", theme_readmes))
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "source_pages", build_frontmatter_list_block("source_pages", source_pages))
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "evidence_from", build_frontmatter_list_block("evidence_from", evidence_from))
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "supersedes", ["supersedes: []"])
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "contradicts", ["contradicts: []"])
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "updated", [f"updated: {today}"])

    body_links = [build_wikilink(item) for item in theme_readmes]
    body_links.extend(build_wikilink(item) for item in source_pages if item not in theme_readmes)
    body = ensure_section_bullets(body, CANONICAL_BODY_LINK_SECTION, body_links)
    return build_frontmatter_document(frontmatter_lines, body)


def upsert_canonical_page(
    root: Path,
    *,
    node_type: str,
    title: str,
    slug: str | None,
    aliases: list[str],
    tags: list[str],
    status: str,
    theme_refs: list[str],
    page_refs: list[str],
    evidence_from: list[str],
    related_entities: list[str],
    related_concepts: list[str],
    related_patterns: list[str],
    related_methods: list[str],
) -> dict[str, Any]:
    if node_type not in CANONICAL_NODE_DIRS:
        raise ValueError(f"Unsupported canonical node type: {node_type}")

    canonical_slug = slugify_title(slug or title)
    canonical_ref = f"{CANONICAL_NODE_DIRS[node_type]}/{canonical_slug}"
    canonical_path = resolve_markdown_ref(root, canonical_ref)
    normalized_pages = unique_preserve_order([normalize_reference(item, root) for item in page_refs if normalize_reference(item, root)])
    themes, theme_readmes = derive_theme_refs(root, theme_refs, normalized_pages)
    if not themes and not normalized_pages:
        raise ValueError("Provide at least one --theme or --link-page/--source-page so the canonical node has context.")

    normalized_aliases = unique_preserve_order(aliases + [title])
    normalized_tags = unique_preserve_order([node_type] + normalize_tag_inputs(tags) + [canonical_slug])
    normalized_related_entities = unique_preserve_order([normalize_reference(item, root) for item in related_entities if normalize_reference(item, root)])
    normalized_related_concepts = unique_preserve_order([normalize_reference(item, root) for item in related_concepts if normalize_reference(item, root)])
    normalized_related_patterns = unique_preserve_order([normalize_reference(item, root) for item in related_patterns if normalize_reference(item, root)])
    normalized_related_methods = unique_preserve_order([normalize_reference(item, root) for item in related_methods if normalize_reference(item, root)])
    normalized_evidence = unique_preserve_order([normalize_reference(item, root) for item in evidence_from if normalize_reference(item, root)])
    existed = canonical_path.exists()

    if existed:
        document = read_text(canonical_path)
        frontmatter_lines, body = split_frontmatter(document)
        if not frontmatter_lines:
            frontmatter_lines = []
        normalized_aliases = unique_preserve_order(parse_frontmatter_list(frontmatter_lines, "aliases") + normalized_aliases)
        normalized_tags = unique_preserve_order(parse_frontmatter_list(frontmatter_lines, "tags") + normalized_tags)
        themes = unique_preserve_order(parse_frontmatter_list(frontmatter_lines, "themes") + themes)
        theme_readmes = unique_preserve_order(parse_frontmatter_list(frontmatter_lines, "related_themes") + theme_readmes)
        normalized_pages = unique_preserve_order(parse_frontmatter_list(frontmatter_lines, "source_pages") + normalized_pages)
        normalized_evidence = unique_preserve_order(parse_frontmatter_list(frontmatter_lines, "evidence_from") + normalized_evidence)
        normalized_related_entities = unique_preserve_order(parse_frontmatter_list(frontmatter_lines, "related_entities") + normalized_related_entities)
        normalized_related_concepts = unique_preserve_order(parse_frontmatter_list(frontmatter_lines, "related_concepts") + normalized_related_concepts)
        normalized_related_patterns = unique_preserve_order(parse_frontmatter_list(frontmatter_lines, "related_patterns") + normalized_related_patterns)
        normalized_related_methods = unique_preserve_order(parse_frontmatter_list(frontmatter_lines, "related_methods") + normalized_related_methods)
        today = datetime.now().strftime("%Y-%m-%d")
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "title", [f"title: {title}"])
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "node_type", [f"node_type: {node_type}"])
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "status", [f"status: {status}"])
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "aliases", build_frontmatter_list_block("aliases", normalized_aliases))
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "tags", build_frontmatter_list_block("tags", normalized_tags))
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "themes", build_frontmatter_list_block("themes", themes))
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "related_entities", build_frontmatter_list_block("related_entities", normalized_related_entities))
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "related_concepts", build_frontmatter_list_block("related_concepts", normalized_related_concepts))
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "related_patterns", build_frontmatter_list_block("related_patterns", normalized_related_patterns))
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "related_methods", build_frontmatter_list_block("related_methods", normalized_related_methods))
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "related_themes", build_frontmatter_list_block("related_themes", theme_readmes))
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "source_pages", build_frontmatter_list_block("source_pages", normalized_pages))
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "evidence_from", build_frontmatter_list_block("evidence_from", normalized_evidence))
        frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "updated", [f"updated: {today}"])
        body_links = [build_wikilink(item) for item in theme_readmes]
        body_links.extend(build_wikilink(item) for item in normalized_pages if item not in theme_readmes)
        body = ensure_section_bullets(body, CANONICAL_BODY_LINK_SECTION, body_links)
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        canonical_path.write_text(build_frontmatter_document(frontmatter_lines, body), encoding="utf-8")
    else:
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        canonical_path.write_text(
            render_canonical_page_from_template(
                root,
                node_type=node_type,
                title=title,
                slug=canonical_slug,
                aliases=normalized_aliases,
                tags=normalized_tags,
                status=status,
                themes=themes,
                theme_readmes=theme_readmes,
                related_entities=normalized_related_entities,
                related_concepts=normalized_related_concepts,
                related_patterns=normalized_related_patterns,
                related_methods=normalized_related_methods,
                source_pages=normalized_pages,
                evidence_from=normalized_evidence,
            ),
            encoding="utf-8",
        )

    return {
        "node_type": node_type,
        "title": title,
        "slug": canonical_slug,
        "canonical_ref": canonical_ref,
        "canonical_path": canonical_path.relative_to(root).as_posix(),
        "themes": themes,
        "related_themes": theme_readmes,
        "source_pages": normalized_pages,
        "evidence_from": normalized_evidence,
        "related_entities": normalized_related_entities,
        "related_concepts": normalized_related_concepts,
        "related_patterns": normalized_related_patterns,
        "related_methods": normalized_related_methods,
        "tags": normalized_tags,
        "aliases": normalized_aliases,
        "status": status,
        "created": not existed,
    }


def link_canonical_page(root: Path, *, page_ref: str, canonical_ref: str, label: str | None = None) -> dict[str, Any]:
    normalized_page = normalize_reference(page_ref, root)
    normalized_canonical = normalize_reference(canonical_ref, root)
    canonical_path = resolve_markdown_ref(root, normalized_canonical)
    if not canonical_path.exists():
        raise FileNotFoundError(f"Canonical page does not exist: {canonical_path}")

    canonical_frontmatter, _ = read_markdown_frontmatter(canonical_path)
    canonical_title = parse_frontmatter_scalar(canonical_frontmatter, "title") or display_name_from_ref(normalized_canonical)
    canonical_status = parse_frontmatter_scalar(canonical_frontmatter, "status") or "active"
    canonical_aliases = parse_frontmatter_list(canonical_frontmatter, "aliases")
    patched_page = patch_page_with_canonical_link(
        root,
        page_ref=normalized_page,
        canonical_ref=normalized_canonical,
        label=label or canonical_title,
        aliases=canonical_aliases,
        add_section_fallback=True,
    )

    theme_readme_ref = infer_theme_readme_ref_from_page(root, normalized_page)
    upsert_canonical_page(
        root,
        node_type=canonical_node_type_from_ref(normalized_canonical),
        title=canonical_title,
        slug=Path(normalized_canonical).name,
        aliases=[],
        tags=[],
        status=canonical_status,
        theme_refs=[theme_readme_ref] if theme_readme_ref else [],
        page_refs=[normalized_page],
        evidence_from=[],
        related_entities=[],
        related_concepts=[],
        related_patterns=[],
        related_methods=[],
    )

    return {
        "page": normalized_page,
        "canonical_ref": normalized_canonical,
        "label": patched_page["label"],
        "theme_readme": theme_readme_ref,
        "page_path": patched_page["page_path"],
        "replaced_inline": patched_page["replaced_inline"],
        "added_section_link": patched_page["added_section_link"],
    }

def build_theme_owners(owners: list[str]) -> list[str]:
    normalized = unique_preserve_order(owners)
    return normalized or ["your-name"]


def build_theme_tags(category: str, theme_dir_name: str, extra_tags: list[str]) -> list[str]:
    slug = theme_slug_from_dir_name(theme_dir_name)
    return unique_preserve_order(DEFAULT_THEME_TAGS[category] + normalize_tag_inputs(extra_tags) + [slug])


def apply_template_replacements(template: str, replacements: dict[str, str]) -> str:
    content = template
    for old, new in replacements.items():
        content = content.replace(old, new)
    return content


def render_theme_readme(
    root: Path,
    category: str,
    title: str,
    theme_dir_name: str,
    owners: list[str],
    tags: list[str],
    status: str,
) -> str:
    template_path = root / "schema" / "templates" / f"{category}-theme.template.md"
    if template_path.exists():
        template = read_text(template_path)
    else:
        template = f"# {title}\n"

    today = datetime.now().strftime("%Y-%m-%d")
    slug = theme_slug_from_dir_name(theme_dir_name)
    replacements = {
        "<theme-name>": slug,
        "<通用主题名>": title,
        "<项目主题名>": title,
        "<研究主题名>": title,
        "<YYYY-MM-DD>": today,
        "- [[<related-theme-1>]]": "- 待补充",
        "- [[<related-theme-2>]]": "- 待补充",
    }
    document = apply_template_replacements(template, replacements)
    frontmatter_lines, body = split_frontmatter(document)
    if not frontmatter_lines:
        return document.rstrip() + "\n"

    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "status", [f"status: {status}"])
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "owners", ["owners:", *[f"  - {owner}" for owner in owners]])
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "tags", ["tags:", *[f"  - {tag}" for tag in tags]])
    frontmatter_lines = replace_frontmatter_block(frontmatter_lines, "updated", [f"updated: {today}"])
    return "---\n" + "\n".join(frontmatter_lines).rstrip() + "\n---\n\n" + body.rstrip() + "\n"


def build_meta_markdown(
    category: str,
    title: str,
    theme_dir_name: str,
    owners: list[str],
    tags: list[str],
    status: str,
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    slug = theme_slug_from_dir_name(theme_dir_name)
    lines = [
        "---",
        f"theme: {slug}",
        f"theme_type: {category}",
        f"status: {status}",
        "owners:",
        *[f"  - {owner}" for owner in owners],
        "tags:",
        *[f"  - {tag}" for tag in tags],
        f"updated: {today}",
        "---",
        "",
        "# 元信息",
        "",
        "## 基本信息",
        f"- 主题标题：{title}",
        f"- 主题目录：{theme_dir_name}",
        f"- 主题类型：{category}",
        f"- 主题路径：themes/{category}/{theme_dir_name}",
        f"- 初始化日期：{today}",
        "",
        "## 边界",
    ]

    if category == "general":
        lines.extend(
            [
                f"- 包含什么：围绕 `{title}` 的通用概念、模式、实践与可复用方法",
                "- 不包含什么：仅属于单个项目或单次实验的实现细节",
            ]
        )
    elif category == "project":
        lines.extend(
            [
                f"- 包含什么：围绕 `{title}` 的业务背景、架构、模块、决策与运维知识",
                "- 不包含什么：尚未确认归属的跨项目通用结论",
            ]
        )
    else:
        lines.extend(
            [
                f"- 包含什么：围绕 `{title}` 的研究问题、概念比较、实验记录与阶段性结论",
                "- 不包含什么：已经稳定沉淀为跨主题通用规范的内容",
            ]
        )

    lines.extend(
        [
            "",
            "## 输入来源",
            "- 主要来源类型：文档、笔记、代码、实验记录、外部资料",
            "- 更新方式：按主题持续增量维护",
            "",
            "## 输出目标",
        ]
    )

    if category == "general":
        lines.append("- 希望沉淀成什么：可跨主题复用的定义、模式、检查单与 FAQ")
    elif category == "project":
        lines.append("- 希望沉淀成什么：可支持协作、维护、排障与交接的项目知识地图")
    else:
        lines.append("- 希望沉淀成什么：可复盘、可比较、可追踪的研究结论与实验脉络")

    return "\n".join(lines).rstrip() + "\n"


def build_overview_markdown(category: str, title: str, theme_dir_name: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# 主题概览",
        "",
        "## 一句话总结",
        f"这里记录 `{title}` 的核心背景、关键资料、结构化知识入口与后续沉淀方向。",
        "",
        "## 当前重点",
        "- 明确主题范围与核心问题",
        "- 将后续资料归档到 `sources/` 并持续结构化更新",
        "- 优先维护 `README.md`、`meta.md` 与关键 wiki 页面",
        "",
        "## 核心知识地图",
        "- 主题入口：`../README.md`",
        "- 元信息：`../meta.md`",
        "- 原始资料：`../sources/`",
        "- 文档抽取产物：`../outputs/document-intake/`",
        "- 术语表：`glossary.md`",
        "- 待确认问题：`open-questions.md`",
    ]

    if category == "general":
        lines.append("- 常见问题：`faq.md`")
    elif category == "project":
        lines.append("- 架构页：`architecture.md`")

    lines.extend(
        [
            "",
            "## 最近更新",
            f"- {today}: 初始化 `{theme_dir_name}` 主题脚手架。",
        ]
    )

    if category == "general":
        lines.extend(
            [
                "",
                "## 建议下一步",
                "- 补充关键概念、模式与 FAQ",
                "- 将可复用经验抽象到 `wiki/patterns/` 或 `wiki/checklists/`",
                "- 识别可沉淀到 `shared/` 的共性知识",
            ]
        )
    elif category == "project":
        lines.extend(
            [
                "",
                "## 建议下一步",
                "- 补充 `architecture.md` 与模块说明",
                "- 记录关键决策、事故与操作手册",
                "- 持续维护技术栈、环境与周报摘要",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## 建议下一步",
                "- 明确研究问题、比较维度与实验计划",
                "- 将关键概念与实验记录结构化到对应子目录",
                "- 把阶段性结论沉淀到 `outputs/thesis.md`",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def build_glossary_markdown(title: str) -> str:
    return (
        "# 术语表\n\n"
        f"## `{title}` 相关术语\n"
        "- 术语：定义待补充\n"
        "- 术语：定义待补充\n"
    )


def build_open_questions_markdown(title: str) -> str:
    return (
        "# Open Questions\n\n"
        f"## `{title}` 当前待确认问题\n"
        "- 还缺哪些关键资料或证据？\n"
        "- 哪些结论仍需进一步验证？\n"
        "- 哪些部分可能需要拆成子页面？\n"
    )


def build_sources_readme_markdown(title: str) -> str:
    return (
        "# Sources\n\n"
        f"将 `{title}` 的原始资料保存在这里，保留原文件，不要直接改写。\n"
    )


def build_document_intake_readme_markdown(title: str) -> str:
    return (
        "# Document Intake\n\n"
        f"这里保存 `{title}` 相关文档的抽取产物，例如 PDF / DOCX / XLSX 的 `.extracted.md` 或 `.extracted.json`。\n"
    )


def build_general_faq_markdown(title: str) -> str:
    return (
        "# FAQ\n\n"
        f"## 关于 `{title}`\n"
        "- 这个主题解决什么问题？\n"
        "- 什么时候应该优先查看这个主题？\n"
        "- 哪些知识已经稳定，哪些仍待补充？\n"
    )


def build_general_stack_tools_markdown(title: str) -> str:
    return (
        "# Tools\n\n"
        f"记录 `{title}` 常用工具、命令、脚本与辅助资源。\n"
    )


def build_general_stack_workflows_markdown(title: str) -> str:
    return (
        "# Workflows\n\n"
        f"记录 `{title}` 的常见工作流、检查顺序和沉淀方式。\n"
    )


def build_general_summary_markdown(title: str) -> str:
    return (
        "# Summary\n\n"
        f"这里用于持续更新 `{title}` 的阶段性总结、关键判断和可复用结论。\n"
    )


def build_general_next_steps_markdown(title: str) -> str:
    return (
        "# Next Steps\n\n"
        f"记录 `{title}` 近期最值得补充的资料、页面和行动项。\n"
    )


def build_engineering_brief_markdown(title: str) -> str:
    return (
        "# Engineering Brief\n\n"
        "## Summary\n\n"
        "- Scope:\n"
        "- Audience:\n"
        "- Confidence: tentative\n\n"
        "## Engineering Impact\n\n"
        "- Confirmed:\n"
        "- Inferred:\n"
        "- Tentative:\n\n"
        "## Constraints\n\n"
        "- Architecture:\n"
        "- Data:\n"
        "- Operations:\n"
        "- Evaluation:\n\n"
        "## Risks\n\n"
        "- Risk:\n"
        "- Mitigation:\n\n"
        "## Recommended Next Actions\n\n"
        "- Action:\n"
        "- Owner:\n"
        "- Acceptance signal:\n\n"
        "## Sources\n\n"
        "- Wiki:\n"
        "- Evidence:\n"
    )


def build_implementation_guide_markdown(title: str) -> str:
    return (
        "# Implementation Guide\n\n"
        "## Summary\n\n"
        "- Goal:\n"
        "- Target project or workflow:\n"
        "- Confidence: tentative\n\n"
        "## Module Boundaries\n\n"
        "- Module:\n"
        "- Responsibility:\n"
        "- Out of scope:\n\n"
        "## Interfaces And Data Flow\n\n"
        "- Input:\n"
        "- Output:\n"
        "- Dependencies:\n"
        "- Failure modes:\n\n"
        "## Test Strategy\n\n"
        "- Unit:\n"
        "- Integration:\n"
        "- Evaluation:\n"
        "- Regression:\n\n"
        "## Rollout Notes\n\n"
        "- Migration:\n"
        "- Observability:\n"
        "- Revert path:\n\n"
        "## Sources\n\n"
        "- Wiki:\n"
        "- Evidence:\n"
    )


def build_decision_brief_markdown(title: str) -> str:
    return (
        "# Decision Brief\n\n"
        "## Decision Question\n\n"
        "- Question:\n"
        "- Context:\n"
        "- Confidence: tentative\n\n"
        "## Options\n\n"
        "- Option:\n"
        "- Pros:\n"
        "- Cons:\n"
        "- Best when:\n\n"
        "## Recommendation\n\n"
        "- Recommended option:\n"
        "- Reason:\n"
        "- Counterexample:\n\n"
        "## Consequences\n\n"
        "- Engineering:\n"
        "- Operations:\n"
        "- Knowledge base:\n\n"
        "## Sources\n\n"
        "- Wiki:\n"
        "- Evidence:\n"
    )


def build_backlog_markdown(title: str) -> str:
    return (
        "# Backlog\n\n"
        "## Project Seeds\n\n"
        "- Idea:\n"
        "- Why now:\n"
        "- Source:\n"
        "- Confidence: tentative\n\n"
        "## Experiments\n\n"
        "- Experiment:\n"
        "- Hypothesis:\n"
        "- Acceptance signal:\n\n"
        "## Implementation Tasks\n\n"
        "- Task:\n"
        "- Depends on:\n"
        "- Done when:\n\n"
        "## Open Risks\n\n"
        "- Risk:\n"
        "- Next check:\n\n"
        "## Sources\n\n"
        "- Wiki:\n"
        "- Evidence:\n"
    )


def build_requirement_analysis_markdown(title: str) -> str:
    return (
        "# Requirement Analysis\n\n"
        "## Summary\n\n"
        "- Source:\n"
        f"- Target theme: {title}\n"
        "- Scope:\n"
        "- Confidence: tentative\n\n"
        "## Requirement Items\n\n"
        "| ID | Type | Requirement | Priority | Confidence | Evidence | Related modules/entities |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| REQ-001 | functional |  | medium | tentative |  |  |\n\n"
        "## Functional Requirements\n\n"
        "- ID: REQ-001\n"
        "- Requirement:\n"
        "- Priority: medium\n"
        "- Description:\n"
        "- Evidence:\n"
        "- Confidence: tentative\n"
        "- Related modules/entities:\n\n"
        "## Non-Functional Constraints\n\n"
        "- ID: NFR-001\n"
        "- Constraint:\n"
        "- Category:\n"
        "- Target or threshold:\n"
        "- Evidence:\n"
        "- Confidence: tentative\n"
        "- Related modules/entities:\n\n"
        "## Technical Constraints\n\n"
        "- ID: TECH-001\n"
        "- Constraint:\n"
        "- Impacted area:\n"
        "- Reason:\n"
        "- Evidence:\n"
        "- Confidence: tentative\n"
        "- Related modules/entities:\n\n"
        "## Acceptance Criteria\n\n"
        "- ID: AC-001\n"
        "- Criterion:\n"
        "- Related requirement:\n"
        "- Verification approach:\n"
        "- Evidence:\n"
        "- Confidence: tentative\n\n"
        "## Open Questions\n\n"
        "- Question:\n"
        "- Blocking impact:\n"
        "- Next step:\n\n"
        "## Sources\n\n"
        "- Wiki:\n"
        "- Evidence:\n"
    )


def build_project_architecture_markdown(title: str) -> str:
    return (
        "# Architecture\n\n"
        f"这里用于描述 `{title}` 的系统边界、核心模块、数据流与关键依赖。\n"
    )


def build_project_stack_markdown(title: str, area: str) -> str:
    return f"# {area}\n\n记录 `{title}` 在 `{area}` 维度的关键技术选型、约束与维护要点。\n"


def build_project_weekly_summary_markdown(title: str) -> str:
    return (
        "# Weekly Summary\n\n"
        f"这里用于记录 `{title}` 的周报摘要、关键变化与风险提示。\n"
    )


def build_project_next_steps_markdown(title: str) -> str:
    return (
        "# Next Steps\n\n"
        f"记录 `{title}` 近期需要推进的模块、文档和治理事项。\n"
    )


def build_research_stack_markdown(title: str, area: str) -> str:
    return f"# {area}\n\n记录 `{title}` 在 `{area}` 维度的工具、方法或候选方案。\n"


def build_research_reading_plan_markdown(title: str) -> str:
    return (
        "# Reading Plan\n\n"
        f"这里用于规划 `{title}` 相关论文、文章、报告与学习顺序。\n"
    )


def build_research_thesis_markdown(title: str) -> str:
    return (
        "# Thesis\n\n"
        f"这里用于沉淀 `{title}` 的阶段性判断、核心结论与证据链。\n"
    )


def build_research_next_steps_markdown(title: str) -> str:
    return (
        "# Next Steps\n\n"
        f"记录 `{title}` 近期最重要的研究问题、实验和资料补充计划。\n"
    )


def build_folder_readme_markdown(folder_name: str, title: str) -> str:
    return f"# {folder_name}\n\n这里用于沉淀 `{title}` 的 `{folder_name}` 相关内容。\n"


def build_theme_scaffold_files(
    root: Path,
    category: str,
    title: str,
    theme_dir_name: str,
    owners: list[str],
    tags: list[str],
    status: str,
) -> dict[Path, str]:
    theme_dir = root / "themes" / category / theme_dir_name
    files: dict[Path, str] = {
        theme_dir / "README.md": render_theme_readme(root, category, title, theme_dir_name, owners, tags, status),
        theme_dir / "meta.md": build_meta_markdown(category, title, theme_dir_name, owners, tags, status),
        theme_dir / "wiki" / "overview.md": build_overview_markdown(category, title, theme_dir_name),
        theme_dir / "wiki" / "glossary.md": build_glossary_markdown(title),
        theme_dir / "wiki" / "open-questions.md": build_open_questions_markdown(title),
        theme_dir / "sources" / "README.md": build_sources_readme_markdown(title),
        theme_dir / "outputs" / "document-intake" / "README.md": build_document_intake_readme_markdown(title),
        theme_dir / "outputs" / "engineering-brief.md": build_engineering_brief_markdown(title),
        theme_dir / "outputs" / "implementation-guide.md": build_implementation_guide_markdown(title),
        theme_dir / "outputs" / "decision-brief.md": build_decision_brief_markdown(title),
        theme_dir / "outputs" / "backlog.md": build_backlog_markdown(title),
    }

    if category == "general":
        files.update(
            {
                theme_dir / "wiki" / "faq.md": build_general_faq_markdown(title),
                theme_dir / "stack" / "tools.md": build_general_stack_tools_markdown(title),
                theme_dir / "stack" / "workflows.md": build_general_stack_workflows_markdown(title),
                theme_dir / "outputs" / "summary.md": build_general_summary_markdown(title),
                theme_dir / "outputs" / "next-steps.md": build_general_next_steps_markdown(title),
            }
        )
    elif category == "project":
        files.update(
            {
                theme_dir / "wiki" / "architecture.md": build_project_architecture_markdown(title),
                theme_dir / "wiki" / "modules" / "README.md": build_folder_readme_markdown("Modules", title),
                theme_dir / "wiki" / "decisions" / "README.md": build_folder_readme_markdown("Decisions", title),
                theme_dir / "wiki" / "incidents" / "README.md": build_folder_readme_markdown("Incidents", title),
                theme_dir / "wiki" / "playbooks" / "README.md": build_folder_readme_markdown("Playbooks", title),
                theme_dir / "stack" / "backend.md": build_project_stack_markdown(title, "Backend"),
                theme_dir / "stack" / "frontend.md": build_project_stack_markdown(title, "Frontend"),
                theme_dir / "stack" / "data.md": build_project_stack_markdown(title, "Data"),
                theme_dir / "stack" / "infra.md": build_project_stack_markdown(title, "Infra"),
                theme_dir / "stack" / "tools.md": build_project_stack_markdown(title, "Tools"),
                theme_dir / "outputs" / "requirement-analysis.md": build_requirement_analysis_markdown(title),
                theme_dir / "outputs" / "weekly-summary.md": build_project_weekly_summary_markdown(title),
                theme_dir / "outputs" / "next-steps.md": build_project_next_steps_markdown(title),
            }
        )
    else:
        files.update(
            {
                theme_dir / "wiki" / "concepts" / "README.md": build_folder_readme_markdown("Concepts", title),
                theme_dir / "wiki" / "comparisons" / "README.md": build_folder_readme_markdown("Comparisons", title),
                theme_dir / "wiki" / "experiments" / "README.md": build_folder_readme_markdown("Experiments", title),
                theme_dir / "wiki" / "decisions" / "README.md": build_folder_readme_markdown("Decisions", title),
                theme_dir / "stack" / "models.md": build_research_stack_markdown(title, "Models"),
                theme_dir / "stack" / "frameworks.md": build_research_stack_markdown(title, "Frameworks"),
                theme_dir / "stack" / "eval.md": build_research_stack_markdown(title, "Eval"),
                theme_dir / "stack" / "tools.md": build_research_stack_markdown(title, "Tools"),
                theme_dir / "outputs" / "reading-plan.md": build_research_reading_plan_markdown(title),
                theme_dir / "outputs" / "thesis.md": build_research_thesis_markdown(title),
                theme_dir / "outputs" / "next-steps.md": build_research_next_steps_markdown(title),
            }
        )

    return files


def write_scaffold_files(files: dict[Path, str]) -> list[Path]:
    written_paths: list[Path] = []
    for path, content in sorted(files.items(), key=lambda item: item[0].as_posix()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written_paths.append(path)
    return written_paths


def build_themes_index_markdown(root: Path) -> str:
    themes = collect_theme_summaries(root)
    grouped: dict[str, list[ThemeSummary]] = {category: [] for category in THEME_CATEGORIES}
    for theme in themes:
        if theme.category in grouped:
            grouped[theme.category].append(theme)

    lines = ["# Themes Index", ""]
    for category in THEME_CATEGORIES:
        lines.append(f"## {THEME_INDEX_HEADINGS[category]}")
        items = grouped.get(category, [])
        if not items:
            lines.append("- 暂无主题")
        else:
            for theme in items:
                lines.append(f"- {theme_readme_link(theme.category, theme.name)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def ensure_cross_theme_map_entry(root: Path, category: str, theme_name: str) -> None:
    path = root / "index" / "cross-theme-map.md"
    section_heading = f"## {theme_name}"
    section_body = "\n".join(
        [
            section_heading,
            f"- 主题入口 {theme_readme_link(category, theme_name)}",
            "- 关联主题待补充",
        ]
    )

    if not path.exists():
        content = "# Cross Theme Map\n\n" + section_body + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return

    content = read_text(path).rstrip()
    if re.search(rf"^##\s+{re.escape(theme_name)}\s*$", content, flags=re.MULTILINE):
        return
    path.write_text(content + "\n\n" + section_body + "\n", encoding="utf-8")


def create_theme(
    root: Path,
    category: str,
    title: str,
    owners: list[str] | None = None,
    extra_tags: list[str] | None = None,
    status: str = "active",
) -> dict[str, Any]:
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Theme title cannot be empty.")

    theme_dir_name = build_theme_dir_name(root, category, clean_title)
    theme_dir = root / "themes" / category / theme_dir_name
    if theme_dir.exists():
        raise FileExistsError(f"Theme directory already exists: {theme_dir}")

    normalized_owners = build_theme_owners(owners or [])
    normalized_tags = build_theme_tags(category, theme_dir_name, extra_tags or [])
    written_files = write_scaffold_files(
        build_theme_scaffold_files(root, category, clean_title, theme_dir_name, normalized_owners, normalized_tags, status)
    )

    themes_index_path = root / "index" / "themes.md"
    themes_index_path.parent.mkdir(parents=True, exist_ok=True)
    themes_index_path.write_text(build_themes_index_markdown(root), encoding="utf-8")

    ensure_cross_theme_map_entry(root, category, theme_dir_name)
    append_recent_update(root, f"新建 `{theme_dir_name}` 主题（{category}），并初始化基础脚手架。")

    home_path = root / "index" / "home.md"
    home_path.parent.mkdir(parents=True, exist_ok=True)
    home_path.write_text(build_home_markdown(root), encoding="utf-8")

    return {
        "category": category,
        "title": clean_title,
        "theme_name": theme_dir_name,
        "status": status,
        "owners": normalized_owners,
        "tags": normalized_tags,
        "relative_path": theme_dir.relative_to(root).as_posix(),
        "created_files": [path.relative_to(root).as_posix() for path in written_files],
        "updated_indexes": [
            themes_index_path.relative_to(root).as_posix(),
            (root / "index" / "cross-theme-map.md").relative_to(root).as_posix(),
            home_path.relative_to(root).as_posix(),
            (root / "index" / "recent-updates.md").relative_to(root).as_posix(),
        ],
    }


def count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_file())


def collect_theme_summaries(root: Path) -> list[ThemeSummary]:
    summaries: list[ThemeSummary] = []
    for category, theme_dir in iter_theme_dirs(root):
        summaries.append(
            ThemeSummary(
                name=theme_dir.name,
                category=category,
                relative_path=theme_dir.relative_to(root).as_posix(),
                theme_type=extract_theme_type(theme_dir / "meta.md"),
                readme_exists=(theme_dir / "README.md").exists(),
                meta_exists=(theme_dir / "meta.md").exists(),
                overview_exists=(theme_dir / "wiki" / "overview.md").exists(),
                source_file_count=count_files(theme_dir / "sources"),
                wiki_file_count=count_files(theme_dir / "wiki"),
                stack_file_count=count_files(theme_dir / "stack"),
                output_file_count=count_files(theme_dir / "outputs"),
            )
        )
    return summaries


def collect_inbox_files(root: Path) -> dict[str, list[str]]:
    inbox_dir = root / "inbox"
    result: dict[str, list[str]] = {}
    if not inbox_dir.exists():
        return result

    for subdir in sorted(p for p in inbox_dir.iterdir() if p.is_dir()):
        result[subdir.name] = sorted(
            item.relative_to(root).as_posix()
            for item in subdir.rglob("*")
            if item.is_file()
        )
    return result


def classify_inbox(root: Path) -> dict[str, Any]:
    """Return read-only routing suggestions for inbox items."""
    inbox_dir = root / "inbox"
    if not inbox_dir.exists():
        return {
            "root": str(root),
            "items": [],
            "counts": {"content_kind": {}, "source_type": {}, "suggested_action": {}},
            "high_confidence_requirements": [],
            "review": [],
        }

    items = [
        classify_inbox_item(root, path)
        for path in sorted((item for item in inbox_dir.rglob("*") if item.is_file()), key=lambda item: item.as_posix().lower())
    ]
    content_counts = Counter(str(item["content_kind"]) for item in items)
    source_counts = Counter(str(item["source_type"]) for item in items)
    action_counts = Counter(str(item["suggested_action"]) for item in items)
    return {
        "root": str(root),
        "items": items,
        "counts": {
            "content_kind": dict(content_counts),
            "source_type": dict(source_counts),
            "suggested_action": dict(action_counts),
        },
        "high_confidence_requirements": [
            item["path"]
            for item in items
            if item["content_kind"] == "requirement" and item["confidence"] in {"high", "confirmed"}
        ],
        "review": [item["path"] for item in items if item["suggested_action"] == "review"],
    }


def classify_inbox_item(root: Path, path: Path) -> dict[str, Any]:
    rel = path.relative_to(root).as_posix() if path.is_absolute() and path.resolve().is_relative_to(root.resolve()) else path.as_posix()
    source_type = detect_inbox_source_type(path)
    preview = inbox_text_preview(path, source_type)
    scores = score_inbox_content_kind(rel, path, source_type, preview)
    content_kind = max(scores, key=lambda key: scores[key]) if scores else "unknown"
    score = scores.get(content_kind, 0.0)
    confidence = inbox_confidence(score)
    action = inbox_suggested_action(rel, source_type, content_kind, score)
    reasons = inbox_classification_reasons(rel, source_type, content_kind, scores, preview)
    return {
        "path": rel,
        "source_type": source_type,
        "content_kind": content_kind,
        "confidence": confidence,
        "score": round(score, 2),
        "suggested_action": action,
        "reasons": reasons[:6],
    }


def detect_inbox_source_type(path: Path) -> str:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in INBOX_IMAGE_EXTENSIONS:
        return "image"
    if suffix in INBOX_VIDEO_EXTENSIONS:
        return "video"
    if suffix in INBOX_AUDIO_EXTENSIONS:
        return "audio"
    if suffix in INBOX_ARCHIVE_EXTENSIONS:
        return "archive"
    if suffix in INBOX_SOURCE_CODE_EXTENSIONS or name in INBOX_MANIFEST_NAMES:
        return "source-code"
    if suffix in INBOX_TEXT_EXTENSIONS:
        return "document"
    return "unknown"


def inbox_text_preview(path: Path, source_type: str, max_chars: int = 12_000) -> str:
    if source_type not in {"document", "source-code", "unknown"}:
        return ""
    if path.suffix.lower() in {".pdf", ".doc", ".docx", ".xls", ".xlsx"}:
        return ""
    try:
        return read_text(path)[:max_chars]
    except OSError:
        return ""


def score_inbox_content_kind(rel: str, path: Path, source_type: str, preview: str) -> dict[str, float]:
    haystack = f"{rel}\n{path.name}\n{preview}".lower()
    rel_lower = rel.lower()
    scores: dict[str, float] = {
        "requirement": 0.0,
        "paper": 0.0,
        "article": 0.0,
        "learning-material": 0.0,
        "source-code": 0.0,
        "image": 0.0,
        "video": 0.0,
        "unknown": 0.05,
    }
    if "/requirements/" in rel_lower or "\\requirements\\" in rel_lower:
        scores["requirement"] += 0.45
    if "/papers/" in rel_lower or "\\papers\\" in rel_lower:
        scores["paper"] += 0.45
    if "/articles/" in rel_lower or "\\articles\\" in rel_lower:
        scores["article"] += 0.4
    if "/source-code/" in rel_lower or "\\source-code\\" in rel_lower:
        scores["source-code"] += 0.45
    if ("/images/" in rel_lower or "\\images\\" in rel_lower or "/media/images/" in rel_lower or "\\media\\images\\" in rel_lower) and source_type == "image":
        scores["image"] += 0.35
    if ("/videos/" in rel_lower or "\\videos\\" in rel_lower or "/media/videos/" in rel_lower or "\\media\\videos\\" in rel_lower) and source_type == "video":
        scores["video"] += 0.35
    if "/audio/" in rel_lower or "\\audio\\" in rel_lower or "/media/audio/" in rel_lower or "\\media\\audio\\" in rel_lower:
        scores["unknown"] += 0.2

    scores["requirement"] += min(0.45, 0.08 * keyword_hits(haystack, REQUIREMENT_HINTS))
    scores["paper"] += min(0.4, 0.08 * keyword_hits(haystack, PAPER_HINTS))
    scores["article"] += min(0.3, 0.07 * keyword_hits(haystack, ARTICLE_HINTS))
    scores["learning-material"] += min(0.3, 0.07 * keyword_hits(haystack, LEARNING_HINTS))

    if re.search(r"(?im)^\s*(功能需求|非功能|验收标准|acceptance criteria|requirements?)\s*[:#]", preview):
        scores["requirement"] += 0.18
    if re.search(r"(?im)^\s*(abstract|摘要)\s*[:#]?", preview) and re.search(r"(?im)^\s*(references|参考文献)\s*[:#]?", preview):
        scores["paper"] += 0.22
    if source_type == "source-code":
        scores["source-code"] += 0.65
    elif source_type == "image":
        scores["image"] += 0.85
    elif source_type == "video":
        scores["video"] += 0.85
    elif source_type == "audio":
        scores["unknown"] += 0.25
    elif source_type == "archive":
        scores["unknown"] += 0.2

    if scores["requirement"] < 0.25 and re.search(r"\b(req|prd|srs|brd|mrd)[-_ ]?\d*\b", path.stem.lower()):
        scores["requirement"] += 0.25
    return {key: min(value, 0.97) for key, value in scores.items()}


def keyword_hits(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword.lower() in text)


def inbox_confidence(score: float) -> str:
    if score >= 0.88:
        return "confirmed"
    if score >= 0.72:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def inbox_suggested_action(rel: str, source_type: str, content_kind: str, score: float) -> str:
    rel_lower = rel.lower()
    if "/review/" in rel_lower or "\\review\\" in rel_lower:
        return "review"
    if content_kind == "requirement":
        return "ingest_requirement" if score >= 0.72 else "review"
    if content_kind in {"paper", "article", "learning-material"} and score >= 0.45:
        return "ingest_to_theme"
    if content_kind == "source-code":
        return "project_reverse_or_source_ingest"
    if source_type in {"image", "video", "audio"}:
        return "extract_media_then_ingest"
    return "review"


def inbox_classification_reasons(rel: str, source_type: str, content_kind: str, scores: dict[str, float], preview: str) -> list[str]:
    reasons = [f"source_type={source_type}"]
    rel_lower = rel.lower()
    if f"/{content_kind}s/" in rel_lower or f"\\{content_kind}s\\" in rel_lower or f"/media/{content_kind}s/" in rel_lower or f"\\media\\{content_kind}s\\" in rel_lower:
        reasons.append(f"path_hint={content_kind}")
    if content_kind == "requirement" and keyword_hits(f"{rel}\n{preview}".lower(), REQUIREMENT_HINTS):
        reasons.append("requirement_keywords_detected")
    if content_kind == "paper" and keyword_hits(f"{rel}\n{preview}".lower(), PAPER_HINTS):
        reasons.append("paper_keywords_detected")
    if content_kind == "source-code":
        reasons.append("code_or_manifest_extension")
    if content_kind in {"image", "video"}:
        reasons.append("media_extension")
    if scores.get(content_kind, 0.0) < 0.72:
        reasons.append("low_confidence_route")
    return reasons


def read_recent_updates(root: Path, limit: int = 10) -> list[str]:
    path = root / "index" / "recent-updates.md"
    if not path.exists():
        return []
    bullets = [line.strip() for line in read_text(path).splitlines() if line.strip().startswith("- ")]
    return bullets[-limit:]


def extract_markdown_links(text: str) -> list[str]:
    links: list[str] = []
    for match in WIKILINK_RE.finditer(text):
        target = match.group(1).split("#", 1)[0].strip().replace("\\", "/").removesuffix(".md")
        if target:
            links.append(target)
    return unique_preserve_order(links)


def shared_asset_refs(root: Path) -> set[str]:
    asset_dir = root / "shared" / "assets"
    if not asset_dir.is_dir():
        return set()
    return {
        normalize_reference(path.relative_to(root).as_posix(), root)
        for path in asset_dir.glob("*.md")
        if path.name.lower() != "readme.md"
    }


def parse_reuse_candidate_rows(content: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = split_markdown_table_row(stripped)
        if len(cells) < 4 or cells[0].lower() == "asset":
            continue
        asset_cell = cells[0]
        links = [target for target in extract_markdown_links(asset_cell) if target.startswith("shared/assets/")]
        plain_asset = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", asset_cell).strip("` ")
        if plain_asset.startswith("shared/assets/"):
            links.append(plain_asset.removesuffix(".md"))
        candidates.append(
            {
                "asset": asset_cell,
                "asset_refs": unique_preserve_order(links),
                "reuse_level": cells[2].strip("` ").lower() if len(cells) > 2 else "",
                "reuse_cost": cells[3].strip("` ").lower() if len(cells) > 3 else "",
                "best_fit": cells[4] if len(cells) > 4 else "",
                "key_risk": cells[5] if len(cells) > 5 else "",
            }
        )
    return candidates


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


def scan_reuse(root: Path) -> dict[str, Any]:
    """Read-only reuse-chain inventory for LLM semantic follow-up."""
    assets = sorted(shared_asset_refs(root))
    assets_set = set(assets)
    target_match_briefs: list[dict[str, Any]] = []
    reuse_candidate_files: list[dict[str, Any]] = []
    missing_match_briefs: list[str] = []
    unpromoted_candidates: list[dict[str, Any]] = []
    broken_asset_refs: list[dict[str, str]] = []
    asset_match_refs: dict[str, list[str]] = {asset: [] for asset in assets}

    for category, theme_dir in iter_theme_dirs(root):
        theme_ref = theme_dir.relative_to(root).as_posix()
        outputs_dir = theme_dir / "outputs"
        reuse_path = outputs_dir / "reuse-candidates.md"
        match_path = outputs_dir / "asset-match-brief.md"

        if category == "project" and not match_path.exists():
            missing_match_briefs.append(theme_ref)

        if reuse_path.exists():
            content = read_text(reuse_path)
            candidates = parse_reuse_candidate_rows(content)
            reuse_candidate_files.append(
                {
                    "theme": theme_ref,
                    "path": reuse_path.relative_to(root).as_posix(),
                    "candidate_count": len(candidates),
                    "candidates": candidates,
                }
            )
            for candidate in candidates:
                refs = candidate.get("asset_refs") or []
                if not refs:
                    if candidate.get("reuse_level") in {"direct", "adapt", "reference"}:
                        unpromoted_candidates.append(
                            {
                                "theme": theme_ref,
                                "path": reuse_path.relative_to(root).as_posix(),
                                "asset": candidate.get("asset", ""),
                                "reuse_level": candidate.get("reuse_level", ""),
                                "severity_hint": "warning" if candidate.get("reuse_level") in {"direct", "adapt"} else "info",
                            }
                        )
                    continue
                for ref in refs:
                    if ref not in assets_set:
                        broken_asset_refs.append(
                            {
                                "path": reuse_path.relative_to(root).as_posix(),
                                "asset_ref": ref,
                                "reason": "reuse-candidates references a missing shared asset",
                            }
                        )

        if match_path.exists():
            content = read_text(match_path)
            refs = [target for target in extract_markdown_links(content) if target.startswith("shared/assets/")]
            target_match_briefs.append(
                {
                    "theme": theme_ref,
                    "path": match_path.relative_to(root).as_posix(),
                    "asset_refs": refs,
                }
            )
            for ref in refs:
                if ref in asset_match_refs:
                    asset_match_refs[ref].append(match_path.relative_to(root).as_posix())
                else:
                    broken_asset_refs.append(
                        {
                            "path": match_path.relative_to(root).as_posix(),
                            "asset_ref": ref,
                            "reason": "asset-match-brief references a missing shared asset",
                        }
                    )

    unmatched_assets = [
        {"asset": asset, "reason": "no project asset-match-brief references this shared asset"}
        for asset in assets
        if not asset_match_refs.get(asset)
    ]
    return {
        "root": str(root),
        "shared_assets": assets,
        "reuse_candidate_files": reuse_candidate_files,
        "target_match_briefs": target_match_briefs,
        "missing_match_briefs": missing_match_briefs,
        "unpromoted_candidates": unpromoted_candidates,
        "unmatched_assets": unmatched_assets,
        "broken_asset_refs": broken_asset_refs,
    }


def append_recent_update(root: Path, message: str) -> None:
    index_dir = root / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    path = index_dir / "recent-updates.md"
    today = datetime.now().strftime("%Y-%m-%d")
    bullet = f"- {today}: {message}"

    if not path.exists():
        path.write_text("# Recent Updates\n\n## 最近更新\n" + bullet + "\n", encoding="utf-8")
        return

    content = read_text(path)
    if "## 最近更新" in content:
        if not content.endswith("\n"):
            content += "\n"
        content += bullet + "\n"
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += "\n## 最近更新\n" + bullet + "\n"
    path.write_text(content, encoding="utf-8")


def print_inventory_text(root: Path, themes: list[ThemeSummary], inbox_files: dict[str, list[str]], recent_updates: list[str]) -> None:
    print(f"Knowledge Base Inventory: {root}")
    print("")
    print("Themes:")
    if not themes:
        print("- No themes found.")
    for theme in themes:
        print(
            f"- {theme.category}/{theme.name} [{theme.theme_type}] "
            f"readme={theme.readme_exists} meta={theme.meta_exists} overview={theme.overview_exists} "
            f"sources={theme.source_file_count} wiki={theme.wiki_file_count} "
            f"stack={theme.stack_file_count} outputs={theme.output_file_count}"
        )

    print("")
    print("Next Theme Numbers:")
    for category in THEME_CATEGORIES:
        print(f"- {category}: {next_theme_number(root, category)}")

    print("")
    print("Inbox:")
    if not inbox_files:
        print("- No inbox directories found.")
    for bucket, files in inbox_files.items():
        print(f"- {bucket}: {len(files)} file(s)")
        for file_path in files[:20]:
            print(f"  - {file_path}")
        if len(files) > 20:
            print("  - ...")

    print("")
    print("Recent Updates:")
    if not recent_updates:
        print("- No recent updates found.")
    else:
        for item in recent_updates:
            print(item)


def print_inbox_classification_text(payload: dict[str, Any]) -> None:
    print(f"Inbox Classification: {payload.get('root')}")
    print("")
    counts = payload.get("counts", {})
    print("Content Kinds:")
    for name, count in sorted((counts.get("content_kind") or {}).items()):
        print(f"- {name}: {count}")
    print("")
    print("Items:")
    items = payload.get("items", [])
    if not items:
        print("- No inbox files found.")
    for item in items:
        print(
            f"- {item['path']}: source_type={item['source_type']} "
            f"content_kind={item['content_kind']} confidence={item['confidence']} "
            f"action={item['suggested_action']}"
        )
        if item.get("reasons"):
            print(f"  reasons: {', '.join(item['reasons'])}")



def build_home_markdown(root: Path) -> str:
    themes = collect_theme_summaries(root)
    grouped: dict[str, list[ThemeSummary]] = {category: [] for category in THEME_CATEGORIES}
    for theme in themes:
        if theme.category in grouped:
            grouped[theme.category].append(theme)

    lines = [
        "# Knowledge Base Home",
        "",
        "## 说明",
        "这是一个按 `general / project / research` 分类的主题优先知识库。",
        "",
        "## 一级入口",
        "- `themes/`",
        "- `shared/`",
        "- `inbox/`",
        "- `index/`",
        "- `schema/`",
        "",
        "## 主题导航",
    ]

    for category in THEME_CATEGORIES:
        lines.extend(["", f"### {THEME_HOME_LABELS[category]}"])
        items = grouped.get(category, [])
        if not items:
            lines.append("- 暂无主题")
            continue
        for theme in items:
            readme_path = theme.relative_path + "/README"
            lines.append(f"- [[{readme_path}|{theme.name}]]")

    lines.extend(
        [
            "",
            "## 推荐起步方式",
            "1. 先看 `index/themes.md` 了解主题总览。",
            "2. 再进入目标主题的 `README.md`。",
            "3. 最后进入该主题的 `wiki/overview.md`。",
            "",
            "## 近期更新",
        ]
    )

    recent_updates = read_recent_updates(root, limit=8)
    if recent_updates:
        lines.extend(recent_updates)
    else:
        lines.append("- 暂无更新记录")

    lines.extend(
        [
            "",
            "## 使用提示",
            textwrap.dedent(
                """\
                - 新资料入库：优先使用 `ingest`
                - 基于知识库回答问题：优先使用 `query`
                - 结构与质量巡检：优先使用 `lint`"""
            ),
            "",
        ]
    )

    return "\n".join(lines).replace("\n- ", "\n- ").rstrip() + "\n"


def emit_payload(payload: dict[str, Any], output_path: Path | None, output_format: str) -> None:
    from kb_ingest_documents import render_payload_content

    content = render_payload_content(payload, output_format)

    if output_path is None:
        print(content)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"Wrote extraction to {output_path}")


def log_ingest_operation(root: Path, action: str, summary: str, details: list[str] | None = None, status: str = "completed") -> None:
    append_activity_log(root, skill="ingest", action=action, summary=summary, status=status, details=details)
