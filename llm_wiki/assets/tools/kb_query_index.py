#!/usr/bin/env python3
"""Build and query a lightweight frontmatter index for the LLM Wiki."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on local environment
    yaml = None


INDEX_REL = Path(".query-index/frontmatter.json")
IGNORED_DIRS = {
    ".agents",
    ".claude",
    ".codex",
    ".hermes",
    ".obsidian",
    ".openclaw",
    ".opencode",
    ".qmd",
    ".query-index",
    ".data-sources",
    "inbox",
}


def parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS, help="Knowledge-base root. Defaults to current directory.")
    common.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(description="Build and query a frontmatter JSON index.")
    parser.add_argument("--root", default=".", help="Knowledge-base root. Defaults to current directory.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_cmd = subparsers.add_parser("index", parents=[common], help="Build the frontmatter index.")
    index_cmd.add_argument("--output", default=INDEX_REL.as_posix(), help="Index path relative to root.")

    filter_cmd = subparsers.add_parser("filter", parents=[common], help="Filter pages by frontmatter fields.")
    filter_cmd.add_argument("--index", default=INDEX_REL.as_posix(), help="Index path relative to root.")
    filter_cmd.add_argument("--node-type")
    filter_cmd.add_argument("--reuse-level")
    filter_cmd.add_argument("--reuse-cost")
    filter_cmd.add_argument("--confidence")
    filter_cmd.add_argument("--tech-stack")
    filter_cmd.add_argument("--theme")
    filter_cmd.add_argument("--license")
    filter_cmd.add_argument("--status")
    filter_cmd.add_argument("--field", action="append", default=[], help="Arbitrary field filter as key=value. Repeatable.")

    aggregate_cmd = subparsers.add_parser("aggregate", parents=[common], help="Aggregate indexed pages by a frontmatter field.")
    aggregate_cmd.add_argument("--index", default=INDEX_REL.as_posix(), help="Index path relative to root.")
    aggregate_cmd.add_argument("--by", required=True, help="Field name to aggregate by, for example themes.")

    return parser.parse_args()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def should_index(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    parts = set(rel.parts)
    if parts & IGNORED_DIRS:
        return False
    rel_text = rel.as_posix()
    if rel_text.startswith("schema/templates/"):
        return False
    if "/sources/" in f"/{rel_text}/" or "/outputs/document-intake/" in f"/{rel_text}/":
        return False
    return path.suffix.lower() == ".md"


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"", "null", "None", "~"}:
        return None
    if value == "[]":
        return []
    if value in {"true", "false"}:
        return value == "true"
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def parse_block(lines: list[str]) -> Any:
    if not lines:
        return []
    if all(line.strip().startswith("- ") for line in lines if line.strip()):
        return [parse_scalar(line.strip()[2:]) for line in lines if line.strip()]

    result: dict[str, Any] = {}
    current_key: str | None = None
    for line in lines:
        if not line.strip():
            continue
        nested_match = re.match(r"^\s{2}([A-Za-z0-9_-]+):\s*(.*)$", line)
        if nested_match:
            current_key = nested_match.group(1)
            value = nested_match.group(2).strip()
            result[current_key] = [] if value in {"", "[]"} else parse_scalar(value)
            continue
        item_match = re.match(r"^\s{4}-\s*(.*)$", line)
        if item_match and current_key:
            result.setdefault(current_key, [])
            if isinstance(result[current_key], list):
                result[current_key].append(parse_scalar(item_match.group(1)))
            continue
        prop_match = re.match(r"^\s{6}([A-Za-z0-9_-]+):\s*(.*)$", line)
        if prop_match and current_key and isinstance(result.get(current_key), list) and result[current_key]:
            last = result[current_key][-1]
            if not isinstance(last, dict):
                last = {"value": last}
                result[current_key][-1] = last
            last[prop_match.group(1)] = parse_scalar(prop_match.group(2))
    return result


def normalize_yaml_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_yaml_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_yaml_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def parse_frontmatter_lines(frontmatter_lines: list[str]) -> dict[str, Any]:
    if yaml is not None:
        try:
            loaded = yaml.safe_load("\n".join(frontmatter_lines)) or {}
            if isinstance(loaded, dict):
                return normalize_yaml_value(loaded)
        except Exception:
            pass

    parsed: dict[str, Any] = {}
    idx = 0
    while idx < len(frontmatter_lines):
        line = frontmatter_lines[idx]
        if not line.strip():
            idx += 1
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not match:
            idx += 1
            continue
        key = match.group(1)
        value = match.group(2).strip()
        idx += 1
        block: list[str] = []
        while idx < len(frontmatter_lines) and not re.match(r"^[A-Za-z0-9_-]+:\s*", frontmatter_lines[idx]):
            block.append(frontmatter_lines[idx])
            idx += 1
        parsed[key] = parse_block(block) if value == "" else parse_scalar(value)
    return parsed


def extract_frontmatter(content: str) -> dict[str, Any] | None:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return None

    return parse_frontmatter_lines(lines[1:end])


def flatten_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(flatten_values(item))
        return values
    if isinstance(value, dict):
        values = []
        for item in value.values():
            values.extend(flatten_values(item))
        return values
    return [str(value)]


def field_matches(frontmatter: dict[str, Any], field: str, expected: str) -> bool:
    values = [value.lower() for value in flatten_values(frontmatter.get(field))]
    expected_lower = expected.lower()
    return any(expected_lower == value or expected_lower in value for value in values)


def build_index(root: Path) -> dict[str, Any]:
    entries = []
    for path in sorted(root.rglob("*.md"), key=lambda item: item.relative_to(root).as_posix().lower()):
        if not should_index(path, root):
            continue
        frontmatter = extract_frontmatter(read_text(path))
        if frontmatter is None:
            continue
        stat = path.stat()
        rel = path.relative_to(root).as_posix()
        entries.append(
            {
                "path": rel,
                "title": frontmatter.get("title") or path.stem,
                "node_type": frontmatter.get("node_type"),
                "frontmatter": frontmatter,
                "mtime": stat.st_mtime,
                "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
            }
        )
    return {
        "schema_version": "kb-frontmatter-index.v1",
        "root": str(root),
        "frontmatter_parser": "pyyaml+fallback" if yaml is not None else "builtin",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entry_count": len(entries),
        "entries": entries,
    }


def load_index(root: Path, index_arg: str) -> dict[str, Any]:
    index_path = Path(index_arg)
    if not index_path.is_absolute():
        index_path = root / index_path
    if not index_path.exists():
        return build_index(root)
    return json.loads(read_text(index_path))


def apply_filters(entries: list[dict[str, Any]], filters: dict[str, str]) -> list[dict[str, Any]]:
    result = []
    for entry in entries:
        frontmatter = entry.get("frontmatter") or {}
        if all(field_matches(frontmatter, key, value) for key, value in filters.items() if value):
            result.append(entry)
    return result


def print_entries(entries: list[dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps({"count": len(entries), "entries": entries}, ensure_ascii=False, indent=2))
        return
    print(f"matches={len(entries)}")
    for entry in entries:
        fm = entry.get("frontmatter") or {}
        details = []
        for key in ["node_type", "reuse_level", "reuse_cost", "confidence", "status"]:
            if fm.get(key):
                details.append(f"{key}={fm[key]}")
        suffix = f" ({', '.join(details)})" if details else ""
        print(f"- {entry['path']} - {entry.get('title')}{suffix}")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    if args.command == "index":
        payload = build_index(root)
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.format == "json":
            print(json.dumps({"index_path": str(output), **payload}, ensure_ascii=False, indent=2))
        else:
            print(f"Wrote frontmatter index to {output}")
            print(f"entries={payload['entry_count']}")
        return 0

    payload = load_index(root, getattr(args, "index", INDEX_REL.as_posix()))
    entries = payload.get("entries", [])

    if args.command == "filter":
        filters = {
            "node_type": args.node_type,
            "reuse_level": args.reuse_level,
            "reuse_cost": args.reuse_cost,
            "confidence": args.confidence,
            "tech_stack": args.tech_stack,
            "themes": args.theme,
            "license_compatibility": args.license,
            "status": args.status,
        }
        for item in args.field:
            if "=" not in item:
                raise SystemExit(f"--field must be key=value, got: {item}")
            key, value = item.split("=", 1)
            filters[key.strip()] = value.strip()
        print_entries(apply_filters(entries, filters), args.format)
        return 0

    if args.command == "aggregate":
        groups: dict[str, list[str]] = defaultdict(list)
        for entry in entries:
            values = flatten_values((entry.get("frontmatter") or {}).get(args.by))
            for value in values or ["[missing]"]:
                groups[str(value)].append(entry["path"])
        result = {
            "field": args.by,
            "groups": [
                {"value": key, "count": len(paths), "sample_paths": paths[:10]}
                for key, paths in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
            ],
        }
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            for group in result["groups"]:
                print(f"{group['value']}: {group['count']}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
