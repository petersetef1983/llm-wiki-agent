#!/usr/bin/env python3
"""Multi-route asset search for deterministic synthesis."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from kb_synthesize_common import DEFAULT_MAX_CHARS, clean_theme_path, extract_tokens, infer_theme_from_path, read_text, title_from_markdown, unique_strings
from kb_synthesize_context import build_candidate_inventory, collect_synthesis_context, parse_requirements

BM25_TIMEOUT_SECONDS = 5
BM25_UNAVAILABLE_TTL_SECONDS = 300
BM25_UNAVAILABLE_MAX_ROOTS = 100
GRAPH_JSON_MAX_CHARS = 500_000
SEARCH_MODES = {"auto", "keyword", "multi"}
SEARCH_SIGNAL_WEIGHTS = {
    "keyword": 0.35,
    "bm25": 0.30,
    "frontmatter": 0.20,
    "graph": 0.15,
}
BM25_UNAVAILABLE_ROOTS: dict[str, float] = {}
BM25_UNAVAILABLE_LOCK = threading.Lock()


def candidate_text(candidate: dict[str, Any]) -> str:
    parts = []
    for key in ("title", "path", "content", "asset", "module", "repo", "description"):
        value = candidate.get(key)
        if isinstance(value, dict):
            parts.extend(str(item) for item in value.values())
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value:
            parts.append(str(value))
    return "\n".join(parts)


def score_candidate(requirement: dict[str, Any], candidate: dict[str, Any]) -> tuple[float, list[str]]:
    req_text = " ".join(str(requirement.get(key, "")) for key in ("id", "type", "text", "related"))
    cand_text = candidate_text(candidate)
    req_tokens = extract_tokens(req_text)
    cand_tokens = extract_tokens(cand_text)
    overlap = sorted(req_tokens & cand_tokens)
    score = float(len(overlap)) * 0.25
    lowered_candidate = cand_text.lower()
    lowered_requirement = str(requirement.get("text", "")).lower()
    for token in req_tokens:
        if len(token) >= 4 and token in lowered_candidate:
            score += 0.1
    if lowered_requirement and lowered_requirement[:24] in lowered_candidate:
        score += 0.35
    if candidate.get("kind") in {"shared_asset", "reuse_candidate"}:
        score += 0.1
    reasons = [f"keyword_overlap={', '.join(overlap[:8])}"] if overlap else ["low_keyword_overlap"]
    reasons.append(f"candidate_kind={candidate.get('kind')}")
    return min(score, 1.0), reasons


def normalize_search_mode(value: str) -> str:
    mode = (value or "auto").strip().lower()
    return mode if mode in SEARCH_MODES else "auto"


def tool_path(root: Path, name: str) -> Path:
    root_tool = root / "tools" / name
    if root_tool.exists():
        return root_tool
    bundled = Path(__file__).resolve().parents[3] / "tools" / name
    return bundled


def requirement_query(requirement: dict[str, Any]) -> str:
    return " ".join(
        str(requirement.get(key) or "")
        for key in ("id", "type", "text", "related")
        if requirement.get(key)
    ).strip()


def candidate_from_path(root: Path, rel_path: str, candidate_by_path: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    clean = rel_path.strip().replace("\\", "/").lstrip("./")
    if "#" in clean:
        clean = clean.split("#", 1)[0]
    if clean in candidate_by_path:
        return dict(candidate_by_path[clean])
    if clean.removesuffix(".md") in candidate_by_path:
        return dict(candidate_by_path[clean.removesuffix(".md")])
    if not clean or clean.startswith("."):
        return None
    path = root / clean
    if not path.is_file():
        return None
    if clean.endswith(".md"):
        content = read_text(path, DEFAULT_MAX_CHARS)
        return {
            "kind": infer_candidate_kind(clean),
            "path": clean,
            "title": title_from_markdown(content, path),
            "content": content,
            "source_theme": infer_theme_from_path(clean),
        }
    if clean.endswith(".json") and "/outputs/document-intake/" in f"/{clean}/":
        return {
            "kind": "evidence_artifact",
            "path": clean,
            "title": PurePosixPath(clean).stem,
            "content": read_text(path, DEFAULT_MAX_CHARS),
            "source_theme": infer_theme_from_path(clean),
        }
    return None


def infer_candidate_kind(path: str) -> str:
    if path.startswith("shared/assets/"):
        return "shared_asset"
    if path.startswith("shared/patterns/"):
        return "shared_pattern"
    if "/outputs/reuse-candidates.md" in path:
        return "reuse_candidate_file"
    if path.startswith("themes/project/"):
        return "historical_project_page"
    return "wiki_page"


def merge_match(
    merged: dict[tuple[str, str], dict[str, Any]],
    requirement: dict[str, Any],
    candidate: dict[str, Any],
    *,
    route: str,
    signal_score: float,
    reasons: list[str],
    evidence_paths: list[str] | None = None,
) -> None:
    candidate_ref = str(candidate.get("path") or candidate.get("candidate_ref") or "")
    candidate_title = str(candidate.get("title") or candidate.get("candidate_title") or PurePosixPath(candidate_ref).stem or "candidate")
    key = (str(requirement.get("id") or ""), candidate_ref or candidate_title)
    existing = merged.get(key)
    if existing is None:
        existing = {
            "requirement_id": requirement.get("id"),
            "requirement": requirement.get("text"),
            "candidate_kind": candidate.get("kind"),
            "candidate_ref": candidate_ref,
            "candidate_title": candidate_title,
            "source_theme": candidate.get("source_theme") or infer_theme_from_path(candidate_ref),
            "match_score": 0.0,
            "match_reason": [],
            "reuse_level_hint": candidate.get("reuse_level"),
            "reuse_cost_hint": candidate.get("reuse_cost"),
            "license_type": candidate.get("license_type") or (candidate.get("license_signals") or {}).get("primary_license"),
            "license_signals": candidate.get("license_signals") or {},
            "community_health": candidate.get("community_health") or {},
            "known_vulnerabilities": candidate.get("known_vulnerabilities") or [],
            "evidence_paths": [],
            "search_signals": {},
        }
        merged[key] = existing
    weighted = SEARCH_SIGNAL_WEIGHTS.get(route, 0.1) * max(0.0, min(float(signal_score), 1.0))
    existing["match_score"] = min(1.0, float(existing.get("match_score") or 0.0) + weighted)
    existing["match_reason"] = unique_strings([*existing.get("match_reason", []), *reasons, f"route={route}"])
    evidence = unique_strings([*(existing.get("evidence_paths") or []), *(evidence_paths or []), candidate_ref])
    existing["evidence_paths"] = [item for item in evidence if item]
    existing["search_signals"][route] = {
        "score": round(max(0.0, min(float(signal_score), 1.0)), 3),
        "evidence_paths": [item for item in unique_strings(evidence_paths or [candidate_ref]) if item],
        "reasons": reasons,
    }
    for field in ("reuse_level_hint", "reuse_cost_hint", "license_type"):
        if not existing.get(field) and candidate.get(field.replace("_hint", "")):
            existing[field] = candidate.get(field.replace("_hint", ""))
    if not existing.get("license_signals") and candidate.get("license_signals"):
        existing["license_signals"] = candidate.get("license_signals")
    if not existing.get("community_health") and candidate.get("community_health"):
        existing["community_health"] = candidate.get("community_health")
    if not existing.get("known_vulnerabilities") and candidate.get("known_vulnerabilities"):
        existing["known_vulnerabilities"] = candidate.get("known_vulnerabilities")


def prune_bm25_unavailable_locked(now: float) -> None:
    for key, timestamp in list(BM25_UNAVAILABLE_ROOTS.items()):
        if now - timestamp > BM25_UNAVAILABLE_TTL_SECONDS:
            BM25_UNAVAILABLE_ROOTS.pop(key, None)
    while len(BM25_UNAVAILABLE_ROOTS) >= BM25_UNAVAILABLE_MAX_ROOTS:
        oldest = min(BM25_UNAVAILABLE_ROOTS, key=BM25_UNAVAILABLE_ROOTS.get)
        BM25_UNAVAILABLE_ROOTS.pop(oldest, None)


def clear_bm25_unavailable_cache() -> None:
    with BM25_UNAVAILABLE_LOCK:
        BM25_UNAVAILABLE_ROOTS.clear()


def is_bm25_unavailable_cached(root_key: str) -> bool:
    with BM25_UNAVAILABLE_LOCK:
        timestamp = BM25_UNAVAILABLE_ROOTS.get(root_key)
        if timestamp is None:
            return False
        if time.monotonic() - timestamp > BM25_UNAVAILABLE_TTL_SECONDS:
            BM25_UNAVAILABLE_ROOTS.pop(root_key, None)
            return False
        return True


def cache_bm25_unavailable(root_key: str) -> None:
    now = time.monotonic()
    with BM25_UNAVAILABLE_LOCK:
        prune_bm25_unavailable_locked(now)
        BM25_UNAVAILABLE_ROOTS[root_key] = now


def run_bm25_search(root: Path, requirement: dict[str, Any], *, top: int) -> dict[str, Any]:
    root_key = str(root.resolve())
    if is_bm25_unavailable_cached(root_key):
        return {"status": "unavailable", "error": "bm25 route previously unavailable in this process; retry after cache ttl", "paths": []}
    script = tool_path(root, "kb_search_bridge.py")
    if not script.exists():
        cache_bm25_unavailable(root_key)
        return {"status": "unavailable", "error": f"kb_search_bridge.py not found: {script}", "paths": []}
    query = requirement_query(requirement)
    if not query:
        return {"status": "skipped", "error": "empty requirement query", "paths": []}
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--root",
                str(root),
                "--format",
                "json",
                "search",
                "--query",
                query,
                "--mode",
                "auto",
                "--top",
                str(max(1, top)),
                "--allow-fallback",
                "--json-output",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=BM25_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        cache_bm25_unavailable(root_key)
        return {"status": "unavailable", "error": str(exc), "paths": []}
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {"stdout": proc.stdout.strip()}
    paths = extract_search_paths(payload)
    if proc.returncode != 0 and not paths:
        cache_bm25_unavailable(root_key)
    return {
        "status": "available" if proc.returncode == 0 else "unavailable",
        "exit_code": proc.returncode,
        "error": proc.stderr.strip() or payload.get("message") or payload.get("error"),
        "paths": paths,
        "raw": payload,
    }


def extract_search_paths(payload: Any) -> list[str]:
    paths: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                lowered_key = str(key).lower()
                if lowered_key in {"path", "file", "filename", "source", "url", "ref"} and isinstance(item, str):
                    add_path(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            for match in re.findall(r"(?<![\w./-])((?:themes|shared|index)/[^\s:,'\")\]]+?\.md)", value):
                add_path(match)

    def add_path(value: str) -> None:
        clean = value.strip().replace("\\", "/").strip("'\"")
        if clean.startswith("llm-wiki://page/"):
            clean = clean.removeprefix("llm-wiki://page/")
        if "#" in clean:
            clean = clean.split("#", 1)[0]
        if clean.endswith(".md") and not clean.startswith("."):
            paths.append(clean)

    walk(payload)
    return unique_strings(paths)


def load_query_index_module(root: Path) -> Any:
    script = tool_path(root, "kb_query_index.py")
    if not script.exists():
        raise FileNotFoundError(f"kb_query_index.py not found: {script}")
    module_name = f"llm_wiki_synthesize_query_index_{abs(hash(str(script.resolve())))}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load query index helper: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def frontmatter_candidates(root: Path, requirement: dict[str, Any], *, top: int) -> dict[str, Any]:
    try:
        module = load_query_index_module(root)
        entries = module.build_index(root).get("entries", [])
    except Exception as exc:  # noqa: BLE001 - search route is best-effort.
        return {"status": "unavailable", "error": str(exc), "items": []}
    items = []
    req_tokens = extract_tokens(requirement_query(requirement))
    for entry in entries:
        path = str(entry.get("path") or "")
        if not path or path.startswith("schema/") or "/sources/" in f"/{path}/":
            continue
        frontmatter = entry.get("frontmatter") or {}
        node_type = str(entry.get("node_type") or frontmatter.get("node_type") or "").lower()
        if path.startswith("shared/assets/"):
            base = 0.45
        elif path.startswith("shared/patterns/"):
            base = 0.40
        elif node_type in {"asset", "pattern", "module", "method", "tool"}:
            base = 0.35
        elif path.startswith("themes/project/"):
            base = 0.15
        else:
            continue
        haystack = json.dumps({"title": entry.get("title"), "path": path, "frontmatter": frontmatter}, ensure_ascii=False)
        overlap = sorted(req_tokens & extract_tokens(haystack))
        if not overlap and base < 0.35:
            continue
        score = min(1.0, base + 0.12 * len(overlap))
        items.append(
            {
                "path": path,
                "title": entry.get("title") or PurePosixPath(path).stem,
                "score": score,
                "frontmatter": frontmatter,
                "reasons": [f"frontmatter_node_type={node_type or 'unknown'}", f"frontmatter_overlap={', '.join(overlap[:8]) or 'none'}"],
            }
        )
    items.sort(key=lambda item: (-float(item["score"]), str(item["path"])))
    return {"status": "available", "entry_count": len(entries), "items": items[: max(1, top)]}


def enrich_candidate_with_frontmatter(candidate: dict[str, Any], frontmatter: dict[str, Any]) -> dict[str, Any]:
    return {
        **candidate,
        "reuse_level": candidate.get("reuse_level") or frontmatter.get("reuse_level"),
        "reuse_cost": candidate.get("reuse_cost") or frontmatter.get("reuse_cost"),
        "license_type": candidate.get("license_type") or frontmatter.get("license") or frontmatter.get("license_type") or frontmatter.get("license_compatibility"),
    }


def graph_candidates(root: Path, requirement: dict[str, Any], target_theme: str, *, top: int) -> dict[str, Any]:
    graph_paths = [
        path
        for path in sorted(root.glob("themes/*/*/outputs/document-intake/graphify/graph.json"), key=lambda item: item.as_posix().lower())
        if not path.relative_to(root).as_posix().startswith(f"{target_theme}/")
    ]
    if not graph_paths:
        return {"status": "unavailable", "error": "no graphify graph artifacts found", "items": []}
    req_tokens = extract_tokens(requirement_query(requirement))
    items = []
    for graph_path in graph_paths:
        try:
            graph = json.loads(read_text(graph_path, max_chars=GRAPH_JSON_MAX_CHARS))
        except (OSError, json.JSONDecodeError) as exc:
            items.append({"status": "error", "path": graph_path.relative_to(root).as_posix(), "error": str(exc)})
            continue
        labels, adjacency = graph_nodes_and_adjacency(graph)
        for key, label in labels.items():
            node_text = f"{key} {label} " + " ".join(str(item.get("label", "")) for item in adjacency.get(key, [])[:10])
            overlap = sorted(req_tokens & extract_tokens(node_text))
            if not overlap:
                continue
            rel_graph = graph_path.relative_to(root).as_posix()
            theme = "/".join(graph_path.relative_to(root).parts[:3])
            node_ref = graph_node_ref(root, theme, key, label) or rel_graph
            items.append(
                {
                    "path": node_ref,
                    "title": label,
                    "score": min(1.0, 0.25 + 0.15 * len(overlap)),
                    "graph_path": rel_graph,
                    "source_theme": theme,
                    "reasons": [f"graph_overlap={', '.join(overlap[:8])}", f"graph_node={key}"],
                }
            )
    good_items = [item for item in items if item.get("score") is not None]
    good_items.sort(key=lambda item: (-float(item["score"]), str(item["path"])))
    errors = [item for item in items if item.get("status") == "error"]
    status = "available" if good_items or len(errors) < len(graph_paths) else "unavailable"
    error = "all graphify graph artifacts failed to parse" if status == "unavailable" and errors else None
    return {"status": status, "error": error, "graph_count": len(graph_paths), "items": good_items[: max(1, top)], "errors": errors}


def graph_parts(graph: Any) -> tuple[list[Any], list[Any]]:
    if not isinstance(graph, dict):
        return [], []
    nodes = graph.get("nodes") or graph.get("vertices") or []
    edges = graph.get("edges") or graph.get("links") or []
    if isinstance(nodes, dict):
        nodes = [{"id": key, **(value if isinstance(value, dict) else {"value": value})} for key, value in nodes.items()]
    if isinstance(edges, dict):
        edges = list(edges.values())
    return list(nodes) if isinstance(nodes, list) else [], list(edges) if isinstance(edges, list) else []


def graph_node_id(node: Any, index: int) -> str:
    if isinstance(node, dict):
        for key in ("id", "node_id", "key", "name", "label", "path"):
            value = node.get(key)
            if value is not None and str(value).strip():
                return str(value)
    return str(node if not isinstance(node, dict) else index)


def graph_node_label(node: Any, node_key: str) -> str:
    if isinstance(node, dict):
        for key in ("label", "name", "title", "path", "id", "node_id"):
            value = node.get(key)
            if value is not None and str(value).strip():
                return str(value)
    return str(node_key)


def graph_edge_endpoints(edge: Any) -> tuple[str | None, str | None, str | None]:
    if isinstance(edge, dict):
        source = edge.get("source") or edge.get("from") or edge.get("start") or edge.get("u")
        target = edge.get("target") or edge.get("to") or edge.get("end") or edge.get("v")
        relation = edge.get("type") or edge.get("relation") or edge.get("label") or edge.get("kind")
        return str(source) if source is not None else None, str(target) if target is not None else None, str(relation) if relation is not None else None
    if isinstance(edge, (list, tuple)) and len(edge) >= 2:
        return str(edge[0]), str(edge[1]), str(edge[2]) if len(edge) > 2 else None
    return None, None, None


def graph_nodes_and_adjacency(graph: Any) -> tuple[dict[str, str], dict[str, list[dict[str, str]]]]:
    nodes, edges = graph_parts(graph)
    labels: dict[str, str] = {}
    for idx, node in enumerate(nodes):
        key = graph_node_id(node, idx)
        labels[key] = graph_node_label(node, key)
    adjacency: dict[str, list[dict[str, str]]] = {key: [] for key in labels}
    for edge in edges:
        source, target, relation = graph_edge_endpoints(edge)
        if not source or not target:
            continue
        adjacency.setdefault(source, []).append({"id": target, "label": labels.get(target, target), "relation": relation or "related"})
        adjacency.setdefault(target, []).append({"id": source, "label": labels.get(source, source), "relation": relation or "related"})
        labels.setdefault(source, source)
        labels.setdefault(target, target)
    return labels, adjacency


def graph_node_ref(root: Path, theme: str, key: str, label: str) -> str | None:
    for value in (key, label):
        clean = str(value).strip().replace("\\", "/").lstrip("./")
        if clean.endswith(".md") and (root / clean).exists():
            return clean
        if clean.startswith("wiki/") and (root / theme / clean).exists():
            return f"{theme}/{clean}"
    return None


def match_assets(
    root: Path,
    target_theme: str,
    *,
    top: int = 20,
    max_chars: int = DEFAULT_MAX_CHARS,
    search_mode: str = "auto",
    bm25_search_fn: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    context = collect_synthesis_context(root, target_theme, max_chars=max_chars)
    requirements = parse_requirements(root, target_theme)
    candidates = build_candidate_inventory(context)
    candidate_by_path = {str(candidate.get("path")): candidate for candidate in candidates if candidate.get("path")}
    mode = normalize_search_mode(search_mode)
    run_multi = mode in {"auto", "multi"}
    diagnostics: dict[str, Any] = {
        "requested_mode": search_mode,
        "resolved_mode": "multi" if run_multi else "keyword",
        "routes": {
            "keyword": {"status": "available", "candidate_count": len(candidates)},
            "bm25": {"status": "skipped" if not run_multi else "pending"},
            "frontmatter": {"status": "skipped" if not run_multi else "pending"},
            "graph": {"status": "skipped" if not run_multi else "pending"},
        },
    }
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    search_fn = bm25_search_fn or (lambda search_root, requirement: run_bm25_search(search_root, requirement, top=top))
    if not requirements:
        if run_multi:
            for route in ("bm25", "frontmatter", "graph"):
                diagnostics["routes"][route] = {"status": "skipped", "error": "no requirements found", "result_count": 0}
        return {
            "schema_version": "llm-wiki-synthesize-matches.v1",
            "root": str(root.resolve()),
            "target_theme": clean_theme_path(target_theme),
            "search_mode": mode,
            "search_diagnostics": diagnostics | {"degraded_to_keyword": False},
            "requirement_count": 0,
            "candidate_count": len(candidates),
            "matches": [],
        }
    for requirement in requirements:
        for candidate in candidates:
            score, reasons = score_candidate(requirement, candidate)
            if score <= 0 and candidate.get("kind") != "shared_asset":
                continue
            if score < 0.15:
                continue
            merge_match(merged, requirement, candidate, route="keyword", signal_score=score, reasons=reasons, evidence_paths=[candidate.get("path", "")])

        if not run_multi:
            continue

        bm25 = search_fn(root.resolve(), requirement)
        diagnostics["routes"]["bm25"] = {
            "status": bm25.get("status"),
            "exit_code": bm25.get("exit_code"),
            "error": bm25.get("error"),
            "result_count": len(bm25.get("paths") or []),
        }
        for rank, rel_path in enumerate(bm25.get("paths") or []):
            candidate = candidate_from_path(root, rel_path, candidate_by_path)
            if not candidate:
                continue
            signal_score = max(0.1, 1.0 - (rank / max(top, 1)))
            merge_match(merged, requirement, candidate, route="bm25", signal_score=signal_score, reasons=[f"bm25_rank={rank + 1}"], evidence_paths=[rel_path])

        frontmatter = frontmatter_candidates(root.resolve(), requirement, top=top)
        diagnostics["routes"]["frontmatter"] = {
            "status": frontmatter.get("status"),
            "error": frontmatter.get("error"),
            "entry_count": frontmatter.get("entry_count"),
            "result_count": len(frontmatter.get("items") or []),
        }
        for item in frontmatter.get("items") or []:
            candidate = candidate_from_path(root, str(item.get("path") or ""), candidate_by_path)
            if not candidate:
                continue
            fm = item.get("frontmatter") or {}
            enriched_candidate = enrich_candidate_with_frontmatter(candidate, fm)
            merge_match(
                merged,
                requirement,
                enriched_candidate,
                route="frontmatter",
                signal_score=float(item.get("score") or 0.0),
                reasons=list(item.get("reasons") or ["frontmatter_match"]),
                evidence_paths=[str(item.get("path") or "")],
            )

        graph = graph_candidates(root.resolve(), requirement, clean_theme_path(target_theme), top=top)
        diagnostics["routes"]["graph"] = {
            "status": graph.get("status"),
            "error": graph.get("error"),
            "graph_count": graph.get("graph_count"),
            "result_count": len(graph.get("items") or []),
            "errors": graph.get("errors") or [],
        }
        for item in graph.get("items") or []:
            candidate = candidate_from_path(root, str(item.get("path") or ""), candidate_by_path) or {
                "kind": "graph_hint",
                "path": item.get("path"),
                "title": item.get("title"),
                "content": json.dumps(item, ensure_ascii=False),
                "source_theme": item.get("source_theme"),
            }
            merge_match(
                merged,
                requirement,
                candidate,
                route="graph",
                signal_score=float(item.get("score") or 0.0),
                reasons=list(item.get("reasons") or ["graph_match"]),
                evidence_paths=[str(item.get("graph_path") or item.get("path") or "")],
            )

    matches = sorted(merged.values(), key=lambda item: (-float(item.get("match_score") or 0.0), str(item.get("candidate_ref") or "")))
    for item in matches:
        item["match_score"] = round(float(item.get("match_score") or 0.0), 2)
    if run_multi and not any(
        diagnostics["routes"][route].get("status") == "available" and diagnostics["routes"][route].get("result_count", 0)
        for route in ("bm25", "frontmatter", "graph")
    ):
        diagnostics["degraded_to_keyword"] = True
    else:
        diagnostics["degraded_to_keyword"] = False
    return {
        "schema_version": "llm-wiki-synthesize-matches.v1",
        "root": str(root.resolve()),
        "target_theme": clean_theme_path(target_theme),
        "search_mode": mode,
        "search_diagnostics": diagnostics,
        "requirement_count": len(requirements),
        "candidate_count": len(candidates),
        "matches": matches[: max(top, 1) * max(len(requirements), 1)],
    }
