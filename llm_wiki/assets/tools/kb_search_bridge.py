#!/usr/bin/env python3
"""Thin qmd CLI bridge for LLM Wiki search workflows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from kb_qmd_capabilities import (
    WINDOWS_VECTOR_DISABLED_REASON,
    detect_qmd_capability,
    is_windows_native,
    run_mcp_http_search,
    run_native_qmd,
    run_wsl_qmd,
    run_wsl_qmd_embed,
)


MODE_TO_QMD_COMMAND = {
    "keyword": "search",
    "bm25": "search",
    "vector": "vsearch",
    "semantic": "vsearch",
    "hybrid": "query",
}
DEFAULT_COLLECTION_NAME = "wiki"
DEFAULT_CONTEXT = "LLM Wiki 个人知识库：项目、shared graph、技术资产和工程输出"
DEFAULT_MASK = "**/*.md"


def parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS, help="Knowledge-base root. Defaults to current directory.")
    common.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(description="Bridge qmd search commands into the KB tool surface.")
    parser.add_argument("--root", default=".", help="Knowledge-base root. Defaults to current directory.")
    parser.add_argument("--format", choices=["text", "json"], default="json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", parents=[common], help="Report qmd BM25/vector/hybrid capability for this KB.")

    init_cmd = subparsers.add_parser("init", parents=[common], help="Initialize qmd collection/context for this KB.")
    init_cmd.add_argument("--name", default=DEFAULT_COLLECTION_NAME, help="qmd collection name.")
    init_cmd.add_argument("--context", default=DEFAULT_CONTEXT, help="qmd context description.")
    init_cmd.add_argument("--mask", default=DEFAULT_MASK, help="qmd collection mask.")
    init_cmd.add_argument("--embed", action="store_true", help="Also run vector embed when --kind is vector/all.")
    init_cmd.add_argument("--kind", choices=["lexical", "vector", "all"], default="lexical", help="Embedding kind when --embed is used.")

    index_cmd = subparsers.add_parser("index", parents=[common], help="Check/update qmd search state without embedding unless explicitly requested.")
    index_cmd.add_argument("--kind", choices=["lexical", "vector", "all"], default="lexical")
    index_cmd.add_argument("--extra-arg", action="append", default=[], help="Extra argument to pass through to qmd. Repeatable.")

    search_cmd = subparsers.add_parser("search", parents=[common], help="Search through qmd without reimplementing search logic.")
    search_cmd.add_argument("--query", required=True)
    search_cmd.add_argument("--mode", choices=["auto", *sorted(MODE_TO_QMD_COMMAND)], default="auto")
    search_cmd.add_argument("--top", type=int, default=10)
    search_cmd.add_argument("--allow-fallback", action="store_true", help="Allow vector-only search to fall back to BM25 when vector is unavailable.")
    search_cmd.add_argument("--json-output", action="store_true", help="Ask qmd for JSON output when supported.")
    search_cmd.add_argument("--extra-arg", action="append", default=[], help="Extra argument to pass through to qmd. Repeatable.")

    return parser.parse_args()


def next_commands(
    name: str = DEFAULT_COLLECTION_NAME,
    context: str = DEFAULT_CONTEXT,
    mask: str = DEFAULT_MASK,
    include_install: bool = True,
) -> list[str]:
    commands = [
        f'qmd collection add . --name {name} --mask "{mask}"',
        f'qmd context add qmd://{name} "{context}"',
        "python tools/kb_search_bridge.py index --root . --kind lexical",
        'python tools/kb_search_bridge.py search --root . --query "告警分级分类" --mode auto --top 10',
    ]
    if include_install:
        commands.insert(0, "npm install -g @tobilu/qmd")
    return commands


def write_payload(payload: dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    status = payload.get("status") or payload.get("command")
    print(f"status={status}")
    for key, value in payload.items():
        if key == "stdout" and value:
            print(value)
        elif key not in {"stdout"}:
            print(f"{key}={value}")


def status_payload(root: Path) -> dict[str, Any]:
    caps = detect_qmd_capability(root)
    payload: dict[str, Any] = {
        **caps,
        "schema_version": "kb-search-bridge.v1",
        "root": str(root),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if caps.get("capability_mode") == "none":
        payload.update(
            {
                "status": "missing",
                "issue_code": "qmd_index_missing",
                "message": "qmd not available via native, WSL2 HTTP, or WSL2 CLI.",
                "next_commands": next_commands(include_install=True),
            }
        )
    elif caps.get("hybrid_available"):
        payload["status"] = "ok"
    elif caps.get("bm25_available"):
        payload["status"] = "degraded"
    else:
        payload["status"] = "unknown"
    return payload


def unavailable_vector_payload(root: Path, mode: str, allow_fallback: bool, capabilities: dict[str, Any], command: str = "search") -> dict[str, Any]:
    return {
        "schema_version": "kb-search-bridge.v1",
        "root": str(root),
        "command": command,
        "mode": mode,
        "status": "unavailable",
        "issue_code": "qmd_vector_unavailable",
        "allow_fallback": allow_fallback,
        "message": capabilities.get("degraded_reason")
        or "qmd vector/hybrid capability is unavailable. Use --allow-fallback for BM25 or enable WSL2 qmd.",
        "capabilities": {
            "capability_mode": capabilities.get("capability_mode"),
            "execution_paths": capabilities.get("execution_paths"),
            "bm25_available": capabilities.get("bm25_available"),
            "vector_available": capabilities.get("vector_available"),
            "hybrid_available": capabilities.get("hybrid_available"),
        },
    }


def resolve_search_command(mode: str, capabilities: dict[str, Any], allow_fallback: bool) -> tuple[str | None, str | None, str | None]:
    paths = list(capabilities.get("execution_paths") or [])
    full_path = "wsl_http_query" if "wsl_http_query" in paths else "wsl_cli_query" if "wsl_cli_query" in paths else "native_full" if "native_vector" in paths else None
    bm25_path = "native_bm25" if "native_bm25" in paths else full_path
    if mode in {"keyword", "bm25"}:
        return "search", None, bm25_path
    if mode == "auto":
        if capabilities.get("hybrid_available") and full_path:
            return "query", None, full_path
        return "search", "auto" if capabilities.get("degraded_reason") else None, bm25_path
    if mode == "hybrid":
        if capabilities.get("hybrid_available") and full_path:
            return "query", None, full_path
        if allow_fallback and capabilities.get("bm25_available"):
            return "search", "hybrid", bm25_path
        return None, "hybrid", None
    if mode in {"vector", "semantic"}:
        if capabilities.get("vector_available") and full_path:
            return "vsearch", None, full_path
        if allow_fallback and capabilities.get("bm25_available"):
            return "search", mode, bm25_path
        return None, mode, None
    return MODE_TO_QMD_COMMAND[mode], None, bm25_path


def run_search(root: Path, execution_path: str, qmd_command: str, query: str, top: int, json_output: bool, extra_args: list[str], caps: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    qmd_args = [qmd_command, query]
    if json_output:
        qmd_args.append("--json")
    qmd_args.extend(["-n", str(top), *extra_args])
    if execution_path == "wsl_http_query":
        return run_mcp_http_search(
            query,
            top=top,
            want_vector=qmd_command in {"query", "vsearch"},
            json_output=json_output,
            timeout=120,
            caps=caps.get("mcp_http"),
        )
    if execution_path == "wsl_cli_query":
        return run_wsl_qmd(root, qmd_args, timeout=300)
    return run_native_qmd(root, qmd_args, timeout=300)


def parse_stdout_json(stdout: str) -> Any:
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def can_run_native_setup(caps: dict[str, Any]) -> bool:
    return bool(caps.get("native", {}).get("native_qmd_path"))


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    if args.command == "status":
        payload = status_payload(root)
        write_payload(payload, args.format)
        return 0

    caps = status_payload(root)

    if args.command == "init":
        if not can_run_native_setup(caps):
            payload = caps | {"message": "Native qmd is required for collection/context setup on this host."}
            write_payload(payload, args.format)
            return 2
        steps: list[dict[str, Any]] = []
        commands = [
            ["collection", "add", ".", "--name", args.name, "--mask", args.mask],
            ["context", "add", f"qmd://{args.name}", args.context],
        ]
        embed_skipped = args.embed and args.kind == "lexical"
        if args.embed and args.kind in {"vector", "all"}:
            if is_windows_native():
                completed = run_wsl_qmd_embed(root, timeout=3600)
                steps.append(
                    {
                        "execution_path": "wsl_cli_query",
                        "qmd_args": ["update", "&&", "embed"],
                        "exit_code": completed.returncode,
                        "stdout": completed.stdout.strip(),
                        "stderr": completed.stderr.strip(),
                    }
                )
                if completed.returncode != 0:
                    write_payload({"schema_version": "kb-search-bridge.v1", "root": str(root), "command": "init", "exit_code": completed.returncode, "steps": steps}, args.format)
                    return completed.returncode
            else:
                commands.append(["embed"])
        exit_code = 0
        for qmd_args in commands:
            completed = run_native_qmd(root, qmd_args, timeout=3600 if qmd_args == ["embed"] else 120)
            steps.append(
                {
                    "execution_path": "native_bm25",
                    "qmd_args": qmd_args,
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                }
            )
            if completed.returncode != 0:
                exit_code = completed.returncode
                break
        payload = {
            "schema_version": "kb-search-bridge.v1",
            "root": str(root),
            "command": "init",
            "collection": args.name,
            "mask": args.mask,
            "context": args.context,
            "embed_requested": args.embed,
            "kind": args.kind,
            "embed_skipped": embed_skipped,
            "exit_code": exit_code,
            "steps": steps,
        }
        write_payload(payload, args.format)
        return exit_code

    if args.command == "index":
        if args.kind == "lexical":
            if not can_run_native_setup(caps):
                write_payload(caps, args.format)
                return 2
            completed = run_native_qmd(root, ["status", "--json", *args.extra_arg], timeout=30)
            qmd_args = ["status", "--json", *args.extra_arg]
            execution_path = "native_bm25"
        else:
            if is_windows_native():
                if not caps.get("vector_available") or "wsl_cli_query" not in list(caps.get("execution_paths") or []):
                    payload = unavailable_vector_payload(root, f"index:{args.kind}", False, caps, command="index")
                    payload["message"] = "WSL2 qmd CLI is required for vector indexing on native Windows."
                    write_payload(payload, args.format)
                    return 3
                completed = run_wsl_qmd_embed(root, args.extra_arg, timeout=3600)
                qmd_args = ["update", "&&", "embed", *args.extra_arg]
                execution_path = "wsl_cli_query"
            else:
                completed = run_native_qmd(root, ["embed", *args.extra_arg], timeout=3600)
                qmd_args = ["embed", *args.extra_arg]
                execution_path = "native_full"
        payload = {
            "schema_version": "kb-search-bridge.v1",
            "root": str(root),
            "command": "index",
            "kind": args.kind,
            "execution_path": execution_path,
            "qmd_args": qmd_args,
            "vector_embedding_executed": args.kind in {"vector", "all"},
            "exit_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
        write_payload(payload, args.format)
        return completed.returncode

    if args.command == "search":
        if not caps.get("bm25_available") and not caps.get("vector_available"):
            write_payload(caps, args.format)
            return 2
        qmd_command, degraded_from, execution_path = resolve_search_command(args.mode, caps, args.allow_fallback)
        if qmd_command is None or execution_path is None:
            payload = unavailable_vector_payload(root, args.mode, args.allow_fallback, caps)
            write_payload(payload, args.format)
            return 3
        json_output = args.json_output or args.format == "json"
        completed = run_search(root, execution_path, qmd_command, args.query, args.top, json_output, args.extra_arg, caps)
        payload = {
            "schema_version": "kb-search-bridge.v1",
            "root": str(root),
            "command": "search",
            "mode": args.mode,
            "resolved_mode": "bm25" if qmd_command == "search" else ("vector" if qmd_command == "vsearch" else "hybrid"),
            "degraded_from": degraded_from,
            "execution_path": execution_path,
            "exit_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
        parsed = parse_stdout_json(completed.stdout)
        if args.format == "json" and parsed is not None:
            payload["results"] = parsed
        write_payload(payload, args.format)
        return completed.returncode

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
