#!/usr/bin/env python3
"""Bridge Graphify outputs into the LLM Wiki evidence layer."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GRAPHIFY_DIR_REL = Path("outputs/document-intake/graphify")
THEME_GRAPHIFY_REL = Path("outputs/document-intake/graphify")
GLOBAL_INDEX_NAME = "global-graph-index.json"
QUERY_DIR_NAME = "queries"
CONFIDENCE_VALUES = {"confirmed", "inferred", "tentative"}
SENSITIVITY_VALUES = {"public", "internal", "confidential", "restricted", "unknown"}
RETENTION_VALUES = {"keep", "review", "expire"}


def parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=".", help="Knowledge-base root. Defaults to current directory.")
    common.add_argument("--format", choices=["text", "json"], default="text")

    parser = argparse.ArgumentParser(description="Run Graphify and normalize its outputs for LLM Wiki ingest.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", parents=[common], help="Report Graphify CLI and local graph artifact status.")

    extract = sub.add_parser("extract", parents=[common], help="Run Graphify over a repo/folder and emit evidence.v1.")
    extract.add_argument("--repo", required=True, help="Git URL or local repository/folder path.")
    extract.add_argument("--theme", required=True, help="Target theme directory relative to root.")
    extract.add_argument("--backend", default="ollama", help="Graphify backend. Default: ollama.")
    extract.add_argument("--ref", help="Optional git ref to checkout after clone.")
    extract.add_argument("--source-id", help="Stable source id. Defaults to graphify-<theme-name>.")
    extract.add_argument("--sensitivity", choices=sorted(SENSITIVITY_VALUES), default="internal")
    extract.add_argument("--retention", choices=sorted(RETENTION_VALUES), default="review")
    extract.add_argument("--confidence", choices=sorted(CONFIDENCE_VALUES), default="inferred")
    extract.add_argument("--graphify-output", help="Use an existing graphify-out directory instead of running Graphify.")
    extract.add_argument("--keep-temp", action="store_true", help="Keep temporary git clone for debugging.")
    extract.add_argument("--include-html", action="store_true", help="Copy graph.html into runtime/ for local review.")
    extract.add_argument("--include-cache", action="store_true", help="Copy graphify cache into runtime/ for local review.")
    extract.add_argument("--extra-arg", action="append", default=[], help="Extra argument passed to Graphify. Repeatable.")

    update = sub.add_parser("update", parents=[common], help="Re-run extract using the last Graphify evidence source URI.")
    update.add_argument("--theme", required=True, help="Target theme directory relative to root.")
    update.add_argument("--backend", help="Override backend from prior evidence.")
    update.add_argument("--extra-arg", action="append", default=[])

    global_add = sub.add_parser("global-add", parents=[common], help="Register a theme graph for cross-project reports.")
    global_add.add_argument("--theme", required=True, help="Theme directory relative to root.")
    global_add.add_argument("--tag", required=True, help="Stable project tag for the graph.")

    sub.add_parser("global-list", parents=[common], help="List registered project graphs.")
    sub.add_parser("global-report", parents=[common], help="Generate cross-project structural graph report.")

    query = sub.add_parser("query", parents=[common], help="Search a theme graph for routing hints.")
    query.add_argument("--theme", required=True)
    query.add_argument("--question", required=True)
    query.add_argument("--top", type=int, default=10)

    path_cmd = sub.add_parser("path", parents=[common], help="Find a simple path between two graph nodes.")
    path_cmd.add_argument("--theme", required=True)
    path_cmd.add_argument("--source", required=True)
    path_cmd.add_argument("--target", required=True)
    path_cmd.add_argument("--max-depth", type=int, default=8)

    explain = sub.add_parser("explain", parents=[common], help="Explain a node and its immediate graph neighborhood.")
    explain.add_argument("--theme", required=True)
    explain.add_argument("--concept", required=True)
    explain.add_argument("--top", type=int, default=20)

    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def resolve_under_root(root: Path, rel: str | Path) -> Path:
    path = Path(rel)
    if path.is_absolute():
        return path
    return root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def theme_dir(root: Path, theme: str) -> Path:
    path = resolve_under_root(root, theme)
    if not path.is_dir():
        raise SystemExit(f"Theme directory not found: {path}")
    return path


def theme_output_dir(theme_path: Path) -> Path:
    return theme_path / THEME_GRAPHIFY_REL


def default_source_id(theme_path: Path) -> str:
    return "graphify-" + re.sub(r"[^a-z0-9]+", "-", theme_path.name.lower()).strip("-")


def is_git_url(value: str) -> bool:
    return bool(re.match(r"^(https?|ssh|git)://", value) or re.match(r"^[^@\s]+@[^:\s]+:.+", value))


def run_command(args: list[str], cwd: Path, timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise SystemExit(f"Command not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"Command timed out after {timeout}s: {' '.join(args)}") from exc


def git_commit(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    completed = run_command(["git", "rev-parse", "HEAD"], cwd=path, timeout=30)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def clone_or_resolve_repo(repo: str, ref: str | None, temp_root: Path) -> tuple[Path, str | None, list[str]]:
    warnings: list[str] = []
    if is_git_url(repo):
        target = temp_root / "repo"
        completed = run_command(["git", "clone", "--depth", "1", repo, str(target)], cwd=temp_root, timeout=1800)
        if completed.returncode != 0:
            raise SystemExit(f"git clone failed: {completed.stderr.strip() or completed.stdout.strip()}")
        if ref:
            checkout = run_command(["git", "checkout", ref], cwd=target, timeout=120)
            if checkout.returncode != 0:
                raise SystemExit(f"git checkout {ref} failed: {checkout.stderr.strip() or checkout.stdout.strip()}")
        return target, git_commit(target), warnings

    path = Path(repo)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.exists():
        raise SystemExit(f"Repo/folder path not found: {path}")
    if ref:
        warnings.append("ref was provided for a local path; bridge records it but does not checkout local worktrees")
    return path, git_commit(path), warnings


def graphify_version() -> dict[str, Any]:
    exe = shutil.which("graphify")
    if not exe:
        return {"available": False, "path": None, "version": None, "error": "graphify CLI not found"}
    completed = run_command(["graphify", "--version"], cwd=Path.cwd(), timeout=30)
    version = (completed.stdout or completed.stderr).strip()
    return {
        "available": completed.returncode == 0,
        "path": exe,
        "version": version or None,
        "error": None if completed.returncode == 0 else (completed.stderr.strip() or completed.stdout.strip()),
    }


def run_graphify(source_dir: Path, backend: str, work_dir: Path, extra_args: list[str]) -> tuple[Path, list[dict[str, Any]]]:
    attempts = [
        ["graphify", "extract", str(source_dir), "--backend", backend, *extra_args],
        ["graphify", str(source_dir), "--backend", backend, "--no-viz", *extra_args],
        ["graphify", str(source_dir), "--backend", backend, *extra_args],
    ]
    results: list[dict[str, Any]] = []
    for command in attempts:
        completed = run_command(command, cwd=work_dir, timeout=7200)
        results.append(
            {
                "args": command,
                "exit_code": completed.returncode,
                "stdout": completed.stdout.strip()[-4000:],
                "stderr": completed.stderr.strip()[-4000:],
            }
        )
        if completed.returncode == 0:
            output_dir = find_graphify_output(work_dir, source_dir)
            if output_dir:
                return output_dir, results
    last = results[-1] if results else {}
    raise SystemExit(f"Graphify failed or did not produce graphify-out/graph.json: {last.get('stderr') or last.get('stdout')}")


def find_graphify_output(work_dir: Path, source_dir: Path) -> Path | None:
    candidates = [work_dir / "graphify-out", source_dir / "graphify-out"]
    for candidate in candidates:
        if (candidate / "graph.json").exists():
            return candidate
    for candidate in sorted(work_dir.rglob("graphify-out")):
        if (candidate / "graph.json").exists():
            return candidate
    return None


def copy_required_outputs(source_output: Path, dest: Path, include_html: bool, include_cache: bool) -> dict[str, str]:
    graph_path = source_output / "graph.json"
    report_path = source_output / "GRAPH_REPORT.md"
    if not graph_path.exists():
        raise SystemExit(f"Graphify output missing graph.json: {graph_path}")
    if not report_path.exists():
        raise SystemExit(f"Graphify output missing GRAPH_REPORT.md: {report_path}")

    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(graph_path, dest / "graph.json")
    shutil.copy2(report_path, dest / "GRAPH_REPORT.md")
    artifacts = {
        "graph_json": (dest / "graph.json").as_posix(),
        "report_markdown": (dest / "GRAPH_REPORT.md").as_posix(),
    }
    runtime = dest / "runtime"
    html = source_output / "graph.html"
    if include_html and html.exists():
        runtime.mkdir(parents=True, exist_ok=True)
        shutil.copy2(html, runtime / "graph.html")
        artifacts["runtime_graph_html"] = (runtime / "graph.html").as_posix()
    cache = source_output / "cache"
    if include_cache and cache.is_dir():
        runtime.mkdir(parents=True, exist_ok=True)
        target_cache = runtime / "graphify-cache"
        if target_cache.exists():
            shutil.rmtree(target_cache)
        shutil.copytree(cache, target_cache)
        artifacts["runtime_cache"] = target_cache.as_posix()
    return artifacts


def node_id(node: Any, index: int) -> str:
    if isinstance(node, dict):
        for key in ["id", "node_id", "key", "name", "label", "path"]:
            value = node.get(key)
            if value is not None and str(value).strip():
                return str(value)
    return str(node if not isinstance(node, dict) else index)


def node_label(node: Any, node_key: str) -> str:
    if isinstance(node, dict):
        for key in ["label", "name", "title", "path", "id", "node_id"]:
            value = node.get(key)
            if value is not None and str(value).strip():
                return str(value)
    return str(node_key)


def edge_endpoints(edge: Any) -> tuple[str | None, str | None, str | None]:
    if isinstance(edge, dict):
        source = edge.get("source") or edge.get("from") or edge.get("start") or edge.get("u")
        target = edge.get("target") or edge.get("to") or edge.get("end") or edge.get("v")
        relation = edge.get("type") or edge.get("relation") or edge.get("label") or edge.get("kind")
        return str(source) if source is not None else None, str(target) if target is not None else None, str(relation) if relation is not None else None
    if isinstance(edge, (list, tuple)) and len(edge) >= 2:
        return str(edge[0]), str(edge[1]), str(edge[2]) if len(edge) > 2 else None
    return None, None, None


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


def graph_summary(graph: Any) -> dict[str, Any]:
    nodes, edges = graph_parts(graph)
    id_to_label: dict[str, str] = {}
    communities = Counter()
    types = Counter()
    for idx, node in enumerate(nodes):
        key = node_id(node, idx)
        id_to_label[key] = node_label(node, key)
        if isinstance(node, dict):
            if node.get("community") is not None:
                communities[str(node.get("community"))] += 1
            node_type = node.get("type") or node.get("kind")
            if node_type is not None:
                types[str(node_type)] += 1
    degree = Counter()
    relations = Counter()
    for edge in edges:
        source, target, relation = edge_endpoints(edge)
        if source:
            degree[source] += 1
        if target:
            degree[target] += 1
        if relation:
            relations[relation] += 1
    top_nodes = [
        {"id": key, "label": id_to_label.get(key, key), "degree": count}
        for key, count in degree.most_common(20)
    ]
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_types": dict(types.most_common(20)),
        "relation_types": dict(relations.most_common(20)),
        "community_count": len(communities),
        "top_communities": [{"id": key, "size": value} for key, value in communities.most_common(20)],
        "god_nodes": top_nodes[:10],
        "top_nodes": top_nodes,
    }


def write_anchor(path: Path, payload: dict[str, Any], artifacts: dict[str, str]) -> None:
    content = [
        "# Graphify Source Anchor",
        "",
        "This source anchor records a Graphify structural graph evidence capture.",
        "",
        f"- source_id: `{payload['source_id']}`",
        f"- source_uri: `{payload['source_uri']}`",
        f"- captured_at: `{payload['captured_at']}`",
        f"- provider: `graphify`",
        f"- analyzed_commit: `{payload['content'].get('captured_commit') or 'unknown'}`",
        f"- backend: `{payload['content'].get('backend') or 'unknown'}`",
        f"- sensitivity: `{payload['sensitivity']}`",
        f"- retention: `{payload['retention']}`",
        f"- confidence: `{payload['confidence']}`",
        "",
        "## Evidence Artifacts",
        "",
    ]
    for name, artifact_path in artifacts.items():
        content.append(f"- {name}: `{artifact_path}`")
    content.extend(
        [
            "",
            "Graphify artifacts are evidence only. `ingest` must review them before updating durable wiki pages.",
            "",
        ]
    )
    path.write_text("\n".join(content), encoding="utf-8")


def extract_command(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    target_theme = theme_dir(root, args.theme)
    output_dir = theme_output_dir(target_theme)
    source_id = args.source_id or default_source_id(target_theme)
    captured_at = utc_now()
    temp_path: Path | None = None
    source_warnings: list[str] = []
    graphify_attempts: list[dict[str, Any]] = []

    try:
        if args.graphify_output:
            source_dir = Path(args.repo).resolve() if Path(args.repo).exists() else Path(args.repo)
            commit = git_commit(source_dir) if source_dir.exists() else None
            graphify_output = Path(args.graphify_output).resolve()
            if not graphify_output.is_dir():
                raise SystemExit(f"--graphify-output directory not found: {graphify_output}")
        else:
            temp_path = Path(tempfile.mkdtemp(prefix="kb-graphify-"))
            source_dir, commit, source_warnings = clone_or_resolve_repo(args.repo, args.ref, temp_path)
            work_dir = temp_path if is_git_url(args.repo) else source_dir
            graphify_output, graphify_attempts = run_graphify(source_dir, args.backend, work_dir, args.extra_arg)

        artifacts = copy_required_outputs(graphify_output, output_dir, args.include_html, args.include_cache)
        graph_path = output_dir / "graph.json"
        report_path = output_dir / "GRAPH_REPORT.md"
        graph = read_json(graph_path)
        summary = graph_summary(graph)
        warnings = [*source_warnings]
        if not args.include_cache and (graphify_output / "cache").exists():
            warnings.append("graphify cache was not copied; runtime/cache artifacts are intentionally excluded")
        if not args.include_html and (graphify_output / "graph.html").exists():
            warnings.append("graph.html was not copied; runtime visualization is intentionally excluded")

        evidence_path = output_dir / "graphify-evidence.json"
        anchor_path = output_dir / "graphify-source-anchor.md"
        artifacts["evidence_json"] = evidence_path.as_posix()
        artifacts["source_anchor"] = anchor_path.as_posix()
        payload = {
            "schema_version": "evidence.v1",
            "source_id": source_id,
            "source_type": "git" if is_git_url(args.repo) or commit else "other",
            "content_type": "graphify-graph",
            "captured_at": captured_at,
            "source_uri": args.repo,
            "provenance": {
                "provider": "graphify",
                "timestamp": captured_at,
                "thread_or_run_id": commit,
            },
            "sensitivity": args.sensitivity,
            "retention": args.retention,
            "confidence": args.confidence,
            "redaction_notes": [],
            "content": {
                "graphify": graphify_version(),
                "command_attempts": graphify_attempts,
                "input": args.repo,
                "input_ref": args.ref,
                "backend": args.backend,
                "captured_commit": commit,
                "artifact_paths": {key: relpath(root, Path(value)) for key, value in artifacts.items()},
                "graph_summary": summary,
                "warnings": warnings,
            },
        }
        write_json(evidence_path, payload)
        artifacts["evidence_json"] = evidence_path.as_posix()
        write_anchor(anchor_path, payload, {key: relpath(root, Path(value)) for key, value in artifacts.items()})
        return {
            "status": "ok",
            "theme": relpath(root, target_theme),
            "output_dir": relpath(root, output_dir),
            "evidence": relpath(root, evidence_path),
            "source_anchor": relpath(root, anchor_path),
            "graph_summary": summary,
            "warnings": warnings,
        }
    finally:
        if temp_path is not None and args.keep_temp:
            print(f"Kept temporary directory: {temp_path}", file=sys.stderr)
        elif temp_path is not None and temp_path.exists():
            shutil.rmtree(temp_path)


def update_command(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    target_theme = theme_dir(root, args.theme)
    evidence_path = theme_output_dir(target_theme) / "graphify-evidence.json"
    if not evidence_path.exists():
        raise SystemExit(f"No prior Graphify evidence found: {evidence_path}")
    payload = read_json(evidence_path)
    content = payload.get("content") or {}
    extract_args = argparse.Namespace(
        root=args.root,
        format=args.format,
        repo=payload.get("source_uri"),
        theme=args.theme,
        backend=args.backend or content.get("backend") or "ollama",
        ref=content.get("input_ref"),
        source_id=payload.get("source_id"),
        sensitivity=payload.get("sensitivity") or "internal",
        retention=payload.get("retention") or "review",
        confidence=payload.get("confidence") or "inferred",
        graphify_output=None,
        keep_temp=False,
        include_html=False,
        include_cache=False,
        extra_arg=args.extra_arg,
    )
    return extract_command(extract_args)


def graph_path_for_theme(root: Path, theme: str) -> Path:
    target_theme = theme_dir(root, theme)
    graph_path = theme_output_dir(target_theme) / "graph.json"
    if not graph_path.exists():
        raise SystemExit(f"Graphify graph not found: {graph_path}")
    return graph_path


def graph_nodes_and_adjacency(graph: Any) -> tuple[dict[str, str], dict[str, list[dict[str, str]]]]:
    nodes, edges = graph_parts(graph)
    labels: dict[str, str] = {}
    for idx, node in enumerate(nodes):
        key = node_id(node, idx)
        labels[key] = node_label(node, key)
    adjacency: dict[str, list[dict[str, str]]] = {key: [] for key in labels}
    for edge in edges:
        source, target, relation = edge_endpoints(edge)
        if not source or not target:
            continue
        adjacency.setdefault(source, []).append({"id": target, "label": labels.get(target, target), "relation": relation or "related"})
        adjacency.setdefault(target, []).append({"id": source, "label": labels.get(source, source), "relation": relation or "related"})
        labels.setdefault(source, source)
        labels.setdefault(target, target)
    return labels, adjacency


def tokenize(text: str) -> list[str]:
    return [item for item in re.findall(r"[A-Za-z0-9_./:-]+", text.lower()) if len(item) >= 3]


def save_query_result(root: Path, theme: str, kind: str, payload: dict[str, Any]) -> Path:
    target_theme = theme_dir(root, theme)
    query_dir = theme_output_dir(target_theme) / QUERY_DIR_NAME
    query_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    path = query_dir / f"{stamp}-{kind}.json"
    write_json(path, payload)
    return path


def query_command(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    graph = read_json(graph_path_for_theme(root, args.theme))
    labels, adjacency = graph_nodes_and_adjacency(graph)
    terms = tokenize(args.question)
    scored = []
    for key, label in labels.items():
        text = f"{key} {label}".lower()
        score = sum(1 for term in terms if term in text)
        if score:
            scored.append((score, key, label))
    if not scored and terms:
        scored = [(0, key, label) for key, label in list(labels.items())[: args.top]]
    results = []
    for score, key, label in sorted(scored, key=lambda item: (-item[0], item[2].lower()))[: args.top]:
        results.append({"id": key, "label": label, "score": score, "neighbors": adjacency.get(key, [])[:10]})
    payload = {
        "schema_version": "graphify-query.v1",
        "query": args.question,
        "theme": args.theme,
        "captured_at": utc_now(),
        "result_count": len(results),
        "results": results,
        "note": "Graphify query results are routing hints, not durable wiki conclusions.",
    }
    output = save_query_result(root, args.theme, "query", payload)
    payload["saved_to"] = relpath(root, output)
    return payload


def find_node_key(labels: dict[str, str], needle: str) -> str | None:
    lowered = needle.lower()
    for key, label in labels.items():
        if lowered == key.lower() or lowered == label.lower():
            return key
    for key, label in labels.items():
        if lowered in key.lower() or lowered in label.lower():
            return key
    return None


def path_command(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    graph = read_json(graph_path_for_theme(root, args.theme))
    labels, adjacency = graph_nodes_and_adjacency(graph)
    start = find_node_key(labels, args.source)
    goal = find_node_key(labels, args.target)
    path: list[dict[str, str]] = []
    if start and goal:
        queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
        seen = {start}
        while queue:
            current, current_path = queue.popleft()
            if current == goal:
                path = [{"id": key, "label": labels.get(key, key)} for key in current_path]
                break
            if len(current_path) > args.max_depth:
                continue
            for neighbor in adjacency.get(current, []):
                neighbor_id = neighbor["id"]
                if neighbor_id not in seen:
                    seen.add(neighbor_id)
                    queue.append((neighbor_id, [*current_path, neighbor_id]))
    payload = {
        "schema_version": "graphify-query.v1",
        "theme": args.theme,
        "source": args.source,
        "target": args.target,
        "resolved_source": start,
        "resolved_target": goal,
        "captured_at": utc_now(),
        "path": path,
        "note": "Graphify path results are routing hints, not durable wiki conclusions.",
    }
    output = save_query_result(root, args.theme, "path", payload)
    payload["saved_to"] = relpath(root, output)
    return payload


def explain_command(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    graph = read_json(graph_path_for_theme(root, args.theme))
    labels, adjacency = graph_nodes_and_adjacency(graph)
    key = find_node_key(labels, args.concept)
    payload = {
        "schema_version": "graphify-query.v1",
        "theme": args.theme,
        "concept": args.concept,
        "resolved_node": key,
        "label": labels.get(key, key) if key else None,
        "captured_at": utc_now(),
        "neighbors": adjacency.get(key, [])[: args.top] if key else [],
        "note": "Graphify explain results are routing hints, not durable wiki conclusions.",
    }
    output = save_query_result(root, args.theme, "explain", payload)
    payload["saved_to"] = relpath(root, output)
    return payload


def global_dir(root: Path) -> Path:
    return root / GRAPHIFY_DIR_REL


def global_index_path(root: Path) -> Path:
    return global_dir(root) / GLOBAL_INDEX_NAME


def load_global_index(root: Path) -> dict[str, Any]:
    path = global_index_path(root)
    if path.exists():
        return read_json(path)
    return {"schema_version": "graphify-global-index.v1", "updated_at": utc_now(), "projects": []}


def save_global_index(root: Path, payload: dict[str, Any]) -> None:
    payload["updated_at"] = utc_now()
    write_json(global_index_path(root), payload)


def global_add_command(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    target_theme = theme_dir(root, args.theme)
    graph_path = theme_output_dir(target_theme) / "graph.json"
    evidence_path = theme_output_dir(target_theme) / "graphify-evidence.json"
    if not graph_path.exists():
        raise SystemExit(f"Graphify graph not found: {graph_path}")
    graph = read_json(graph_path)
    index = load_global_index(root)
    project = {
        "tag": args.tag,
        "theme": relpath(root, target_theme),
        "graph_path": relpath(root, graph_path),
        "evidence_path": relpath(root, evidence_path) if evidence_path.exists() else None,
        "added_at": utc_now(),
        "graph_summary": graph_summary(graph),
    }
    index["projects"] = [item for item in index.get("projects", []) if item.get("tag") != args.tag]
    index["projects"].append(project)
    index["projects"].sort(key=lambda item: str(item.get("tag")))
    save_global_index(root, index)
    return {"status": "ok", "project": project, "index": relpath(root, global_index_path(root))}


def normalized_label(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", text)


def graph_labels(graph: Any) -> list[str]:
    nodes, _edges = graph_parts(graph)
    labels = []
    for idx, node in enumerate(nodes):
        key = node_id(node, idx)
        label = node_label(node, key)
        if label:
            labels.append(label)
    return labels


def global_report_command(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    index = load_global_index(root)
    projects = []
    label_to_projects: dict[str, dict[str, Any]] = {}
    for item in index.get("projects", []):
        graph_path = resolve_under_root(root, str(item.get("graph_path") or ""))
        if not graph_path.exists():
            projects.append({**item, "status": "missing_graph"})
            continue
        graph = read_json(graph_path)
        labels = graph_labels(graph)
        projects.append({**item, "status": "ok", "label_count": len(labels)})
        for label in labels:
            normalized = normalized_label(label)
            if not normalized or len(normalized) < 3:
                continue
            bucket = label_to_projects.setdefault(normalized, {"label": label, "projects": set()})
            bucket["projects"].add(str(item.get("tag")))
    shared = []
    for normalized, value in label_to_projects.items():
        project_tags = sorted(value["projects"])
        if len(project_tags) > 1:
            shared.append({"label": value["label"], "normalized": normalized, "projects": project_tags, "project_count": len(project_tags)})
    shared.sort(key=lambda item: (-int(item["project_count"]), str(item["normalized"])))
    report = {
        "schema_version": "graphify-global-report.v1",
        "captured_at": utc_now(),
        "project_count": len(projects),
        "projects": projects,
        "shared_nodes": shared[:200],
        "note": "This is structural evidence only. Ingest must review relationships before editing cross-theme-map or shared nodes.",
    }
    out_dir = global_dir(root)
    json_path = out_dir / "global-cross-project-report.json"
    md_path = out_dir / "global-cross-project-report.md"
    write_json(json_path, report)
    lines = [
        "# Graphify Global Cross-Project Report",
        "",
        "This report is structural evidence only. Do not treat it as confirmed semantic reuse without ingest review.",
        "",
        f"- captured_at: `{report['captured_at']}`",
        f"- project_count: `{report['project_count']}`",
        "",
        "## Registered Projects",
        "",
    ]
    for project in projects:
        lines.append(f"- `{project.get('tag')}` -> `{project.get('theme')}` ({project.get('status')})")
    lines.extend(["", "## Shared Structural Nodes", "", "| Label | Projects |", "| --- | --- |"])
    for item in shared[:50]:
        lines.append(f"| {item['label']} | {', '.join(item['projects'])} |")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "ok", "json": relpath(root, json_path), "markdown": relpath(root, md_path), "shared_node_count": len(shared)}


def status_command(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    graphs = []
    for graph_path in sorted(root.glob("themes/*/*/outputs/document-intake/graphify/graph.json")):
        graphs.append(
            {
                "graph_path": relpath(root, graph_path),
                "evidence_exists": (graph_path.parent / "graphify-evidence.json").exists(),
                "report_exists": (graph_path.parent / "GRAPH_REPORT.md").exists(),
                "source_anchor_exists": (graph_path.parent / "graphify-source-anchor.md").exists(),
            }
        )
    return {
        "schema_version": "kb-graphify-bridge.v1",
        "root": str(root),
        "checked_at": utc_now(),
        "graphify": graphify_version(),
        "graph_count": len(graphs),
        "graphs": graphs,
        "global_index_exists": global_index_path(root).exists(),
    }


def print_payload(payload: Any, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, dict):
        status = payload.get("status") or payload.get("schema_version") or "ok"
        print(f"status={status}")
        for key, value in payload.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                print(f"{key}={value}")
            elif key in {"warnings"} and value:
                print(f"{key}={'; '.join(str(item) for item in value)}")
            elif key.endswith("count") or key in {"graph_count", "shared_node_count"}:
                print(f"{key}={value}")
        return
    print(payload)


def main() -> int:
    args = parse_args()
    if args.command == "status":
        payload = status_command(args)
    elif args.command == "extract":
        payload = extract_command(args)
    elif args.command == "update":
        payload = update_command(args)
    elif args.command == "global-add":
        payload = global_add_command(args)
    elif args.command == "global-list":
        payload = load_global_index(Path(args.root).resolve())
    elif args.command == "global-report":
        payload = global_report_command(args)
    elif args.command == "query":
        payload = query_command(args)
    elif args.command == "path":
        payload = path_command(args)
    elif args.command == "explain":
        payload = explain_command(args)
    else:
        raise SystemExit(f"Unknown command: {args.command}")
    print_payload(payload, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
