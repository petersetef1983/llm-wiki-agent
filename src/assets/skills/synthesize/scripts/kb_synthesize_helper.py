#!/usr/bin/env python3
"""Deterministic helpers for demand-driven synthesis workflows.

This module is the stable CLI/facade entrypoint. Implementation lives in the
sibling kb_synthesize_* modules so copied skills and spec_from_file_location
callers can keep loading kb_synthesize_helper.py unchanged.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Copied skills and spec_from_file_location loads can leave same-name sibling
# modules cached from another skill directory. When __file__ is available, drop
# only those foreign siblings; packaged modules without __file__ are left alone.
for module_name in (
    "kb_synthesize_common",
    "kb_synthesize_context",
    "kb_synthesize_search",
    "kb_synthesize_assessment",
    "kb_synthesize_outputs",
):
    existing = sys.modules.get(module_name)
    existing_file = None
    existing_path = getattr(existing, "__file__", None) if existing is not None else None
    if existing_path:
        try:
            existing_file = Path(str(existing_path)).resolve().parent
        except OSError:
            existing_file = None
    if existing_file is not None and existing_file != SCRIPTS_DIR:
        sys.modules.pop(module_name, None)

import kb_synthesize_assessment as _assessment
import kb_synthesize_outputs as _outputs
import kb_synthesize_search as _search
from kb_synthesize_assessment import (
    PERMISSIVE_LICENSE_TERMS,
    REVIEW_LICENSE_TERMS,
    RISKY_LICENSE_TERMS,
    assess_reuse as _assess_reuse,
    check_license as _check_license,
    detect_promotion_candidates,
    is_promotion_candidate,
    license_status_for,
    license_term_matches,
    has_known_vulnerabilities,
    normalize_reuse_cost,
    normalize_reuse_level,
    reuse_risks,
    validation_task,
)
from kb_synthesize_common import (
    CONFIRM_WRITE,
    DEFAULT_MAX_CHARS,
    OUTPUT_NAMES,
    STOPWORDS,
    WIKILINK_RE,
    build_wikilink,
    clean_theme_path,
    extract_tokens,
    infer_theme_from_path,
    is_protected_sources_path,
    log_synthesize_operation,
    normalize_ref,
    read_text,
    safe_write_path,
    slugify,
    table_escape,
    title_from_markdown,
    unique_strings,
    validate_wikilinks,
)
from kb_synthesize_context import (
    build_candidate_inventory,
    collect_existing_pages,
    collect_historical_project_pages,
    collect_markdown_under,
    collect_open_source_evidence,
    collect_reuse_candidates,
    collect_synthesis_context,
    page_payload,
    parse_requirement_bullets,
    parse_requirement_table,
    parse_requirements,
    parse_reuse_candidate_rows,
    priority_for_text,
    requirement_analysis_path,
    split_markdown_table_row,
)
from kb_synthesize_outputs import (
    apply_generated_outputs,
    build_synthesis_pipeline as _build_synthesis_pipeline,
    generate_outputs as _generate_outputs,
    render_asset_match_brief,
    render_decision_brief,
    render_engineering_brief,
    render_implementation_guide,
    render_shared_asset,
    render_technical_assets_index,
    render_theme_asset_link,
)
from kb_synthesize_search import (
    BM25_UNAVAILABLE_MAX_ROOTS,
    BM25_UNAVAILABLE_LOCK,
    BM25_TIMEOUT_SECONDS,
    BM25_UNAVAILABLE_ROOTS,
    BM25_UNAVAILABLE_TTL_SECONDS,
    GRAPH_JSON_MAX_CHARS,
    SEARCH_MODES,
    SEARCH_SIGNAL_WEIGHTS,
    cache_bm25_unavailable,
    candidate_from_path,
    candidate_text,
    clear_bm25_unavailable_cache,
    enrich_candidate_with_frontmatter,
    extract_search_paths,
    frontmatter_candidates,
    graph_candidates,
    graph_edge_endpoints,
    graph_node_id,
    graph_node_label,
    graph_node_ref,
    graph_nodes_and_adjacency,
    graph_parts,
    infer_candidate_kind,
    is_bm25_unavailable_cached,
    load_query_index_module,
    merge_match,
    normalize_search_mode,
    requirement_query,
    run_bm25_search as _run_bm25_search,
    score_candidate,
    tool_path,
)

# Public mutable hook kept for existing tests/tools that monkeypatch helper.run_bm25_search.
run_bm25_search = _run_bm25_search


def match_assets(root: Path, target_theme: str, *, top: int = 20, max_chars: int = DEFAULT_MAX_CHARS, search_mode: str = "auto") -> dict[str, Any]:
    return _search.match_assets(
        root,
        target_theme,
        top=top,
        max_chars=max_chars,
        search_mode=search_mode,
        bm25_search_fn=lambda search_root, requirement: run_bm25_search(search_root, requirement, top=top),
    )


def check_license(root: Path, target_theme: str, *, top: int = 20, search_mode: str = "auto", match_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    match_payload = match_payload or match_assets(root, target_theme, top=top, search_mode=search_mode)
    return _check_license(root, target_theme, top=top, search_mode=search_mode, match_payload=match_payload)


def assess_reuse(root: Path, target_theme: str, *, top: int = 20, search_mode: str = "auto", match_payload: dict[str, Any] | None = None, license_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    match_payload = match_payload or match_assets(root, target_theme, top=top, search_mode=search_mode)
    license_payload = license_payload or check_license(root, target_theme, top=top, search_mode=search_mode, match_payload=match_payload)
    return _assess_reuse(root, target_theme, top=top, search_mode=search_mode, match_payload=match_payload, license_payload=license_payload)


def generate_outputs(root: Path, target_theme: str, *, top: int = 20, search_mode: str = "auto", reuse_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    reuse_payload = reuse_payload or assess_reuse(root, target_theme, top=top, search_mode=search_mode)
    return _generate_outputs(root, target_theme, top=top, search_mode=search_mode, reuse_payload=reuse_payload)


def build_synthesis_pipeline(root: Path, target_theme: str, *, top: int = 20, max_chars: int = DEFAULT_MAX_CHARS, search_mode: str = "auto") -> dict[str, Any]:
    root = root.resolve()
    matches = match_assets(root, target_theme, top=top, max_chars=max_chars, search_mode=search_mode)
    licenses = check_license(root, target_theme, top=top, search_mode=search_mode, match_payload=matches)
    reuse = assess_reuse(root, target_theme, top=top, search_mode=search_mode, match_payload=matches, license_payload=licenses)
    outputs = generate_outputs(root, target_theme, top=top, search_mode=search_mode, reuse_payload=reuse)
    return {
        "schema_version": "llm-wiki-synthesize-pipeline.v1",
        "root": str(root),
        "target_theme": clean_theme_path(target_theme),
        "requirements": parse_requirements(root, target_theme),
        "matches": matches,
        "license_checks": licenses,
        "reuse_assessment": reuse,
        "generated_outputs": outputs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic synthesis helpers.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in [
        ("context", "Read context for a target synthesis theme."),
        ("match-assets", "Match target requirements to historical/shared/open-source assets."),
        ("check-license", "Assign engineering license-risk labels to matched assets."),
        ("assess-reuse", "Assess reuse level, cost, risk, and validation tasks."),
        ("generate-outputs", "Generate target-theme output proposals and optional confirmed writes."),
    ]:
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--root", default=".")
        cmd.add_argument("--target-theme", required=True)
        cmd.add_argument("--top", type=int, default=20)
        cmd.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
        cmd.add_argument("--search-mode", choices=sorted(SEARCH_MODES), default="auto")
        cmd.add_argument("--format", choices=["json"], default="json")
        if name == "generate-outputs":
            cmd.add_argument("--confirm", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    if args.command == "context":
        payload = collect_synthesis_context(root, args.target_theme, max_chars=args.max_chars)
    elif args.command == "match-assets":
        payload = match_assets(root, args.target_theme, top=args.top, max_chars=args.max_chars, search_mode=args.search_mode)
    elif args.command == "check-license":
        payload = check_license(root, args.target_theme, top=args.top, search_mode=args.search_mode)
    elif args.command == "assess-reuse":
        payload = assess_reuse(root, args.target_theme, top=args.top, search_mode=args.search_mode)
    elif args.command == "generate-outputs":
        payload = generate_outputs(root, args.target_theme, top=args.top, search_mode=args.search_mode)
        if args.confirm:
            payload["apply"] = apply_generated_outputs(root.resolve(), payload, confirm=args.confirm)
    else:
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
