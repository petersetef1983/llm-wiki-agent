from __future__ import annotations

import subprocess
import sys
from importlib import resources
from pathlib import Path

from .assets import assets_root, diff_trees
from .manifest import CANONICAL_SKILL_ROOT, is_existing_kb_root, validate_manifest
from .mirror import check_one_platform


def asset_drift(root: Path) -> list[str]:
    issues: list[str] = []
    components = [
        ("schema", assets_root() / "schema", root / "schema"),
        ("tools", assets_root() / "tools", root / "tools"),
        ("skills", assets_root() / "skills", root / CANONICAL_SKILL_ROOT),
    ]
    for name, src_traversable, dst in components:
        with resources.as_file(src_traversable) as src:
            diff = diff_trees(src, dst)
            for item in diff.missing:
                issues.append(f"{name}: missing {item}")
            for item in diff.changed:
                issues.append(f"{name}: changed {item}")
            if diff.extra:
                issues.append(f"{name}: preserve extras ({len(diff.extra)} file(s))")
    return issues


def run_existing_lint(root: Path) -> tuple[int, str]:
    lint_script = root / ".agents" / "skills" / "lint" / "scripts" / "kb_lint.py"
    if not lint_script.exists():
        return 1, f"lint script missing: {lint_script}"
    proc = subprocess.run(
        [sys.executable, str(lint_script), "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode, output


def doctor(root: Path, *, platforms: list[str]) -> int:
    kb_root = root.resolve()
    issues: list[str] = []
    if not is_existing_kb_root(kb_root):
        issues.append("root is missing required LLM Wiki paths")
    issues.extend(validate_manifest(kb_root, platforms))
    issues.extend(asset_drift(kb_root))
    for platform in platforms:
        issues.extend(f"{platform}: {item}" for item in check_one_platform(kb_root, platform))

    lint_code, lint_output = run_existing_lint(kb_root)
    if lint_code != 0:
        issues.append(f"kb_lint exited with {lint_code}")

    if issues:
        print(f"LLM Wiki Doctor: issues={len(issues)}")
        for issue in issues:
            print(f"- {issue}")
        if lint_output:
            print("\n[lint]")
            print(lint_output)
        return 1

    print("LLM Wiki Doctor: ok")
    if lint_output:
        print("\n[lint]")
        print(lint_output)
    return 0
