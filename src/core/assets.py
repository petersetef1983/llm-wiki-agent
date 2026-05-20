from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class TreeDiff:
    missing: list[str]
    changed: list[str]
    extra: list[str]

    @property
    def has_upgrade_diffs(self) -> bool:
        return bool(self.missing or self.changed)

    @property
    def has_any_diffs(self) -> bool:
        return bool(self.missing or self.changed or self.extra)


def assets_root() -> resources.abc.Traversable:
    return resources.files("src") / "assets"


def should_skip_asset(rel: Path) -> bool:
    return "__pycache__" in rel.parts or rel.suffix == ".pyc"


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_tree(root: Path) -> dict[str, str]:
    items: dict[str, str] = {}
    if not root.exists():
        return items
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or should_skip_asset(rel) or rel.as_posix() == ".mirror-state.json":
            continue
        items[rel.as_posix()] = file_digest(path)
    return items


def diff_trees(source: Path, target: Path) -> TreeDiff:
    source_state = snapshot_tree(source)
    target_state = snapshot_tree(target)
    missing: list[str] = []
    changed: list[str] = []
    extra: list[str] = []
    for key in sorted(set(source_state) | set(target_state)):
        source_hash = source_state.get(key)
        target_hash = target_state.get(key)
        if source_hash is None:
            extra.append(key)
        elif target_hash is None:
            missing.append(key)
        elif source_hash != target_hash:
            changed.append(key)
    return TreeDiff(missing=missing, changed=changed, extra=extra)


def copy_traversable_tree(src: resources.abc.Traversable, dst: Path, actions: list[str], dry_run: bool) -> None:
    if not src.is_dir():
        raise FileNotFoundError(f"asset directory not found: {src}")
    for item in sorted(src.iterdir(), key=lambda p: p.name):
        if should_skip_asset(Path(item.name)):
            continue
        target = dst / item.name
        if item.is_dir():
            if not target.exists():
                actions.append(f"mkdir {target}")
            if not dry_run:
                target.mkdir(parents=True, exist_ok=True)
            copy_traversable_tree(item, target, actions, dry_run)
            continue
        actions.append(f"write {target}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())


def copy_filesystem_tree(src: Path, dst: Path, actions: list[str], dry_run: bool) -> None:
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if should_skip_asset(rel):
            continue
        target = dst / rel
        if path.is_dir():
            if not target.exists():
                actions.append(f"mkdir {target}")
            if not dry_run:
                target.mkdir(parents=True, exist_ok=True)
            continue
        actions.append(f"write {target}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def write_text(path: Path, text: str, actions: list[str], dry_run: bool) -> None:
    actions.append(f"write {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
