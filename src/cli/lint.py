from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..agent import CONFIRM_WRITE, AgentResponse, apply_changes, build_lint_request, render_change_diffs, resolve_provider
from ..core.assets import assets_root


def register_lint(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("lint", help="Run content, graph, and knowledge lint checks.")
    parser.add_argument("--root", default=".", help="Knowledge base root.")
    parser.add_argument("--scope", choices=["structure", "graph", "knowledge", "all"], default="all", help="Check scope.")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on warnings as well as errors.")
    parser.add_argument("--summary", action="store_true", help="Print compact top-issues summary.")
    parser.add_argument("--summary-top", type=int, default=5, help="Number of top issues in summary mode.")
    parser.add_argument("--explain", action="store_true", help="Ask an agent to explain deterministic lint findings.")
    parser.add_argument("--fix-plan", action="store_true", help="Ask an agent for a safe fix plan and optional proposed changes.")
    parser.add_argument("--provider", choices=["openai", "command"], help="Agent provider for --explain/--fix-plan.")
    parser.add_argument("--model", help="Model name for provider=openai. Defaults to LLM_WIKI_MODEL.")
    parser.add_argument("--agent-command", help="External command for provider=command. Reads JSON on stdin and writes JSON on stdout.")
    parser.add_argument("--confirm", default="", help=f"Apply proposed fix-plan changes only with {CONFIRM_WRITE}.")
    parser.set_defaults(handler=run_lint)


def run_lint(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not args.explain and not args.fix_plan:
        result = _run_lint(root, args, output_format=args.format)
        if result["stdout"]:
            print(result["stdout"])
        if result["stderr"]:
            print(result["stderr"], file=sys.stderr)
        return int(result["exit_code"])

    lint_result = _run_lint(root, args, output_format="json")
    lint_payload = _parse_json(lint_result["stdout"]) or {
        "status": "error",
        "stdout": lint_result["stdout"],
        "stderr": lint_result["stderr"],
        "exit_code": lint_result["exit_code"],
    }
    request = build_lint_request(root, lint_payload, fix_plan=args.fix_plan)
    provider = resolve_provider(args.provider, model=args.model, agent_command=args.agent_command)
    response = provider.complete(request)
    diffs = render_change_diffs(root, response.proposed_changes)
    apply_result = None
    if args.fix_plan and args.confirm == CONFIRM_WRITE:
        apply_result = apply_changes(root, response.proposed_changes, confirm=args.confirm)

    if args.format == "json":
        print(
            json.dumps(
                {
                    "lint": lint_payload,
                    "lint_exit_code": lint_result["exit_code"],
                    "response": response.to_dict(),
                    "diffs": diffs,
                    "apply": apply_result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_agent_lint(lint_payload, response, diffs, apply_result)
    if apply_result and apply_result.get("status") == "partial":
        return 1
    return int(lint_result["exit_code"])


def _print_agent_lint(
    lint_payload: dict[str, Any],
    response: AgentResponse,
    diffs: list[dict[str, Any]],
    apply_result: dict[str, Any] | None,
) -> None:
    summary = lint_payload.get("summary")
    if summary:
        print(f"lint_summary: errors={summary.get('error', 0)} warnings={summary.get('warning', 0)} info={summary.get('info', 0)}")
        print()
    print(response.answer)
    if response.gaps:
        print("gaps:")
        for gap in response.gaps:
            print(f"- {gap}")
    if diffs:
        print("proposed_changes:")
        for item in diffs:
            change = item["change"]
            print(f"- {change['action']} {change['path']} [{item['status']}]")
            if item.get("error"):
                print(f"  error: {item['error']}")
    if apply_result:
        print(f"apply_status: {apply_result.get('status')}")
    elif diffs:
        print(f"dry_run: pass --confirm {CONFIRM_WRITE} with --fix-plan to apply proposed changes")


def _run_lint(root: Path, args: argparse.Namespace, *, output_format: str) -> dict[str, Any]:
    script_args = [
        "--root",
        str(root),
        "--scope",
        args.scope,
        "--format",
        output_format,
        "--summary-top",
        str(args.summary_top),
    ]
    if args.strict:
        script_args.append("--strict")
    if args.summary and output_format == "text":
        script_args.append("--summary")
    proc = subprocess.run(
        [sys.executable, str(_lint_script(root)), *script_args],
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


def _lint_script(root: Path) -> Path:
    candidate = root / ".agents" / "skills" / "lint" / "scripts" / "kb_lint.py"
    if candidate.exists():
        return candidate
    return Path(str(assets_root() / "skills" / "lint" / "scripts" / "kb_lint.py"))


def _parse_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
