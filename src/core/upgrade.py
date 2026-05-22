from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

from .assets import assets_root, copy_filesystem_tree, diff_trees, write_text
from .inbox import INBOX_STAGING_DIRS
from .manifest import CANONICAL_SKILL_ROOT, SUPPORTED_PLATFORMS, expected_manifest_text, is_existing_kb_root
from .mirror import sync_one_platform


CONFIRM_UPGRADE = "UPGRADE-KB"
USER_KNOWLEDGE_DIRS = {"themes", "shared", "index", "inbox"}
QMD_PLATFORM_IGNORE_LINES = (
    '      - ".trae/**"',
    '      - ".opencode/**"',
    '      - ".openclaw/**"',
    '      - ".hermes/**"',
)
DEPRECATED_GENERATED_PATHS = (Path(".agents/skills/bootstrap/assets/skeleton"),)


def describe_diff(actions: list[str], name: str, missing: list[str], changed: list[str], extra: list[str]) -> None:
    if missing or changed:
        actions.append(f"upgrade {name} ({len(missing) + len(changed)} diff(s))")
        for item in missing[:20]:
            actions.append(f"  missing:{item}")
        for item in changed[:20]:
            actions.append(f"  changed:{item}")
        omitted = max(0, len(missing) + len(changed) - 40)
        if omitted:
            actions.append(f"  ... {omitted} more")
    else:
        actions.append(f"check {name}: up to date")
    if extra:
        actions.append(f"preserve {name} extras ({len(extra)} file(s))")


def ensure_qmd_config(kb_root: Path, actions: list[str], dry_run: bool) -> None:
    qmd_path = kb_root / "qmd.yml"
    if not qmd_path.exists():
        actions.append("upgrade qmd.yml (missing)")
        if not dry_run:
            with resources.as_file(assets_root() / "kb-skeleton" / "qmd.yml") as src:
                qmd_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return

    text = qmd_path.read_text(encoding="utf-8")
    missing_lines = [line for line in QMD_PLATFORM_IGNORE_LINES if line.strip()[2:] not in text]
    if not missing_lines:
        actions.append("check qmd.yml: up to date")
        return

    labels = ", ".join(line.strip()[2:] for line in missing_lines)
    actions.append(f"upgrade qmd.yml (add {labels} ignore)")
    if dry_run:
        return

    lines = text.splitlines()
    insert_after = None
    for marker in [
        '      - ".hermes/**"',
        '      - ".openclaw/**"',
        '      - ".opencode/**"',
        '      - ".trae/**"',
        '      - ".codex/**"',
        '      - ".claude/**"',
        '      - ".agents/**"',
        "    ignore:",
    ]:
        for idx, line in enumerate(lines):
            if line.rstrip() == marker:
                insert_after = idx
        if insert_after is not None:
            break
    if insert_after is None:
        lines.extend(missing_lines)
    else:
        for offset, line in enumerate(missing_lines, start=1):
            lines.insert(insert_after + offset, line)
    qmd_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def cleanup_deprecated_generated_paths(kb_root: Path, actions: list[str], dry_run: bool) -> None:
    for rel in DEPRECATED_GENERATED_PATHS:
        target = kb_root / rel
        if not target.exists():
            continue
        actions.append(f"remove deprecated generated asset {rel.as_posix()}")
        if dry_run:
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()


def ensure_inbox_staging_dirs(kb_root: Path, actions: list[str], dry_run: bool) -> None:
    missing = [rel for rel in INBOX_STAGING_DIRS if not (kb_root / rel).is_dir()]
    if not missing:
        actions.append("check inbox staging dirs: up to date")
        return
    actions.append(f"upgrade inbox staging dirs ({len(missing)} missing)")
    for rel in missing:
        actions.append(f"  mkdir:{rel.as_posix()}")
        if not dry_run:
            (kb_root / rel).mkdir(parents=True, exist_ok=True)


def upgrade_kb(root: Path, *, dry_run: bool, confirm: str, force_conflicts: bool) -> int:
    kb_root = root.resolve()
    if not is_existing_kb_root(kb_root):
        print(f"Refusing to upgrade non-KB root: {kb_root}")
        return 2
    if not dry_run and confirm != CONFIRM_UPGRADE:
        print(f"Refusing to upgrade without --confirm {CONFIRM_UPGRADE}. Use --dry-run first.")
        return 2

    actions: list[str] = []
    conflicts: list[str] = []
    components = [
        ("schema", assets_root() / "schema", kb_root / "schema", False),
        ("tools", assets_root() / "tools", kb_root / "tools", False),
        ("skills", assets_root() / "skills", kb_root / CANONICAL_SKILL_ROOT, True),
        ("templates", assets_root() / "templates", kb_root / ".agents" / "templates", False),
    ]
    for name, src_traversable, dst, conflict_sensitive in components:
        with resources.as_file(src_traversable) as src:
            diff = diff_trees(src, dst)
            describe_diff(actions, name, diff.missing, diff.changed, diff.extra)
            if conflict_sensitive and diff.changed:
                conflicts.extend(diff.changed)
            if not dry_run and (diff.missing or diff.changed):
                if conflict_sensitive and diff.changed and not force_conflicts:
                    continue
                copy_filesystem_tree(src, dst, [], dry_run=False)

    ensure_qmd_config(kb_root, actions, dry_run)
    ensure_inbox_staging_dirs(kb_root, actions, dry_run)
    cleanup_deprecated_generated_paths(kb_root, actions, dry_run)

    if conflicts and not force_conflicts:
        actions.append(f"conflict skills ({len(conflicts)} file(s)); rerun with --force-conflicts to overwrite")

    actions.append("sync platform adapters")
    if not dry_run and (not conflicts or force_conflicts):
        for platform in SUPPORTED_PLATFORMS:
            sync_one_platform(kb_root, platform, [], check=False)
        write_text(kb_root / "llm-wiki.yaml", expected_manifest_text(list(SUPPORTED_PLATFORMS)), [], dry_run=False)

    blocked = bool(conflicts and not force_conflicts and not dry_run)
    mode = "DRY RUN" if dry_run else "BLOCKED" if blocked else "APPLIED"
    print(f"[{mode}] upgrade {kb_root}")
    for action in actions:
        print(f"- {action}")
    if blocked:
        return 1
    return 0
