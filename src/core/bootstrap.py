from __future__ import annotations

from pathlib import Path

from .assets import assets_root, copy_traversable_tree, write_text
from .manifest import CANONICAL_SKILL_ROOT, expected_manifest_text, is_existing_kb_root
from .mirror import sync_one_platform


CONFIRM_CREATE = "CREATE-KB"
RUNTIME_DIRS = {".codex", ".agents", ".claude", ".trae", ".opencode", ".openclaw", ".hermes"}
RUNTIME_ALLOWED_FILENAMES = {
    ".mirror-state.json",
    "settings.json",
    "config.json",
    "state.json",
    "metadata.json",
    "README.md",
}
RUNTIME_ALLOWED_SUFFIXES = {".log", ".tmp", ".cache"}
RUNTIME_ALLOWED_DIR_NAMES = {
    "__pycache__",
    "cache",
    "caches",
    "logs",
    "tmp",
    "temp",
    "state",
    "sessions",
    "runs",
    "rules",
    "plans",
}
SKELETON_DIRS = (
    Path("themes/general"),
    Path("themes/project"),
    Path("themes/research"),
    Path("inbox/to-be-filed"),
)


def is_recognized_runtime_path(rel: Path) -> bool:
    parts = rel.parts
    if not parts:
        return True
    if len(parts) >= 2 and parts[0] == "skills" and parts[1] == "bootstrap":
        return True
    if any(part == "__pycache__" for part in parts):
        return True
    if any(part.lower() in RUNTIME_ALLOWED_DIR_NAMES for part in parts[:-1]):
        return True
    name = parts[-1]
    if name in RUNTIME_ALLOWED_FILENAMES:
        return True
    if Path(name).suffix in RUNTIME_ALLOWED_SUFFIXES:
        return True
    return False


def classify_target(root: Path) -> tuple[bool, list[str], list[str]]:
    ignored: list[str] = []
    blockers: list[str] = []
    if not root.exists():
        return True, ignored, blockers
    if not root.is_dir():
        return False, ignored, [f"target is not a directory: {root}"]

    for child in sorted(root.iterdir()):
        if child.name not in RUNTIME_DIRS:
            blockers.append(f"ordinary path exists: {child}")
            continue
        unknowns: list[str] = []
        for descendant in sorted(child.rglob("*")):
            if descendant.is_dir():
                continue
            rel = descendant.relative_to(child)
            if not is_recognized_runtime_path(rel):
                unknowns.append(str(descendant))
        if unknowns:
            blockers.extend(f"unknown runtime content: {item}" for item in unknowns)
        else:
            ignored.append(str(child))
    return not blockers, ignored, blockers


def ensure_skeleton_dirs(root: Path, actions: list[str], dry_run: bool) -> None:
    for rel in SKELETON_DIRS:
        path = root / rel
        action = f"mkdir {path}"
        if not path.exists() and action not in actions:
            actions.append(action)
        if not dry_run:
            path.mkdir(parents=True, exist_ok=True)


def init_kb(target: Path, *, platforms: list[str], dry_run: bool, confirm: str, adopt_existing: bool) -> int:
    root = target.resolve()
    existing = is_existing_kb_root(root)
    actions: list[str] = []

    if existing and not adopt_existing:
        print(f"Refusing to initialize existing LLM Wiki root: {root}")
        print("Use --adopt-existing to add agent-kit metadata/platform adapters.")
        return 2

    if not existing:
        safe, ignored, blockers = classify_target(root)
        if not safe:
            print(f"Refusing to initialize non-empty target: {root}")
            for blocker in blockers:
                print(f"- {blocker}")
            return 2
        if not dry_run and confirm != CONFIRM_CREATE:
            print(f"Refusing to write without --confirm {CONFIRM_CREATE}. Use --dry-run first.")
            return 2
        if not root.exists():
            actions.append(f"mkdir {root}")
            if not dry_run:
                root.mkdir(parents=True, exist_ok=True)
        for item in ignored:
            actions.append(f"ignore runtime directory {item}")
        copy_traversable_tree(assets_root() / "kb-skeleton", root, actions, dry_run)
        ensure_skeleton_dirs(root, actions, dry_run)
        copy_traversable_tree(assets_root() / "schema", root / "schema", actions, dry_run)
        copy_traversable_tree(assets_root() / "tools", root / "tools", actions, dry_run)
        copy_traversable_tree(assets_root() / "skills", root / CANONICAL_SKILL_ROOT, actions, dry_run)
    elif not dry_run and confirm != CONFIRM_CREATE:
        print(f"Refusing to adopt existing KB without --confirm {CONFIRM_CREATE}. Use --dry-run first.")
        return 2

    copy_traversable_tree(assets_root() / "templates", root / ".agents" / "templates", actions, dry_run)
    write_text(root / "llm-wiki.yaml", expected_manifest_text(platforms), actions, dry_run)
    if not dry_run:
        sync_actions: list[str] = []
        for platform in platforms:
            sync_one_platform(root, platform, sync_actions, check=False)
        actions.extend(sync_actions)

    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"[{mode}] init {root}")
    for action in actions:
        print(f"- {action}")
    return 0
