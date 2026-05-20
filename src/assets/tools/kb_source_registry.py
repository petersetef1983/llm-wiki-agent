#!/usr/bin/env python3
"""Manage local source registry metadata for future ingest adapters."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REGISTRY_REL = Path(".data-sources/registry.json")
SOURCE_TYPES = {"git", "document", "im", "meeting", "cicd", "internal-system", "other"}


def parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS, help="Knowledge-base root. Defaults to current directory.")
    common.add_argument("--registry", default=argparse.SUPPRESS, help="Registry path relative to root.")
    common.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(description="Manage the KB source registry.")
    parser.add_argument("--root", default=".", help="Knowledge-base root. Defaults to current directory.")
    parser.add_argument("--registry", default=REGISTRY_REL.as_posix(), help="Registry path relative to root.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", parents=[common], help="Create an empty local source registry if missing.")

    register = subparsers.add_parser("register", parents=[common], help="Register or update a source.")
    register.add_argument("--id", required=True)
    register.add_argument("--type", required=True, choices=sorted(SOURCE_TYPES))
    register.add_argument("--provider", default="generic")
    register.add_argument("--url")
    register.add_argument("--theme")
    register.add_argument("--enabled", choices=["true", "false"], default="false")
    register.add_argument("--description")
    register.add_argument("--metadata", action="append", default=[], help="Additional metadata as key=value. Repeatable.")

    subparsers.add_parser("list", parents=[common], help="List registered sources.")
    subparsers.add_parser("status", parents=[common], help="Summarize registry health.")

    return parser.parse_args()


def registry_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def empty_registry(root: Path) -> dict[str, Any]:
    return {
        "schema_version": "source-registry.v1",
        "root": str(root),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": [],
    }


def read_registry(path: Path, root: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_registry(root)
    return json.loads(path.read_text(encoding="utf-8"))


def write_registry(path: Path, payload: dict[str, Any]) -> None:
    payload["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_metadata(items: list[str]) -> dict[str, str]:
    result = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--metadata must be key=value, got: {item}")
        key, value = item.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def print_payload(payload: Any, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, dict) and isinstance(payload.get("sources"), list):
        print(f"sources={len(payload['sources'])}")
        for source in payload["sources"]:
            print(f"- {source['id']} ({source['type']}, enabled={source.get('enabled', False)})")
    elif isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}={value}")
    else:
        print(payload)


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    path = registry_path(root, args.registry)

    if args.command == "init":
        payload = read_registry(path, root)
        write_registry(path, payload)
        print_payload({"registry": str(path), "source_count": len(payload["sources"])}, args.format)
        return 0

    payload = read_registry(path, root)

    if args.command == "register":
        source = {
            "id": args.id,
            "type": args.type,
            "provider": args.provider,
            "url": args.url,
            "theme": args.theme,
            "enabled": args.enabled == "true",
            "description": args.description,
            "metadata": parse_metadata(args.metadata),
            "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "freshness": "unknown",
        }
        payload["sources"] = [item for item in payload.get("sources", []) if item.get("id") != args.id]
        payload["sources"].append(source)
        payload["sources"].sort(key=lambda item: item["id"])
        write_registry(path, payload)
        print_payload({"registry": str(path), "registered": args.id}, args.format)
        return 0

    if args.command == "list":
        print_payload(payload, args.format)
        return 0

    if args.command == "status":
        sources = payload.get("sources", [])
        result = {
            "registry": str(path),
            "exists": path.exists(),
            "source_count": len(sources),
            "enabled_count": sum(1 for item in sources if item.get("enabled")),
            "types": sorted({str(item.get("type")) for item in sources}),
        }
        print_payload(result, args.format)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
