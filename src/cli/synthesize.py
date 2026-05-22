from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..agent import CONFIRM_WRITE, AgentResponse, apply_changes, build_synthesize_request, render_change_diffs, resolve_provider
from ..core.assets import assets_root


def register_synthesize(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("synthesize", help="Generate demand-driven cross-project engineering outputs.")
    parser.add_argument("--root", default=".", help="Knowledge base root.")
    parser.add_argument("--target-theme", required=True, help="Target project theme, for example themes/project/00-product.")
    parser.add_argument("--search-mode", choices=["auto", "keyword", "multi"], default="auto", help="Deterministic asset matching route. Defaults to auto multi-route with keyword fallback.")
    parser.add_argument("--provider", choices=["openai", "command"], help="Agent provider. Defaults to env or OpenAI.")
    parser.add_argument("--model", help="Model name for provider=openai. Defaults to LLM_WIKI_MODEL.")
    parser.add_argument("--agent-command", help="External command for provider=command. Reads JSON on stdin and writes JSON on stdout.")
    parser.add_argument("--confirm", default="", help=f"Apply proposed synthesis changes only with {CONFIRM_WRITE}.")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    parser.set_defaults(handler=run_synthesize)


def run_synthesize(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    request = build_synthesize_request(root, args.target_theme, search_mode=args.search_mode)
    provider = resolve_provider(args.provider, model=args.model, agent_command=args.agent_command)
    response = provider.complete(request)
    diffs = render_change_diffs(root, response.proposed_changes)

    apply_result: dict[str, Any] | None = None
    post_apply: dict[str, Any] | None = None
    if args.confirm == CONFIRM_WRITE:
        apply_result = apply_changes(root, response.proposed_changes, confirm=args.confirm)
        if apply_result.get("status") in {"ok", "partial"}:
            _append_synthesize_log(root, request.task["target_theme"], response, apply_result)
            post_apply = _post_synthesize(root)

    if args.format == "json":
        print(
            json.dumps(
                {
                    "target_theme": request.task["target_theme"],
                    "mode": "applied" if apply_result else "dry-run",
                    "response": response.to_dict(),
                    "diffs": diffs,
                    "apply": apply_result,
                    "post_apply": post_apply,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_synthesize(response, diffs, apply_result, post_apply)

    if apply_result and apply_result.get("status") == "partial":
        return 1
    return 0


def _print_synthesize(
    response: AgentResponse,
    diffs: list[dict[str, Any]],
    apply_result: dict[str, Any] | None,
    post_apply: dict[str, Any] | None,
) -> None:
    print(response.answer)
    print()
    print(f"answer_status: {response.answer_status}")
    print(f"writeback_candidate: {response.writeback_candidate}")
    if response.gaps:
        print("gaps:")
        for gap in response.gaps:
            print(f"- {gap}")
    if not diffs:
        print("proposed_changes: none")
    else:
        print("proposed_changes:")
        for item in diffs:
            change = item["change"]
            print(f"- {change['action']} {change['path']} [{item['status']}]")
            if item.get("error"):
                print(f"  error: {item['error']}")
            elif item.get("diff"):
                print(item["diff"])
    if apply_result:
        print()
        print(f"apply_status: {apply_result.get('status')}")
        for item in apply_result.get("applied", []):
            print(f"- applied {item['action']} {item['path']}")
        for item in apply_result.get("denied", []):
            print(f"- denied {item['change'].get('path')}: {item['error']}")
    else:
        print()
        print(f"dry_run: pass --confirm {CONFIRM_WRITE} to apply proposed changes")
    if post_apply:
        print()
        print("post_apply:")
        for name, result in post_apply.items():
            print(f"- {name}: exit_code={result['exit_code']}")


def _append_synthesize_log(root: Path, target_theme: str, response: AgentResponse, apply_result: dict[str, Any]) -> None:
    applied = ", ".join(item.get("path", "") for item in apply_result.get("applied", []) if item.get("path")) or "none"
    append_activity_log = _load_activity_log_helper(root)
    append_activity_log(
        root,
        skill="synthesize",
        action="synthesize",
        summary=f"Generated synthesis outputs for `{target_theme}`.",
        status=str(apply_result.get("status", "completed")),
        details=[
            f"answer_status={response.answer_status}",
            f"writeback_candidate={response.writeback_candidate}",
            f"applied={applied}",
        ],
    )


def _load_activity_log_helper(root: Path) -> Any:
    candidate = root / ".agents" / "skills" / "shared" / "scripts" / "kb_activity_log.py"
    if not candidate.exists():
        candidate = Path(str(assets_root() / "skills" / "shared" / "scripts" / "kb_activity_log.py"))
    module_name = "llm_wiki_cli_activity_log"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing.append_activity_log
    spec = importlib.util.spec_from_file_location(module_name, candidate)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load activity log helper: {candidate}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.append_activity_log


def _post_synthesize(root: Path) -> dict[str, Any]:
    return {
        "query_index": _run_script(_tool_script(root, "kb_query_index.py"), ["--root", str(root), "--format", "json", "index"], root),
        "lint_summary": _run_script(_lint_script(root), ["--root", str(root), "--summary", "--summary-top", "5"], root),
    }


def _tool_script(root: Path, name: str) -> Path:
    candidate = root / "tools" / name
    if candidate.exists():
        return candidate
    return Path(str(assets_root() / "tools" / name))


def _lint_script(root: Path) -> Path:
    candidate = root / ".agents" / "skills" / "lint" / "scripts" / "kb_lint.py"
    if candidate.exists():
        return candidate
    return Path(str(assets_root() / "skills" / "lint" / "scripts" / "kb_lint.py"))


def _run_script(script: Path, script_args: list[str], root: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(script), *script_args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
