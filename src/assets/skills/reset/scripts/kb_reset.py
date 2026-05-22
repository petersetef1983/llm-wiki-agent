#!/usr/bin/env python3
"""Reset an LLM Wiki repository to its empty skeleton."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


CONFIRM_TOKEN = "RESET-KB"
THEME_CATEGORIES = ("general", "project", "research")
SHARED_CATEGORIES = ("entities", "concepts", "patterns", "methods", "tools", "glossary")
INBOX_DIRS = (
    "to-be-filed",
    "review",
    "requirements",
    "papers",
    "articles",
    "images",
    "videos",
    "audio",
    "source-code",
)
INDEX_FILES = {
    "home.md": """# Knowledge Base Home

## Summary
This LLM Wiki has been reset to an empty skeleton.

## Entry Points
- `themes/`
- `shared/`
- `inbox/`
- `index/`
- `schema/`

## Recommended Flow
1. Add raw materials to `inbox/` or a theme `sources/` directory.
2. Use `ingest` to compile durable wiki content.
3. Use `query` for grounded answers.
4. Use `lint` to check structure and graph health.
""",
    "themes.md": """# Themes Index

## General Themes

No themes yet.

## Project Themes

No themes yet.

## Research Themes

No themes yet.
""",
    "recent-updates.md": """# Recent Updates

No updates yet.
""",
    "cross-theme-map.md": """# Cross-Theme Map

No cross-theme relationships yet.
""",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def is_kb_root(root: Path) -> bool:
    required_dirs = [root / "themes", root / "shared", root / "schema", root / ".agents" / "skills"]
    return all(path.exists() for path in required_dirs)


def ensure_within_root(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Refusing to touch path outside root: {resolved}") from exc
    return resolved


def remove_path(path: Path, *, dry_run: bool, actions: list[str]) -> None:
    if not path.exists():
        return
    actions.append(f"remove {path}")
    if dry_run:
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def write_file(path: Path, content: str, *, dry_run: bool, actions: list[str]) -> None:
    actions.append(f"write {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def make_dir(path: Path, *, dry_run: bool, actions: list[str]) -> None:
    actions.append(f"mkdir {path}")
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)


def reset_themes(root: Path, *, dry_run: bool, actions: list[str]) -> None:
    themes_root = ensure_within_root(root, root / "themes")
    for category in THEME_CATEGORIES:
        category_dir = ensure_within_root(root, themes_root / category)
        if category_dir.exists():
            for child in sorted(category_dir.iterdir()):
                remove_path(ensure_within_root(root, child), dry_run=dry_run, actions=actions)
        make_dir(category_dir, dry_run=dry_run, actions=actions)

    if themes_root.exists():
        for child in sorted(themes_root.iterdir()):
            if child.name not in THEME_CATEGORIES:
                remove_path(ensure_within_root(root, child), dry_run=dry_run, actions=actions)
    make_dir(themes_root, dry_run=dry_run, actions=actions)


def reset_shared(root: Path, *, dry_run: bool, actions: list[str]) -> None:
    shared_root = ensure_within_root(root, root / "shared")
    if shared_root.exists():
        for child in sorted(shared_root.iterdir()):
            remove_path(ensure_within_root(root, child), dry_run=dry_run, actions=actions)
    make_dir(shared_root, dry_run=dry_run, actions=actions)
    write_file(
        shared_root / "README.md",
        """# Shared Knowledge

Reusable cross-theme knowledge will be rebuilt here.
""",
        dry_run=dry_run,
        actions=actions,
    )
    for category in SHARED_CATEGORIES:
        category_dir = shared_root / category
        make_dir(category_dir, dry_run=dry_run, actions=actions)
        write_file(
            category_dir / "README.md",
            f"""# {category.replace('-', ' ').title()}

No entries yet.
""",
            dry_run=dry_run,
            actions=actions,
        )


def reset_index(root: Path, *, dry_run: bool, actions: list[str]) -> None:
    index_root = ensure_within_root(root, root / "index")
    if index_root.exists():
        for child in sorted(index_root.iterdir()):
            remove_path(ensure_within_root(root, child), dry_run=dry_run, actions=actions)
    make_dir(index_root, dry_run=dry_run, actions=actions)
    for filename, content in INDEX_FILES.items():
        write_file(index_root / filename, content, dry_run=dry_run, actions=actions)


def reset_inbox(root: Path, *, dry_run: bool, actions: list[str]) -> None:
    inbox_root = ensure_within_root(root, root / "inbox")
    if inbox_root.exists():
        for child in sorted(inbox_root.iterdir()):
            remove_path(ensure_within_root(root, child), dry_run=dry_run, actions=actions)
    for rel in INBOX_DIRS:
        make_dir(ensure_within_root(root, inbox_root / rel), dry_run=dry_run, actions=actions)


def reset_logs(root: Path, *, dry_run: bool, actions: list[str]) -> None:
    remove_path(ensure_within_root(root, root / "log.md"), dry_run=dry_run, actions=actions)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Knowledge-base root. Defaults to current directory.")
    parser.add_argument("--dry-run", action="store_true", help="Print the reset plan without changing files.")
    parser.add_argument(
        "--confirm",
        default="",
        help=f"Required destructive confirmation token: {CONFIRM_TOKEN}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    dry_run = args.dry_run

    if not is_kb_root(root):
        print(f"Refusing to reset because this does not look like an LLM Wiki root: {root}", file=sys.stderr)
        return 2
    if not dry_run and args.confirm != CONFIRM_TOKEN:
        print(f"Refusing to reset without --confirm {CONFIRM_TOKEN}. Use --dry-run first.", file=sys.stderr)
        return 2

    actions: list[str] = []
    reset_themes(root, dry_run=dry_run, actions=actions)
    reset_shared(root, dry_run=dry_run, actions=actions)
    reset_index(root, dry_run=dry_run, actions=actions)
    reset_inbox(root, dry_run=dry_run, actions=actions)
    reset_logs(root, dry_run=dry_run, actions=actions)

    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"[{mode}] Reset plan for {root}")
    for action in actions:
        print(f"- {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
