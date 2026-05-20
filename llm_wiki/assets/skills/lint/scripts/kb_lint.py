#!/usr/bin/env python3
"""Lint the theme-first knowledge base."""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))
KB_TOOLS_DIR = Path(__file__).resolve().parents[4] / "tools"
if str(KB_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(KB_TOOLS_DIR))

from kb_activity_log import append_activity_log
from kb_qmd_capabilities import detect_qmd_capability


ROOT_REQUIRED_DIRS = ["themes", "shared", "schema", "index", "inbox"]
THEME_CATEGORY_DIRS = ["general", "project", "research"]
THEME_REQUIRED_FILES = ["README.md", "meta.md"]
THEME_REQUIRED_DIRS = ["sources", "wiki", "stack", "outputs"]
WIKI_REQUIRED_BY_TYPE = {
    "project": ["overview.md", "glossary.md", "open-questions.md", "architecture.md"],
    "research": ["overview.md", "glossary.md", "open-questions.md"],
    "general": ["overview.md", "glossary.md", "open-questions.md", "faq.md"],
}
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
REUSE_LEVELS_FOR_PROMOTION_WARNING = {"direct", "adapt"}
REUSE_LEVELS_FOR_PROMOTION_INFO = {"reference"}
PLACEHOLDER_PATTERNS = [
    "your-name",
    "<theme-name>",
    "<your-name>",
    "<repo-url-or-local-path>",
    "<YYYY-MM-DD>",
    "topic-1",
    "scope-1",
    "<language>",
    "<framework>",
]
IGNORED_MARKDOWN_DIRS = {".agents", ".claude", ".codex", ".trae", ".opencode", ".openclaw", ".hermes", ".obsidian"}
AGENTS_REVIEW_TOKENS = 1000
AGENTS_REGRESSION_TOKENS = 1500
SKILL_ENTRY_REVIEW_TOKENS = 1500
SKILL_SOURCE_REL = Path(".agents/skills")
SKILL_MIRROR_RELS_BY_PLATFORM = {
    "claude": Path(".claude/skills"),
    "codex": Path(".codex/skills"),
    "trae": Path(".trae/skills"),
    "opencode": Path(".opencode/skills"),
    "openclaw": Path(".openclaw/skills"),
    "hermes": Path(".hermes/skills"),
}
SKILL_MIRROR_RELS = list(SKILL_MIRROR_RELS_BY_PLATFORM.values())
MIRROR_STATE_FILE = ".mirror-state.json"
QMD_INDEX_STALE_DAYS = 7


@dataclass
class Issue:
    severity: str
    code: str
    path: str
    message: str
    scope: str = "structure"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint the LLM wiki knowledge base.")
    parser.add_argument("--root", default=".", help="Knowledge base root directory")
    parser.add_argument(
        "--scope",
        choices=["structure", "graph", "knowledge", "all"],
        default="all",
        help="Check scope. Default runs structure, graph, and knowledge checks.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings as well as errors",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact top-issues summary instead of the full text issue list.",
    )
    parser.add_argument(
        "--summary-top",
        type=int,
        default=5,
        help="Number of highest-impact issues to include in summary mode and JSON top_issues.",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def estimated_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def should_skip_mirror_path(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix == ".pyc" or path.name == MIRROR_STATE_FILE


def snapshot_files(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not root.is_dir():
        return result
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if should_skip_mirror_path(relative):
            continue
        result[relative.as_posix()] = file_digest(path)
    return result


def configured_skill_mirror_rels(root: Path) -> list[Path]:
    manifest = root / "llm-wiki.yaml"
    if not manifest.exists():
        return SKILL_MIRROR_RELS
    text = read_text(manifest)
    configured = [
        rel
        for platform, rel in SKILL_MIRROR_RELS_BY_PLATFORM.items()
        if f"  {platform}:" in text
    ]
    return configured or SKILL_MIRROR_RELS


def extract_theme_type(meta_path: Path) -> str | None:
    if not meta_path.exists():
        return None
    content = read_text(meta_path)
    match = re.search(r"(?m)^theme_type:\s*([A-Za-z0-9_-]+)\s*$", content)
    return match.group(1).strip() if match else None


def theme_dir_sort_key(path: Path) -> tuple[int, str]:
    match = re.match(r"^\s*(\d+)[.-](.+)$", path.name)
    if match:
        return int(match.group(1)), match.group(2).strip().lower()
    return 10_000, path.name.lower()


def iter_theme_dirs(root: Path) -> list[tuple[str, Path]]:
    themes_dir = root / "themes"
    if not themes_dir.exists():
        return []

    discovered: list[tuple[str, Path]] = []
    for category_dir in sorted((p for p in themes_dir.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        if category_dir.name in THEME_CATEGORY_DIRS:
            for theme_dir in sorted((p for p in category_dir.iterdir() if p.is_dir()), key=theme_dir_sort_key):
                discovered.append((category_dir.name, theme_dir))
        else:
            discovered.append(("uncategorized", category_dir))
    return discovered


def build_note_index(root: Path) -> tuple[set[str], set[str], set[str]]:
    exact_notes: set[str] = set()
    basenames: set[str] = set()
    theme_names: set[str] = set()

    for _category, theme_dir in iter_theme_dirs(root):
        if theme_dir.is_dir():
            theme_names.add(theme_dir.name)

    for md_path in root.rglob("*.md"):
        relative = md_path.relative_to(root).as_posix()
        no_ext = relative[:-3]
        exact_notes.add(no_ext)
        basenames.add(md_path.stem)

    return exact_notes, basenames, theme_names


def normalize_path_ref(reference: str) -> str:
    raw = reference.strip().replace("\\", "/")
    raw = raw.split("#", 1)[0].strip()
    raw = raw.removeprefix("./").strip("/")
    return raw


def resolve_repo_ref(root: Path, reference: str) -> bool:
    raw = normalize_path_ref(reference)
    if not raw:
        return True
    path = root / raw
    if path.exists():
        return True
    if not Path(raw).suffix and path.with_suffix(".md").exists():
        return True
    return False


def resolve_repo_path(root: Path, reference: str) -> Path | None:
    raw = normalize_path_ref(reference)
    if not raw or raw.startswith("http://") or raw.startswith("https://"):
        return None
    path = root / raw
    if path.exists():
        return path
    if not Path(raw).suffix and path.with_suffix(".md").exists():
        return path.with_suffix(".md")
    return None


def iter_markdown_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*.md"):
        relative_parts = path.relative_to(root).parts
        if relative_parts and relative_parts[0] in IGNORED_MARKDOWN_DIRS:
            continue
        relative_text = path.relative_to(root).as_posix()
        if "/outputs/document-intake/graphify/runtime/" in f"/{relative_text}":
            continue
        if "/graphify-out/" in f"/{relative_text}/":
            continue
        paths.append(path)
    return sorted(paths, key=lambda item: item.relative_to(root).as_posix().lower())


def iter_semantic_markdown_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in iter_markdown_files(root):
        relative_parts = path.relative_to(root).parts
        if relative_parts and relative_parts[0] in {"themes", "shared"}:
            paths.append(path)
    return paths


def extract_frontmatter(content: str) -> tuple[dict[str, object], str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content

    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return {}, content

    frontmatter_lines = lines[1:end]
    body = "\n".join(lines[end + 1 :])
    values: dict[str, object] = {}
    current_key: str | None = None
    for line in frontmatter_lines:
        if not line.strip():
            continue
        if re.match(r"^[A-Za-z0-9_-]+:", line):
            key, value = line.split(":", 1)
            current_key = key.strip()
            clean_value = value.strip()
            values[current_key] = [] if clean_value in {"", "[]"} else clean_value
            continue
        if current_key and line.strip().startswith("- "):
            existing = values.setdefault(current_key, [])
            if not isinstance(existing, list):
                existing = [str(existing)]
                values[current_key] = existing
            existing.append(line.strip()[2:].strip())
    return values, body


def frontmatter_list(frontmatter: dict[str, object], key: str) -> list[str]:
    value = frontmatter.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text or text == "[]":
        return []
    return [text]


def frontmatter_scalar(frontmatter: dict[str, object], key: str) -> str | None:
    value = frontmatter.get(key)
    if value is None or isinstance(value, list):
        return None
    text = str(value).strip()
    return text or None


def markdown_links(content: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for raw_target in WIKILINK_RE.findall(content):
        target = normalize_wikilink_target(raw_target)
        if target and target not in seen:
            seen.add(target)
            links.append(target)
    return links


def shared_asset_refs(root: Path) -> set[str]:
    asset_dir = root / "shared" / "assets"
    if not asset_dir.is_dir():
        return set()
    return {
        path.relative_to(root).as_posix().removesuffix(".md")
        for path in asset_dir.glob("*.md")
        if path.name.lower() != "readme.md"
    }


def parse_reuse_candidate_rows(content: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = split_markdown_table_row(stripped)
        if len(cells) < 4 or cells[0].lower() == "asset":
            continue
        asset_cell = cells[0]
        refs = [target for target in markdown_links(asset_cell) if target.startswith("shared/assets/")]
        plain_asset = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", asset_cell).strip("` ")
        if plain_asset.startswith("shared/assets/"):
            refs.append(plain_asset.removesuffix(".md"))
        rows.append(
            {
                "asset": asset_cell,
                "asset_refs": sorted(set(refs)),
                "reuse_level": cells[2].strip("` ").lower() if len(cells) > 2 else "",
            }
        )
    return rows


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


def parse_frontmatter_date(frontmatter: dict[str, object], key: str) -> dt.date | None:
    value = frontmatter_scalar(frontmatter, key)
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def path_mtime_date(path: Path) -> dt.date | None:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return None


def is_canonical_page(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return False
    if path.name.lower() == "readme.md":
        return False
    return relative.startswith(
        (
            "shared/entities/",
            "shared/concepts/",
            "shared/patterns/",
            "shared/methods/",
            "shared/glossary/",
            "shared/assets/",
        )
    )


def canonical_ref(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix().removesuffix(".md")


def strip_template_noise(text: str) -> str:
    noise_patterns = [
        "这个实体是什么，它在当前知识库中扮演什么角色。",
        "这个概念的最小稳定定义是什么。",
        "这项技术资产提供什么可复用能力。",
        "适用于：",
        "不适用于：",
        "上游 / 依赖：",
        "下游 / 使用方：",
        "相关概念：",
        "相关主题：",
        "上位概念：",
        "下位概念：",
        "相关实体：",
        "相关模式：",
        "来源页：",
        "原始资料：",
        "待补充",
    ]
    cleaned = text
    for pattern in noise_patterns:
        cleaned = cleaned.replace(pattern, "")
    cleaned = re.sub(r"(?m)^\s*-\s*$", "", cleaned)
    cleaned = re.sub(r"(?m)^#+\s+.*$", "", cleaned)
    return cleaned.strip()


def normalize_identifier(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def issue_priority(issue: Issue) -> tuple[int, int]:
    severity_rank = {"error": 0, "warning": 1, "info": 2}.get(issue.severity, 3)
    path_text = issue.path.replace("\\", "/")
    example_penalty = 5 if re.search(r"/00-[^/]*example/", path_text) else 0
    code_rank = {
        "missing_theme_file": 0,
        "missing_theme_dir": 0,
        "canonical_template_body": 1,
        "canonical_missing_field": 1,
        "asset_missing_field": 1,
        "asset_bad_value": 1,
        "stale_page": 2,
        "output_stale": 2,
        "duplicate_canonical_node": 2,
        "contradiction_gap": 3,
        "source_drift": 3,
        "project_stale": 3,
        "graphify_evidence_incomplete": 3,
        "graphify_bad_metadata": 3,
        "graphify_runtime_artifact": 3,
        "graphify_global_missing_graph": 3,
        "shared_index_missing_entry": 3,
        "index_missing_shared_node": 3,
        "theme_missing_shared_backlink": 3,
        "missing_engineering_output": 4,
        "root_misresolved": 0,
    }.get(issue.code, 9)
    return severity_rank, code_rank + example_penalty


def normalize_wikilink_target(target: str) -> str:
    target = target.split("|", 1)[0].strip()
    target = target.split("#", 1)[0].strip()
    return target.replace("\\", "/").removesuffix(".md")


def resolve_wikilink(target: str, exact_notes: set[str], basenames: set[str], theme_names: set[str]) -> bool:
    if not target:
        return True
    if target in exact_notes:
        return True
    if target in basenames:
        return True
    if target in theme_names:
        return True
    return False


def load_index_theme_names(index_path: Path) -> set[str]:
    if not index_path.exists():
        return set()
    content = read_text(index_path)
    found = set()
    for raw in WIKILINK_RE.findall(content):
        target = normalize_wikilink_target(raw)
        if target:
            target_path = Path(target)
            found.add(target_path.parent.name if target_path.name.lower() == "readme" else target_path.name)
    return found


def rel_display(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def lint_root(root: Path) -> list[Issue]:
    issues: list[Issue] = []

    if not root.exists():
        issues.append(Issue("error", "root_missing", str(root), "知识库根目录不存在", "structure"))
        return issues

    if not (root / "AGENTS.md").exists() and (root / "kb" / "AGENTS.md").exists():
        issues.append(
            Issue(
                "error",
                "root_misresolved",
                str(root),
                "当前 root 看起来是知识库父目录；请从 `kb/` 目录执行，或显式传入 `--root kb`",
                "structure",
            )
        )
        return issues

    nested_root = root / "kb"
    if nested_root.is_dir() and (nested_root / "log.md").exists():
        issues.append(
            Issue(
                "warning",
                "root_misresolved",
                rel_display(root, nested_root),
                "发现嵌套的 `kb/` 运行产物，可能由旧版 helper 默认 `--root kb` 误写产生",
                "structure",
            )
        )

    for dirname in ROOT_REQUIRED_DIRS:
        path = root / dirname
        if not path.exists():
            issues.append(Issue("error", "missing_root_dir", str(path), f"缺少根目录 `{dirname}`", "structure"))

    themes_dir = root / "themes"
    if themes_dir.exists():
        for category in THEME_CATEGORY_DIRS:
            category_path = themes_dir / category
            if not category_path.exists():
                issues.append(Issue("warning", "missing_theme_category", str(category_path), f"缺少主题分类目录 `{category}/`", "structure"))

    return issues


def find_qmd_timestamp(value: object) -> dt.datetime | None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ["indexed", "updated", "mtime", "modified"]):
                parsed = parse_loose_datetime(item)
                if parsed:
                    return parsed
            nested = find_qmd_timestamp(item)
            if nested:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = find_qmd_timestamp(item)
            if nested:
                return nested
    return None


def parse_loose_datetime(value: object) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.fromtimestamp(float(value), tz=dt.timezone.utc)
        except (OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _qmd_subprocess_args(args: list[str]) -> list[str]:
    resolved = shutil.which("qmd")
    if resolved and sys.platform != "win32":
        return ["qmd", *args]
    for candidate in _qmd_js_candidates():
        if candidate.exists():
            return ["node", str(candidate), *args]
    if resolved:
        return ["qmd", *args]
    return ["qmd", *args]


def _qmd_js_candidates() -> list[Path]:
    candidates: list[Path] = []
    resolved = shutil.which("qmd")
    if resolved:
        cmd_path = Path(resolved).resolve()
        for parent in [cmd_path.parent, *cmd_path.parents]:
            js = parent / "node_modules" / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"
            if path_exists(js):
                candidates.append(js)
                break
    nvm_root = Path(os.environ.get("NVM_HOME", Path.home() / "AppData" / "Local" / "nvm"))
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    module_roots = [
        nvm_root / "node_modules",
        Path("C:/nvm4w/nodejs/node_modules"),
        appdata / "npm" / "node_modules",
        Path.home() / "AppData" / "Roaming" / "npm" / "node_modules",
    ]
    for module_root in module_roots:
        js = module_root / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"
        if js not in candidates:
            candidates.append(js)
    return candidates


def path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def qmd_config_requires_vector(config_path: Path) -> bool:
    if not config_path.exists():
        return False
    content = read_text(config_path).lower()
    return bool(re.search(r"(?m)^\s*(require_vector|vector_required)\s*:\s*true\s*$", content))


def qmd_bm25_probe(root: Path) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            _qmd_subprocess_args(["search", "__kb_capability_probe__", "-n", "1"]),
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def lint_qmd_index(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    config_path = root / "qmd.yml"
    if not config_path.exists():
        issues.append(Issue("info", "qmd_index_missing", "qmd.yml", "缺少 qmd 配置；阶段三检索层尚未初始化", "structure"))
        return issues

    caps = detect_qmd_capability(root)
    if caps.get("capability_mode") == "none":
        issues.append(
            Issue(
                "info",
                "qmd_index_missing",
                "qmd.yml",
                "未找到可用 qmd（native、WSL2 HTTP、WSL2 CLI 均不可用）；安装 `@tobilu/qmd` 后再构建本地检索索引",
                "structure",
            )
        )
        mcp_http = caps.get("mcp_http") or {}
        if os.environ.get("QMD_MCP_URL") and not mcp_http.get("available"):
            issues.append(
                Issue(
                    "info",
                    "qmd_mcp_http_down",
                    "qmd.yml",
                    f"配置了 QMD_MCP_URL={mcp_http.get('mcp_http_url') or os.environ.get('QMD_MCP_URL')}，但 qmd MCP HTTP 不可达",
                    "structure",
                )
            )
        return issues

    requires_vector = qmd_config_requires_vector(config_path)
    if requires_vector and not caps.get("vector_available"):
        issues.append(
            Issue(
                "warning",
                "qmd_vector_unavailable",
                "qmd.yml",
                f"qmd.yml 要求 vector/hybrid，但当前 capability_mode={caps.get('capability_mode')} 不支持向量；建议启动 WSL2 qmd HTTP daemon 或安装 WSL2 qmd CLI",
                "structure",
            )
        )

    mcp_http = caps.get("mcp_http") or {}
    if os.environ.get("QMD_MCP_URL") and not mcp_http.get("available"):
        issues.append(
            Issue(
                "info",
                "qmd_mcp_http_down",
                "qmd.yml",
                f"配置了 QMD_MCP_URL={mcp_http.get('mcp_http_url') or os.environ.get('QMD_MCP_URL')}，但 qmd MCP HTTP 不可达；向量搜索会降级到其他可用路径",
                "structure",
            )
        )

    native = caps.get("native") or {}
    status_stdout = native.get("native_status")
    if not status_stdout:
        return issues
    try:
        payload = json.loads(str(status_stdout))
    except json.JSONDecodeError:
        return issues

    indexed_at = find_qmd_timestamp(payload)
    if indexed_at:
        now = dt.datetime.now(dt.timezone.utc)
        if indexed_at.tzinfo is None:
            indexed_at = indexed_at.replace(tzinfo=dt.timezone.utc)
        if (now - indexed_at).days > QMD_INDEX_STALE_DAYS:
            issues.append(
                Issue(
                    "info",
                    "qmd_index_stale",
                    "qmd.yml",
                    f"qmd 索引时间超过 {QMD_INDEX_STALE_DAYS} 天，建议运行 `python tools/kb_search_bridge.py index --root . --kind lexical`；vector 索引仅在 WSL2/Linux 中显式构建",
                    "structure",
                )
            )
    return issues


def lint_operational_budgets(root: Path) -> list[Issue]:
    issues: list[Issue] = []

    agents_path = root / "AGENTS.md"
    if not agents_path.exists():
        issues.append(Issue("warning", "missing_agents_contract", "AGENTS.md", "缺少 always-loaded `AGENTS.md` 规约", "structure"))
    else:
        content = read_text(agents_path)
        tokens = estimated_tokens(content)
        if tokens > AGENTS_REGRESSION_TOKENS:
            issues.append(
                Issue(
                    "warning",
                    "agents_size_regression",
                    "AGENTS.md",
                    f"`AGENTS.md` 估算 {tokens} tokens，超过 {AGENTS_REGRESSION_TOKENS} 的常驻上下文回归预算",
                    "structure",
                )
            )
        elif tokens > AGENTS_REVIEW_TOKENS:
            issues.append(
                Issue(
                    "info",
                    "agents_size_review",
                    "AGENTS.md",
                    f"`AGENTS.md` 估算 {tokens} tokens，超过 {AGENTS_REVIEW_TOKENS}，建议审查是否可继续按需拆分",
                    "structure",
                )
            )

    skill_root = root / SKILL_SOURCE_REL
    if skill_root.is_dir():
        for skill_entry in sorted(skill_root.glob("*/SKILL.md")):
            tokens = estimated_tokens(read_text(skill_entry))
            if tokens > SKILL_ENTRY_REVIEW_TOKENS:
                issues.append(
                    Issue(
                        "info",
                        "skill_entry_too_large",
                        str(skill_entry.relative_to(root)),
                        f"`SKILL.md` 估算 {tokens} tokens，建议把细节移入 references/",
                        "structure",
                    )
                )

    source_snapshot = snapshot_files(root / SKILL_SOURCE_REL)
    if source_snapshot:
        for mirror_rel in configured_skill_mirror_rels(root):
            mirror_path = root / mirror_rel
            if not mirror_path.is_dir():
                issues.append(Issue("warning", "skill_mirror_missing", mirror_rel.as_posix(), "skill mirror 不存在", "structure"))
                continue
            mirror_snapshot = snapshot_files(mirror_path)
            if source_snapshot != mirror_snapshot:
                issues.append(
                    Issue(
                        "warning",
                        "skill_mirror_drift",
                        mirror_rel.as_posix(),
                        "skill mirror 与 `.agents/skills/` 不一致；运行 `python tools/sync_agent_skills.py`",
                        "structure",
                    )
                )

    return issues


SKELETON_SYNC_REL_PATHS = [
    "AGENTS.md",
    "schema/entity-relationship-model.md",
    "schema/output-format.md",
    "schema/theme-types.md",
    "schema/wiki-writing-standards.md",
    "schema/source-adapter-contract.md",
    "tools/sync_agent_skills.py",
]


def lint_skeleton_drift(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    skeleton_root = root / ".agents" / "skills" / "bootstrap" / "assets" / "skeleton"
    if not skeleton_root.is_dir():
        return issues

    for rel in SKELETON_SYNC_REL_PATHS:
        kb_file = root / rel
        skel_file = skeleton_root / rel
        if kb_file.exists() and skel_file.exists():
            if file_digest(kb_file) != file_digest(skel_file):
                issues.append(
                    Issue(
                        "warning",
                        "skeleton_structural_drift",
                        rel,
                        f"bootstrap skeleton 的 `{rel}` 与知识库版本不一致，可能导致新知识库继承旧架构",
                        "structure",
                    )
                )
        elif kb_file.exists() and not skel_file.exists():
            issues.append(
                Issue(
                    "warning",
                    "skeleton_file_missing",
                    rel,
                    f"知识库有 `{rel}` 但 bootstrap skeleton 中缺失，新知识库将缺少此文件",
                    "structure",
                )
            )

    kb_templates = root / "schema" / "templates"
    skel_templates = skeleton_root / "schema" / "templates"
    if kb_templates.is_dir() and skel_templates.is_dir():
        kb_template_files = {p.name for p in kb_templates.glob("*.md")}
        skel_template_files = {p.name for p in skel_templates.glob("*.md")}
        for name in sorted(kb_template_files - skel_template_files):
            issues.append(
                Issue(
                    "warning",
                    "skeleton_template_missing",
                    f"schema/templates/{name}",
                    f"知识库模板 `{name}` 在 bootstrap skeleton 中缺失",
                    "structure",
                )
            )
        for name in sorted(kb_template_files & skel_template_files):
            if file_digest(kb_templates / name) != file_digest(skel_templates / name):
                issues.append(
                    Issue(
                        "warning",
                        "skeleton_template_drift",
                        f"schema/templates/{name}",
                        f"bootstrap skeleton 的模板 `{name}` 与知识库版本不一致",
                        "structure",
                    )
                )

    return issues


def lint_themes(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    themes_dir = root / "themes"
    if not themes_dir.exists():
        return issues

    for category, theme_dir in iter_theme_dirs(root):
        if category == "uncategorized":
            issues.append(Issue("warning", "uncategorized_theme", str(theme_dir), "主题未放入 general/project/research 二级目录", "structure"))
        for filename in THEME_REQUIRED_FILES:
            path = theme_dir / filename
            if not path.exists():
                issues.append(Issue("error", "missing_theme_file", str(path), f"主题缺少 `{filename}`", "structure"))

        for dirname in THEME_REQUIRED_DIRS:
            path = theme_dir / dirname
            if not path.exists():
                issues.append(Issue("error", "missing_theme_dir", str(path), f"主题缺少 `{dirname}/`", "structure"))

        theme_type = extract_theme_type(theme_dir / "meta.md")
        if not theme_type:
            issues.append(Issue("error", "missing_theme_type", str(theme_dir / "meta.md"), "无法识别 `theme_type`", "structure"))
            continue
        if theme_type not in WIKI_REQUIRED_BY_TYPE:
            issues.append(
                Issue(
                    "error",
                    "unknown_theme_type",
                    str(theme_dir / "meta.md"),
                    f"未知主题类型 `{theme_type}`",
                    "structure",
                )
            )
            continue

        wiki_dir = theme_dir / "wiki"
        for filename in WIKI_REQUIRED_BY_TYPE[theme_type]:
            path = wiki_dir / filename
            if not path.exists():
                issues.append(
                    Issue(
                        "warning",
                        "missing_wiki_entry",
                        str(path),
                        f"`{theme_type}` 主题建议包含 `{filename}`",
                        "structure",
                    )
                )

    return issues


def lint_markdown_files(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    exact_notes, basenames, theme_names = build_note_index(root)

    for md_path in iter_markdown_files(root):
        content = read_text(md_path)
        relative = md_path.relative_to(root)

        if not content.strip():
            issues.append(Issue("warning", "empty_markdown", str(relative), "Markdown 文件为空", "structure"))
            continue

        if any(pattern in content for pattern in PLACEHOLDER_PATTERNS):
            issues.append(Issue("info", "placeholder_content", str(relative), "文件中包含占位符内容", "structure"))

        for raw_target in WIKILINK_RE.findall(content):
            target = normalize_wikilink_target(raw_target)
            if not resolve_wikilink(target, exact_notes, basenames, theme_names):
                issues.append(
                    Issue(
                        "warning",
                        "dead_wikilink",
                        str(relative),
                        f"存在无法解析的 wikilink `[[{raw_target}]]`",
                        "structure",
                    )
                )

    return issues


def lint_index(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    themes_dir = root / "themes"
    index_path = root / "index" / "themes.md"
    if not themes_dir.exists():
        return issues

    theme_names = {theme_dir.name for _category, theme_dir in iter_theme_dirs(root)}
    indexed_names = load_index_theme_names(index_path)

    if not index_path.exists():
        issues.append(Issue("error", "missing_index", str(index_path), "缺少 `index/themes.md`", "structure"))
        return issues

    for theme_name in sorted(theme_names - indexed_names):
        issues.append(
            Issue(
                "warning",
                "theme_not_indexed",
                str(index_path.relative_to(root)),
                f"主题 `{theme_name}` 未出现在 `index/themes.md` 中",
                "structure",
            )
        )

    return issues


def lint_graph(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    exact_notes, _basenames, _theme_names = build_note_index(root)
    canonical_pages = [path for path in iter_markdown_files(root) if is_canonical_page(root, path)]

    incoming_links: dict[str, int] = {canonical_ref(root, path): 0 for path in canonical_pages}
    body_relation_links: dict[str, set[str]] = {canonical_ref(root, path): set() for path in canonical_pages}

    for md_path in iter_markdown_files(root):
        content = read_text(md_path)
        current_ref = md_path.relative_to(root).as_posix().removesuffix(".md")
        for raw_target in WIKILINK_RE.findall(content):
            target = normalize_wikilink_target(raw_target)
            if target in incoming_links and target != current_ref:
                incoming_links[target] += 1
            if current_ref in body_relation_links and target.startswith("shared/"):
                body_relation_links[current_ref].add(target)

    required_fields = ["title", "node_type", "status", "themes", "source_pages", "updated"]
    relation_fields = ["related_assets", "related_entities", "related_concepts", "related_patterns", "related_methods", "related_themes"]
    allowed_node_types = {"asset", "entity", "concept", "pattern", "method", "glossary"}
    asset_required_fields = [
        "asset_type",
        "source_projects",
        "suitable_for",
        "not_suitable_for",
        "tech_stack",
        "dependencies",
        "license",
        "license_compatibility",
        "maturity",
        "reuse_level",
        "reuse_cost",
        "confidence",
        "evidence_from",
    ]
    asset_allowed_values = {
        "reuse_level": {"direct", "adapt", "reference", "reject"},
        "reuse_cost": {"low", "medium", "high"},
        "confidence": {"confirmed", "inferred", "tentative"},
    }

    for path in canonical_pages:
        relative = path.relative_to(root)
        ref = canonical_ref(root, path)
        frontmatter, body = extract_frontmatter(read_text(path))

        for field in required_fields:
            value = frontmatter.get(field)
            if value is None or value == [] or value == "":
                issues.append(Issue("warning", "canonical_missing_field", str(relative), f"canonical node 缺少 `{field}` 字段", "graph"))

        node_type = frontmatter_scalar(frontmatter, "node_type")
        if node_type and node_type not in allowed_node_types:
            issues.append(Issue("error", "canonical_bad_node_type", str(relative), f"未知 node_type `{node_type}`", "graph"))

        if node_type == "asset":
            for field in asset_required_fields:
                value = frontmatter.get(field)
                if value is None or value == [] or value == "":
                    issues.append(Issue("warning", "asset_missing_field", str(relative), f"technical asset 缺少 `{field}` 字段", "graph"))
            for field, allowed_values in asset_allowed_values.items():
                value = frontmatter_scalar(frontmatter, field)
                if value and value not in allowed_values:
                    allowed = ", ".join(sorted(allowed_values))
                    issues.append(Issue("warning", "asset_bad_value", str(relative), f"`{field}` 值 `{value}` 不在允许范围：{allowed}", "graph"))

        for field in ["themes", "source_pages", "evidence_from", "source_projects", *relation_fields]:
            for item in frontmatter_list(frontmatter, field):
                if field.startswith("related_") or field in {"themes", "source_pages", "evidence_from", "source_projects"}:
                    if item.startswith("http://") or item.startswith("https://"):
                        continue
                    if not resolve_repo_ref(root, item):
                        issues.append(Issue("warning", "graph_bad_reference", str(relative), f"`{field}` 指向不存在的路径 `{item}`", "graph"))

        if incoming_links.get(ref, 0) == 0:
            issues.append(Issue("warning", "orphan_canonical", str(relative), "canonical node 没有来自其他页面的 wikilink", "graph"))

        frontmatter_related = set()
        for field in relation_fields:
            frontmatter_related.update(item.removesuffix(".md") for item in frontmatter_list(frontmatter, field) if item.startswith("shared/"))
        body_related = body_relation_links.get(ref, set())
        missing_from_frontmatter = sorted(body_related - frontmatter_related - {ref})
        for target in missing_from_frontmatter:
            if target in exact_notes:
                issues.append(
                    Issue(
                        "info",
                        "relation_missing_frontmatter",
                        str(relative),
                        f"正文链接 `{target}` 未出现在 related_* 字段中",
                        "graph",
                    )
                )

    return issues


def lint_knowledge(root: Path) -> list[Issue]:
    issues: list[Issue] = []

    for path in iter_semantic_markdown_files(root):
        relative = path.relative_to(root)
        content = read_text(path)
        frontmatter, body = extract_frontmatter(content)

        if is_canonical_page(root, path):
            meaningful_body = strip_template_noise(body)
            template_markers = [
                "这个实体是什么，它在当前知识库中扮演什么角色。",
                "这个概念的最小稳定定义是什么。",
                "这项技术资产提供什么可复用能力。",
                "## 当前结论\n\n- \n- \n-",
                "## 未决问题\n\n- \n- \n-",
            ]
            if len(meaningful_body) < 80 or any(marker in body for marker in template_markers):
                issues.append(Issue("warning", "canonical_template_body", str(relative), "canonical node 正文仍像模板占位，缺少可查询知识", "knowledge"))

            if not frontmatter_list(frontmatter, "evidence_from") and not frontmatter_list(frontmatter, "source_pages"):
                issues.append(Issue("warning", "canonical_missing_evidence", str(relative), "canonical node 缺少 evidence/source 链路", "knowledge"))

        if "outputs/" in relative.as_posix() and relative.name != "README.md":
            if len(strip_template_noise(content)) < 80:
                issues.append(Issue("info", "thin_output", str(relative), "output 页面内容较薄，可能尚未形成工程行动视图", "knowledge"))
            if "## Sources" in content and "- Wiki:" in content and "- Evidence:" in content:
                if not re.search(r"\[\[[^\]]+\]\]|themes/|shared/", content):
                    issues.append(Issue("info", "output_missing_sources", str(relative), "output 页面缺少指向 wiki/shared 的来源链接", "knowledge"))

    for _category, theme_dir in iter_theme_dirs(root):
        outputs_dir = theme_dir / "outputs"
        for filename in ["engineering-brief.md", "implementation-guide.md", "decision-brief.md", "backlog.md", "reuse-candidates.md"]:
            path = outputs_dir / filename
            if not path.exists():
                issues.append(
                    Issue(
                        "info",
                        "missing_engineering_output",
                        str(path.relative_to(root)),
                        f"主题缺少工程行动输出 `{filename}`",
                        "knowledge",
                    )
                )

    return issues


def lint_semantic_knowledge(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    canonical_pages = [path for path in iter_markdown_files(root) if is_canonical_page(root, path)]

    for path in iter_semantic_markdown_files(root):
        relative = path.relative_to(root)
        content = read_text(path)
        frontmatter, body = extract_frontmatter(content)
        updated = parse_frontmatter_date(frontmatter, "updated")
        refs = [
            *frontmatter_list(frontmatter, "source_pages"),
            *frontmatter_list(frontmatter, "evidence_from"),
        ]
        ref_dates = []
        for ref in refs:
            ref_path = resolve_repo_path(root, ref)
            if ref_path:
                ref_date = path_mtime_date(ref_path)
                if ref_date:
                    ref_dates.append((ref, ref_date))
        if updated and ref_dates:
            newest_ref, newest_ref_date = max(ref_dates, key=lambda item: item[1])
            if newest_ref_date > updated:
                issues.append(
                    Issue(
                        "info",
                        "stale_page",
                        str(relative),
                        f"`updated` 早于引用来源 `{newest_ref}` 的文件时间，可能需要重新编译 wiki 结论",
                        "knowledge",
                    )
                )

        lower_content = body.lower()
        conflict_markers = ["contradict", "conflict", "inconsistent", "冲突", "矛盾", "不一致", "存疑", "被否决"]
        has_conflict_language = any(marker in lower_content for marker in conflict_markers)
        has_contradicts = bool(frontmatter_list(frontmatter, "contradicts"))
        has_open_question_link = "open-questions" in lower_content or "未决" in content or "unknown" in lower_content
        if has_conflict_language and not has_contradicts and not has_open_question_link:
            issues.append(
                Issue(
                    "info",
                    "contradiction_gap",
                    str(relative),
                    "页面出现冲突/存疑语义，但未写入 `contradicts` 或 open questions 链路",
                    "knowledge",
                )
            )

        evidence_refs = frontmatter_list(frontmatter, "evidence_from")
        if evidence_refs and is_canonical_page(root, path):
            has_traceability_section = any(marker in body.lower() for marker in ["evidence", "source", "sources", "confidence"]) or any(
                marker in body for marker in ["证据", "来源", "置信", "原始资料", "抽取"]
            )
            referenced_name_present = any(Path(normalize_path_ref(ref)).stem.lower() in body.lower() for ref in evidence_refs)
            if not has_traceability_section and not referenced_name_present:
                issues.append(
                    Issue(
                        "info",
                        "source_drift",
                        str(relative),
                        "`evidence_from` 存在，但正文缺少可追溯证据说明或来源名称",
                        "knowledge",
                    )
                )

    identifier_to_paths: dict[str, list[Path]] = {}
    title_by_path: dict[Path, str] = {}
    for path in canonical_pages:
        frontmatter, _body = extract_frontmatter(read_text(path))
        title = frontmatter_scalar(frontmatter, "title") or path.stem
        title_by_path[path] = title
        identifiers = [title, path.stem, *frontmatter_list(frontmatter, "aliases")]
        for identifier in identifiers:
            normalized = normalize_identifier(identifier)
            if normalized:
                identifier_to_paths.setdefault(normalized, []).append(path)

    for identifier, paths in sorted(identifier_to_paths.items()):
        unique_paths = sorted(set(paths), key=lambda item: item.relative_to(root).as_posix())
        if len(unique_paths) > 1:
            display_paths = ", ".join(path.relative_to(root).as_posix() for path in unique_paths)
            issues.append(
                Issue(
                    "warning",
                    "duplicate_canonical_node",
                    display_paths,
                    f"多个 canonical nodes 共享 title/alias `{identifier}`",
                    "knowledge",
                )
            )

    compared: set[tuple[Path, Path]] = set()
    for left in canonical_pages:
        for right in canonical_pages:
            if left >= right or (left, right) in compared:
                continue
            compared.add((left, right))
            left_title = normalize_identifier(title_by_path.get(left, left.stem))
            right_title = normalize_identifier(title_by_path.get(right, right.stem))
            if not left_title or not right_title:
                continue
            similarity = difflib.SequenceMatcher(None, left_title, right_title).ratio()
            if similarity >= 0.9:
                issues.append(
                    Issue(
                        "info",
                        "similar_canonical_node",
                        f"{left.relative_to(root).as_posix()} | {right.relative_to(root).as_posix()}",
                        f"canonical node 标题相似度较高 ({similarity:.2f})，需要确认是否重复概念",
                        "knowledge",
                    )
                )

    for _category, theme_dir in iter_theme_dirs(root):
        wiki_dir = theme_dir / "wiki"
        outputs_dir = theme_dir / "outputs"
        if not wiki_dir.exists() or not outputs_dir.exists():
            continue
        wiki_files = [theme_dir / "README.md", theme_dir / "meta.md", *iter_markdown_files(wiki_dir)]
        wiki_dates = [(path, path_mtime_date(path)) for path in wiki_files if path.exists()]
        wiki_dates = [(path, date) for path, date in wiki_dates if date]
        if not wiki_dates:
            continue
        newest_wiki_path, newest_wiki_date = max(wiki_dates, key=lambda item: item[1])
        for filename in ["engineering-brief.md", "implementation-guide.md", "decision-brief.md", "backlog.md", "reuse-candidates.md", "asset-match-brief.md"]:
            output_path = outputs_dir / filename
            if not output_path.exists():
                continue
            output_date = path_mtime_date(output_path)
            if output_date and newest_wiki_date > output_date:
                issues.append(
                    Issue(
                        "info",
                        "output_stale",
                        str(output_path.relative_to(root)),
                        f"主题 wiki `{newest_wiki_path.relative_to(root).as_posix()}` 比 output 更新，行动视图可能过期",
                        "knowledge",
                    )
                )

    return issues


def shared_nodes_by_kind(root: Path, kind: str) -> list[Path]:
    directory = root / "shared" / kind
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.glob("*.md") if path.name.lower() != "readme.md"),
        key=lambda item: item.relative_to(root).as_posix().lower(),
    )


def theme_dir_from_ref(root: Path, reference: str) -> Path | None:
    raw = normalize_path_ref(reference)
    if not raw.startswith("themes/"):
        return None
    parts = raw.split("/")
    if len(parts) < 3:
        return None
    theme_dir = root / parts[0] / parts[1] / parts[2]
    return theme_dir if theme_dir.is_dir() else None


def lint_shared_discoverability(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    technical_assets_index = root / "index" / "technical-assets.md"
    technical_assets_content = read_text(technical_assets_index) if technical_assets_index.exists() else ""

    for kind in ["concepts", "patterns"]:
        nodes = shared_nodes_by_kind(root, kind)
        readme = root / "shared" / kind / "README.md"
        readme_content = read_text(readme) if readme.exists() else ""

        for node_path in nodes:
            node_ref = canonical_ref(root, node_path)
            if node_ref not in readme_content:
                issues.append(
                    Issue(
                        "info",
                        "shared_index_missing_entry",
                        str(readme.relative_to(root)),
                        f"`{node_ref}` 未出现在 shared/{kind}/README.md 中",
                        "knowledge",
                    )
                )
            if node_ref not in technical_assets_content:
                issues.append(
                    Issue(
                        "info",
                        "index_missing_shared_node",
                        str(technical_assets_index.relative_to(root)),
                        f"`{node_ref}` 未出现在 index/technical-assets.md 中",
                        "knowledge",
                    )
                )

            frontmatter, _body = extract_frontmatter(read_text(node_path))
            theme_dirs = []
            for theme_ref in frontmatter_list(frontmatter, "themes"):
                theme_dir = theme_dir_from_ref(root, theme_ref)
                if theme_dir and theme_dir not in theme_dirs:
                    theme_dirs.append(theme_dir)

            for theme_dir in theme_dirs:
                theme_files = [theme_dir / "README.md", *iter_markdown_files(theme_dir / "wiki")]
                theme_text = "\n".join(read_text(path) for path in theme_files if path.exists())
                if node_ref not in theme_text:
                    issues.append(
                        Issue(
                            "info",
                            "theme_missing_shared_backlink",
                            str(node_path.relative_to(root)),
                            f"`{node_ref}` 声明关联 `{theme_dir.relative_to(root).as_posix()}`，但该主题 README/wiki 未链接回 shared node",
                            "knowledge",
                        )
                    )

    return issues


def lint_reuse_chain(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    assets = shared_asset_refs(root)
    asset_matches: dict[str, list[str]] = {asset: [] for asset in assets}

    for _category, theme_dir in iter_theme_dirs(root):
        outputs_dir = theme_dir / "outputs"
        reuse_path = outputs_dir / "reuse-candidates.md"
        if reuse_path.exists():
            for candidate in parse_reuse_candidate_rows(read_text(reuse_path)):
                refs = [str(ref) for ref in candidate.get("asset_refs", [])]
                reuse_level = str(candidate.get("reuse_level") or "").lower()
                asset_label = str(candidate.get("asset") or "").strip()
                if refs:
                    for ref in refs:
                        if ref not in assets:
                            issues.append(
                                Issue(
                                    "warning",
                                    "reuse_candidate_missing_asset",
                                    str(reuse_path.relative_to(root)),
                                    f"reuse-candidates 引用的候选资产 `{ref}` 不存在于 shared/assets",
                                    "knowledge",
                                )
                            )
                    continue
                if reuse_level in REUSE_LEVELS_FOR_PROMOTION_WARNING:
                    issues.append(
                        Issue(
                            "warning",
                            "reuse_candidate_not_promoted",
                            str(reuse_path.relative_to(root)),
                            f"`{asset_label}` 复用级别为 `{reuse_level}`，但未链接到已提升的 shared/assets 技术资产",
                            "knowledge",
                        )
                    )
                elif reuse_level in REUSE_LEVELS_FOR_PROMOTION_INFO:
                    issues.append(
                        Issue(
                            "info",
                            "reuse_candidate_not_promoted",
                            str(reuse_path.relative_to(root)),
                            f"`{asset_label}` 复用级别为 `reference`，可按需评估是否提升到 shared/assets",
                            "knowledge",
                        )
                    )

        match_path = outputs_dir / "asset-match-brief.md"
        if match_path.exists():
            for ref in [target for target in markdown_links(read_text(match_path)) if target.startswith("shared/assets/")]:
                if ref not in assets:
                    issues.append(
                        Issue(
                            "error",
                            "asset_match_missing_asset",
                            str(match_path.relative_to(root)),
                            f"asset-match-brief 引用的候选资产 `{ref}` 不存在于 shared/assets",
                            "knowledge",
                        )
                    )
                else:
                    asset_matches.setdefault(ref, []).append(match_path.relative_to(root).as_posix())

    for asset in sorted(assets):
        if not asset_matches.get(asset):
            issues.append(
                Issue(
                    "info",
                    "asset_without_match_brief",
                    asset + ".md",
                    "shared/assets 技术资产尚未被任何目标项目 asset-match-brief 引用",
                    "knowledge",
                )
            )

    return issues


def lint_project_freshness(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    reported_stale: set[str] = set()
    report_path = root / "outputs" / "freshness" / "latest.json"
    if report_path.exists():
        try:
            payload = json.loads(read_text(report_path))
        except json.JSONDecodeError:
            payload = {}
        for item in payload.get("items", []) if isinstance(payload, dict) else []:
            if str(item.get("status") or "").lower() == "stale":
                theme = str(item.get("theme") or "unknown")
                reported_stale.add(theme)
                issues.append(
                    Issue(
                        "warning",
                        "project_stale",
                        rel_display(root, report_path),
                        f"`{theme}` 的 freshness report 标记为 stale；需要生成/审阅 diff evidence 后再 ingest affected pages",
                        "knowledge",
                    )
                )

    for _category, theme_dir in iter_theme_dirs(root):
        if _category != "project":
            continue
        theme_ref = theme_dir.relative_to(root).as_posix()
        if theme_ref in reported_stale:
            continue
        sync_status = theme_dir / "outputs" / "sync-status.md"
        if not sync_status.exists():
            continue
        content = read_text(sync_status).lower()
        if re.search(r"freshness(?:\s+status)?\s*:\s*`?stale`?", content):
            issues.append(
                Issue(
                    "warning",
                    "project_stale",
                    rel_display(root, sync_status),
                    f"`{theme_ref}` 的 sync-status 标记为 stale；需要刷新 project-reverse evidence",
                    "knowledge",
                )
            )

    return issues


def lint_graphify_integration(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    bridge_path = root / "tools" / "kb_graphify_bridge.py"
    if not bridge_path.exists():
        issues.append(
            Issue(
                "info",
                "graphify_bridge_missing",
                "tools/kb_graphify_bridge.py",
                "缺少 Graphify bridge；无法生成结构图谱 evidence",
                "structure",
            )
        )

    allowed_sensitivity = {"public", "internal", "confidential", "restricted", "unknown"}
    allowed_retention = {"keep", "review", "expire"}
    allowed_confidence = {"confirmed", "inferred", "tentative"}

    for evidence_path in sorted(root.glob("themes/*/*/outputs/document-intake/graphify/graphify-evidence.json")):
        relative = evidence_path.relative_to(root).as_posix()
        graphify_dir = evidence_path.parent
        required_artifacts = ["graph.json", "GRAPH_REPORT.md", "graphify-source-anchor.md"]
        for filename in required_artifacts:
            if not (graphify_dir / filename).exists():
                issues.append(
                    Issue(
                        "warning",
                        "graphify_evidence_incomplete",
                        relative,
                        f"Graphify evidence 缺少 `{filename}`",
                        "knowledge",
                    )
                )
        try:
            payload = json.loads(read_text(evidence_path))
        except json.JSONDecodeError:
            issues.append(Issue("warning", "graphify_evidence_invalid_json", relative, "Graphify evidence 不是有效 JSON", "knowledge"))
            continue
        if payload.get("schema_version") != "evidence.v1":
            issues.append(Issue("warning", "graphify_bad_metadata", relative, "Graphify evidence 必须使用 `evidence.v1` envelope", "knowledge"))
        for field in ["source_id", "sensitivity", "retention", "confidence"]:
            if not payload.get(field):
                issues.append(Issue("warning", "graphify_bad_metadata", relative, f"Graphify evidence 缺少 `{field}`", "knowledge"))
        sensitivity = str(payload.get("sensitivity") or "")
        retention = str(payload.get("retention") or "")
        confidence = str(payload.get("confidence") or "")
        if sensitivity and sensitivity not in allowed_sensitivity:
            issues.append(Issue("warning", "graphify_bad_metadata", relative, f"`sensitivity` 值 `{sensitivity}` 不合法", "knowledge"))
        if retention and retention not in allowed_retention:
            issues.append(Issue("warning", "graphify_bad_metadata", relative, f"`retention` 值 `{retention}` 不合法", "knowledge"))
        if confidence and confidence not in allowed_confidence:
            issues.append(Issue("warning", "graphify_bad_metadata", relative, f"`confidence` 值 `{confidence}` 不合法", "knowledge"))

        anchor_path = graphify_dir / "graphify-source-anchor.md"
        if anchor_path.exists():
            anchor = read_text(anchor_path)
            for marker in ["source_id", "source_uri", "captured_at", "provider"]:
                if marker not in anchor:
                    issues.append(
                        Issue(
                            "warning",
                            "graphify_source_anchor_incomplete",
                            anchor_path.relative_to(root).as_posix(),
                            f"Graphify source anchor 缺少 `{marker}`",
                            "knowledge",
                        )
                    )

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir() and path.name in {"graphify-cache", "graphify-out"} and "/runtime/" not in f"/{rel}/":
            issues.append(
                Issue(
                    "warning",
                    "graphify_runtime_artifact",
                    rel,
                    "Graphify runtime/cache 产物不应进入 durable wiki；仅允许放在被忽略的 graphify/runtime/ 下",
                    "structure",
                )
            )
        if path.is_file() and path.name.lower() == "graph.html" and "/runtime/" not in f"/{rel}":
            issues.append(
                Issue(
                    "warning",
                    "graphify_runtime_artifact",
                    rel,
                    "`graph.html` 是运行态可视化，不应作为 durable wiki artifact",
                    "structure",
                )
            )

    for sources_dir in root.glob("themes/*/*/sources"):
        for git_dir in sources_dir.rglob(".git"):
            issues.append(
                Issue(
                    "error",
                    "source_checkout_in_sources",
                    git_dir.relative_to(root).as_posix(),
                    "`sources/` 下发现完整 Git checkout；只允许保存 source anchor 和原始资料",
                    "structure",
                )
            )

    global_index = root / "outputs" / "document-intake" / "graphify" / "global-graph-index.json"
    if global_index.exists():
        try:
            payload = json.loads(read_text(global_index))
        except json.JSONDecodeError:
            issues.append(Issue("warning", "graphify_global_invalid_json", global_index.relative_to(root).as_posix(), "Graphify global index 不是有效 JSON", "knowledge"))
            return issues
        for item in payload.get("projects", []) if isinstance(payload, dict) else []:
            graph_ref = str(item.get("graph_path") or "")
            if graph_ref and not resolve_repo_ref(root, graph_ref):
                issues.append(
                    Issue(
                        "warning",
                        "graphify_global_missing_graph",
                        global_index.relative_to(root).as_posix(),
                        f"Graphify global index 指向不存在的 graph `{graph_ref}`",
                        "knowledge",
                    )
                )

    return issues


def summarize(issues: Iterable[Issue]) -> dict[str, int]:
    result = {"error": 0, "warning": 0, "info": 0}
    for issue in issues:
        result[issue.severity] += 1
    return result


def summarize_by_scope(issues: Iterable[Issue]) -> dict[str, dict[str, int]]:
    result = {
        "structure": {"error": 0, "warning": 0, "info": 0},
        "graph": {"error": 0, "warning": 0, "info": 0},
        "knowledge": {"error": 0, "warning": 0, "info": 0},
    }
    for issue in issues:
        if issue.scope not in result:
            result[issue.scope] = {"error": 0, "warning": 0, "info": 0}
        result[issue.scope][issue.severity] += 1
    return result


def print_text(issues: list[Issue], summary: dict[str, int]) -> None:
    print("KB Lint Result")
    print(f"errors={summary['error']} warnings={summary['warning']} info={summary['info']}")
    if not issues:
        print("No issues found.")
        return
    for issue in issues:
        print(f"[{issue.severity.upper()}] {issue.scope}:{issue.code} {issue.path} - {issue.message}")


def top_issues(issues: list[Issue], limit: int) -> list[Issue]:
    return sorted(issues, key=lambda item: (*issue_priority(item), item.scope, item.path, item.code))[: max(limit, 0)]


def print_summary_mode(issues: list[Issue], summary: dict[str, int], by_scope: dict[str, dict[str, int]], limit: int) -> None:
    print("KB Lint Summary")
    print(f"errors={summary['error']} warnings={summary['warning']} info={summary['info']}")
    print(
        "by_scope="
        + ", ".join(
            f"{scope}:e{counts['error']}/w{counts['warning']}/i{counts['info']}"
            for scope, counts in by_scope.items()
        )
    )
    selected = top_issues(issues, limit)
    if not selected:
        print("No issues found.")
        return
    print(f"Top {len(selected)} actionable gaps:")
    for issue in selected:
        print(f"- [{issue.severity.upper()}] {issue.scope}:{issue.code} {issue.path} - {issue.message}")


def log_lint_operation(root: Path, summary: dict[str, int], status: str) -> None:
    append_activity_log(
        root,
        skill="lint",
        action="lint",
        summary=f"执行知识库 lint：errors={summary['error']} warnings={summary['warning']} info={summary['info']}",
        status=status,
        details=[f"root={root}"],
    )


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    issues: list[Issue] = []
    if args.scope in {"structure", "all"}:
        issues.extend(lint_root(root))
        issues.extend(lint_qmd_index(root))
        issues.extend(lint_operational_budgets(root))
        issues.extend(lint_skeleton_drift(root))
        issues.extend(lint_themes(root))
        issues.extend(lint_markdown_files(root))
        issues.extend(lint_index(root))
    if args.scope in {"graph", "all"}:
        issues.extend(lint_graph(root))
    if args.scope in {"knowledge", "all"}:
        issues.extend(lint_knowledge(root))
        issues.extend(lint_semantic_knowledge(root))
        issues.extend(lint_shared_discoverability(root))
        issues.extend(lint_reuse_chain(root))
        issues.extend(lint_project_freshness(root))
    if args.scope in {"structure", "knowledge", "all"}:
        issues.extend(lint_graphify_integration(root))

    issues.sort(key=lambda item: (("error", "warning", "info").index(item.severity), item.scope, item.path, item.code))
    summary = summarize(issues)
    by_scope = summarize_by_scope(issues)

    if args.format == "json":
        print(
            json.dumps(
                {
                    "root": str(root),
                    "scope": args.scope,
                    "summary": summary,
                    "by_scope": by_scope,
                    "top_issues": [asdict(i) for i in top_issues(issues, args.summary_top)],
                    "issues": [asdict(i) for i in issues],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.summary:
        print_summary_mode(issues, summary, by_scope, args.summary_top)
    else:
        print_text(issues, summary)

    has_errors = summary["error"] > 0
    has_warnings = summary["warning"] > 0
    lint_status = "issues-found" if has_errors or has_warnings else "completed"
    log_lint_operation(root, summary, lint_status)
    if has_errors or (args.strict and has_warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
