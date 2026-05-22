from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any

from ..core.assets import assets_root
from ..mcp.service import LLMWikiService
from .types import AgentRequest


MAX_PAGE_CHARS = 8_000
MAX_SOURCE_CHARS = 16_000
INGEST_TYPES = {"auto", "requirement"}
DEFAULT_INGEST_OUTPUT_TEMPLATE_PATHS = [
    "outputs/engineering-brief.md",
    "outputs/implementation-guide.md",
    "outputs/decision-brief.md",
    "outputs/backlog.md",
    "outputs/reuse-candidates.md",
    "outputs/asset-match-brief.md",
]
SYNTHESIZE_OUTPUT_TEMPLATE_PATHS = [
    "asset-match-brief.md",
    "engineering-brief.md",
    "implementation-guide.md",
    "decision-brief.md",
    "backlog.md",
]
BASELINE_QUERY_PAGES = [
    "index/home.md",
    "index/themes.md",
    "index/cross-theme-map.md",
    "index/technical-assets.md",
]


def build_query_request(root: Path, question: str, *, top: int = 10) -> AgentRequest:
    kb_root = root.resolve()
    service = LLMWikiService(kb_root)
    search_payload = service.search(query=question, mode="auto", top=top, allow_fallback=True)
    pages = _read_context_pages(service, _baseline_and_search_paths(search_payload))
    instructions = _skill_text(kb_root, "query", "SKILL.md") + "\n\n" + _skill_text(kb_root, "query", "references/workflow.md")
    return AgentRequest(
        operation="query",
        root=kb_root,
        task={"question": question},
        instructions=instructions,
        context={
            "manifest": service.manifest_summary(),
            "search": search_payload,
            "pages": pages,
        },
    )


def build_ingest_request(
    root: Path,
    source: str,
    *,
    ingest_type: str = "auto",
    target_theme: str = "",
    git_analysis_options: dict[str, Any] | None = None,
) -> AgentRequest:
    kb_root = root.resolve()
    service = LLMWikiService(kb_root)
    normalized_type = ingest_type if ingest_type in INGEST_TYPES else "auto"
    normalized_target_theme = _clean_theme_path(target_theme)
    instructions = _skill_text(kb_root, "ingest", "SKILL.md") + "\n\n" + _skill_text(kb_root, "ingest", "references/workflow.md")
    output_templates = _build_ingest_output_templates(kb_root, normalized_type, normalized_target_theme)
    instructions += (
        "\n\n## Generate Outputs\n"
        "- Use `context.generate_outputs.templates` as preferred skeletons for proposed engineering outputs.\n"
        "- Prefer target-theme-local outputs when `task.target_theme` is set.\n"
        "- Keep output claims linked to durable wiki pages, shared assets, or evidence artifacts.\n"
    )
    if normalized_type == "requirement":
        requirement_path = _theme_output_path(normalized_target_theme, "requirement-analysis.md")
        instructions += (
            "\n\n## Requirement Ingest Override\n"
            "- Treat the source as a requirement document instead of a generic note.\n"
            "- Extract functional requirements, non-functional constraints, technical constraints, acceptance criteria, and key entities.\n"
            f"- Propose a write to `{requirement_path}` using the provided template.\n"
            "- Give each requirement a stable ID, priority, confidence, evidence link, and related modules/entities when known.\n"
        )
    return AgentRequest(
        operation="ingest",
        root=kb_root,
        task={
            "source": source,
            "source_type": normalized_type,
            "target_theme": normalized_target_theme,
            "git_analysis_options": git_analysis_options or {},
        },
        instructions=instructions,
        context={
            "manifest": service.manifest_summary(),
            "inventory": _ingest_inventory(kb_root),
            "source": _source_context(kb_root, source),
            "reuse_scan": _scan_reuse(kb_root),
            "baseline_pages": _read_context_pages(service, BASELINE_QUERY_PAGES),
            "generate_outputs": {
                "enabled": bool(output_templates),
                "guide": _schema_text(kb_root, "output-format.md"),
                "templates": output_templates,
            },
            "output_templates": output_templates,
        },
    )


def build_synthesize_request(root: Path, target_theme: str, *, top: int = 20, search_mode: str = "auto") -> AgentRequest:
    kb_root = root.resolve()
    service = LLMWikiService(kb_root)
    normalized_target_theme = _clean_theme_path(target_theme)
    if not normalized_target_theme:
        raise ValueError("synthesize requires --target-theme under themes/<category>/<theme>")
    helper = _load_synthesize_module(kb_root)
    synthesis_context = helper.collect_synthesis_context(kb_root, normalized_target_theme, max_chars=MAX_PAGE_CHARS)
    synthesis_pipeline = helper.build_synthesis_pipeline(kb_root, normalized_target_theme, top=top, max_chars=MAX_PAGE_CHARS, search_mode=search_mode)
    output_templates = [
        {
            "path": _theme_output_path(normalized_target_theme, name),
            "content": _schema_text(kb_root, f"templates/{name.replace('.md', '.template.md')}"),
        }
        for name in SYNTHESIZE_OUTPUT_TEMPLATE_PATHS
    ]
    output_templates = [item for item in output_templates if item["content"].strip()]
    instructions = _skill_text(kb_root, "synthesize", "SKILL.md") + "\n\n" + _skill_text(kb_root, "synthesize", "references/workflow.md")
    instructions += (
        "\n\n## Synthesis Contract\n"
        "- Generate target-theme-local outputs only; do not rewrite raw sources.\n"
        "- Treat `requirement-analysis.md` as demand-side input, not as a proven reusable asset.\n"
        "- Use `context.synthesis_pipeline` as the deterministic baseline for matches, license risks, reuse cost, validation tasks, wikilinks, and promotion proposals.\n"
        "- Recommend shared asset or pattern promotion only when evidence is cross-theme and source-backed; include such writes only when confidence is explicit.\n"
        "- Flag license, coupling, freshness, and vulnerability uncertainty as risks rather than legal conclusions.\n"
    )
    search_payload = service.search(query=normalized_target_theme, mode="auto", top=top, allow_fallback=True)
    return AgentRequest(
        operation="synthesize",
        root=kb_root,
        task={"target_theme": normalized_target_theme},
        instructions=instructions,
        context={
            "manifest": service.manifest_summary(),
            "target_theme": normalized_target_theme,
            "search": search_payload,
            "synthesis": synthesis_context,
            "synthesis_pipeline": synthesis_pipeline,
            "output_templates": output_templates,
        },
    )


def build_lint_request(root: Path, lint_payload: dict[str, Any], *, fix_plan: bool) -> AgentRequest:
    kb_root = root.resolve()
    instructions = _skill_text(kb_root, "lint", "SKILL.md") + "\n\n" + _skill_text(kb_root, "lint", "references/workflow.md")
    return AgentRequest(
        operation="lint",
        root=kb_root,
        task={"mode": "fix_plan" if fix_plan else "explain"},
        instructions=instructions,
        context={"lint": lint_payload},
    )


def _read_context_pages(service: LLMWikiService, paths: list[str]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        clean = _clean_page_path(path)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        page = service.read_page(clean, max_chars=MAX_PAGE_CHARS)
        if page.get("status") == "ok":
            pages.append(page)
    return pages


def _baseline_and_search_paths(search_payload: dict[str, Any]) -> list[str]:
    paths = list(BASELINE_QUERY_PAGES)
    for value in _walk_values(search_payload):
        if isinstance(value, str):
            clean = _clean_page_path(value)
            if clean:
                paths.append(clean)
    return paths


def _clean_page_path(value: str) -> str:
    text = value.strip().replace("\\", "/")
    if text.startswith("llm-wiki://page/"):
        text = text.removeprefix("llm-wiki://page/")
    if "#" in text:
        text = text.split("#", 1)[0]
    text = text.strip().strip('"').strip("'").lstrip("./")
    if not text.endswith(".md"):
        return ""
    try:
        rel = PurePosixPath(text)
    except ValueError:
        return ""
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        return ""
    return rel.as_posix()


def _source_context(root: Path, source: str) -> dict[str, Any]:
    path = Path(source).expanduser()
    if path.exists():
        resolved = path.resolve()
        if resolved.is_dir():
            return {
                "kind": "directory",
                "path": str(resolved),
                "files": _directory_sample(resolved),
            }
        extracted = _extract_document(root, resolved)
        if extracted:
            return {"kind": "file", "path": str(resolved), "extracted": extracted}
        return {
            "kind": "file",
            "path": str(resolved),
            "preview": _read_text_limited(resolved, MAX_SOURCE_CHARS),
        }
    return {"kind": "external", "source": source, "note": "source was not fetched by the CLI; agent should request evidence if needed"}


def _directory_sample(path: Path) -> list[str]:
    files = []
    for item in sorted(path.rglob("*"), key=lambda p: p.as_posix().lower()):
        if item.is_file():
            rel = item.relative_to(path).as_posix()
            if ".git/" not in f"{rel}/" and "__pycache__" not in item.parts:
                files.append(rel)
        if len(files) >= 200:
            break
    return files


def _ingest_inventory(root: Path) -> dict[str, Any]:
    core = _load_ingest_core(root)
    try:
        inbox_classification = core.classify_inbox(root) if hasattr(core, "classify_inbox") else {}
        themes = core.collect_theme_summaries(root)
        return {
            "themes": [asdict(theme) for theme in themes],
            "inbox": core.collect_inbox_files(root),
            "inbox_classification": inbox_classification,
            "recent_updates": core.read_recent_updates(root),
            "next_theme_numbers": {
                category: core.next_theme_number(root, category)
                for category in getattr(core, "THEME_CATEGORIES", ["general", "project", "research"])
            },
        }
    except Exception as exc:  # noqa: BLE001 - context gathering should be best-effort.
        return {"status": "error", "error": str(exc)}


def _scan_reuse(root: Path) -> dict[str, Any]:
    core = _load_ingest_core(root)
    try:
        return core.scan_reuse(root)
    except Exception as exc:  # noqa: BLE001 - optional context.
        return {"status": "error", "error": str(exc)}


def _build_ingest_output_templates(root: Path, ingest_type: str, target_theme: str = "") -> list[dict[str, str]]:
    templates: list[dict[str, str]] = []
    for path in DEFAULT_INGEST_OUTPUT_TEMPLATE_PATHS:
        name = PurePosixPath(path).name
        _append_output_template(templates, root, _theme_output_path(target_theme, name), f"templates/{name.replace('.md', '.template.md')}")
    if ingest_type == "requirement":
        _append_output_template(
            templates,
            root,
            _theme_output_path(target_theme, "requirement-analysis.md"),
            "templates/requirement-analysis.template.md",
        )
    return templates


def _append_output_template(
    templates: list[dict[str, str]],
    root: Path,
    output_path: str,
    schema_rel_path: str,
) -> None:
    content = _schema_text(root, schema_rel_path)
    if content.strip():
        templates.append({"path": output_path, "content": content})


def _extract_document(root: Path, path: Path) -> dict[str, Any] | None:
    module = _load_ingest_module(root, "kb_ingest_documents.py", "llm_wiki_agent_ingest_documents")
    try:
        payload = module.extract_document(path, MAX_SOURCE_CHARS, 12, 8)
    except Exception:
        return None
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > MAX_SOURCE_CHARS:
        payload["text"] = str(payload.get("text") or "")[:MAX_SOURCE_CHARS]
        payload["truncated_by_cli"] = True
    return payload


def _load_ingest_core(root: Path) -> Any:
    return _load_ingest_module(root, "kb_ingest_core.py", "llm_wiki_agent_ingest_core")


def _load_synthesize_module(root: Path) -> Any:
    scripts_dir = root / ".agents" / "skills" / "synthesize" / "scripts"
    filename = "kb_synthesize_helper.py"
    if not (scripts_dir / filename).exists():
        scripts_dir = Path(str(assets_root() / "skills" / "synthesize" / "scripts"))
    module_name = "llm_wiki_agent_synthesize_helper"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, scripts_dir / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load synthesize helper: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_ingest_module(root: Path, filename: str, module_name: str) -> Any:
    scripts_dir = root / ".agents" / "skills" / "ingest" / "scripts"
    if not (scripts_dir / filename).exists():
        scripts_dir = Path(str(assets_root() / "skills" / "ingest" / "scripts"))
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, scripts_dir / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load ingest helper: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _skill_text(root: Path, skill: str, rel_path: str) -> str:
    local_path = root / ".agents" / "skills" / skill / Path(rel_path)
    if local_path.is_file():
        return local_path.read_text(encoding="utf-8")
    path = assets_root() / "skills" / skill / rel_path
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _schema_text(root: Path, rel_path: str) -> str:
    local_path = root / "schema" / Path(rel_path)
    if local_path.is_file():
        return local_path.read_text(encoding="utf-8")
    path = assets_root() / "schema" / rel_path
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _clean_theme_path(value: str) -> str:
    text = (value or "").strip().replace("\\", "/").strip("/")
    if not text:
        return ""
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


def _theme_output_path(target_theme: str, output_name: str) -> str:
    name = PurePosixPath(output_name).name
    clean_theme = _clean_theme_path(target_theme)
    if clean_theme:
        return f"{clean_theme}/outputs/{name}"
    return f"outputs/{name}"


def _read_text_limited(path: Path, limit: int) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit]


def _walk_values(value: Any) -> list[Any]:
    found = [value]
    if isinstance(value, dict):
        for item in value.values():
            found.extend(_walk_values(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_values(item))
    return found
