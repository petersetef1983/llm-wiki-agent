from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from llm_wiki import __version__


SUPPORTED_PLATFORMS = ("codex", "claude", "trae", "opencode", "openclaw", "hermes")
METADATA_FILE = "llm-wiki.yaml"
CANONICAL_SKILL_ROOT = Path(".agents/skills")
KB_REQUIRED_PATHS = (
    "themes",
    "shared",
    "schema",
    ".agents/skills",
)


def parse_platforms(value: str | Iterable[str]) -> list[str]:
    if isinstance(value, str):
        raw = [item.strip().lower() for item in value.split(",") if item.strip()]
    else:
        raw = [item.strip().lower() for item in value if item.strip()]
    if not raw or raw == ["all"]:
        return list(SUPPORTED_PLATFORMS)
    unknown = sorted(set(raw) - set(SUPPORTED_PLATFORMS))
    if unknown:
        raise ValueError(f"unsupported platform(s): {', '.join(unknown)}")
    return list(dict.fromkeys(raw))


def is_existing_kb_root(root: Path) -> bool:
    return all((root / rel).exists() for rel in KB_REQUIRED_PATHS)


def metadata_path(root: Path) -> Path:
    return root / METADATA_FILE


def expected_manifest_text(platforms: list[str], *, created_at: str | None = None) -> str:
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    lines = [
        f'kit_version: "{__version__}"',
        f'schema_version: "{__version__}"',
        f'skills_version: "{__version__}"',
        f'created_at: "{timestamp}"',
        "platforms:",
    ]
    from llm_wiki.adapters import get_adapter

    for platform in platforms:
        adapter = get_adapter(platform)
        lines.extend(
            [
                f"  {platform}:",
                "    enabled: true",
                f"    instruction_file: {adapter.instruction_file.as_posix()}",
                f"    skill_root: {adapter.manifest_skill_root().as_posix()}",
            ]
        )
        generated_files = adapter.generated_file_paths()
        if generated_files:
            lines.append("    generated_files:")
            lines.extend(f"      - {path.as_posix()}" for path in generated_files)
        if adapter.mcp_server_name:
            lines.append(f"    mcp_server: {adapter.mcp_server_name}")
    return "\n".join(lines) + "\n"


def read_manifest_text(root: Path) -> str:
    path = metadata_path(root)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def validate_manifest(root: Path, platforms: list[str]) -> list[str]:
    text = read_manifest_text(root)
    if not text:
        return [f"missing {METADATA_FILE}"]
    issues: list[str] = []
    required_lines = [
        f'kit_version: "{__version__}"',
        f'schema_version: "{__version__}"',
        f'skills_version: "{__version__}"',
    ]
    for line in required_lines:
        if line not in text:
            issues.append(f"{METADATA_FILE}: missing or stale `{line}`")
    from llm_wiki.adapters import get_adapter

    for platform in platforms:
        if f"  {platform}:" not in text:
            issues.append(f"{METADATA_FILE}: missing platform `{platform}`")
            continue
        adapter = get_adapter(platform)
        expected_lines = [
            f"instruction_file: {adapter.instruction_file.as_posix()}",
            f"skill_root: {adapter.manifest_skill_root().as_posix()}",
        ]
        expected_lines.extend(f"- {path.as_posix()}" for path in adapter.generated_file_paths())
        if adapter.mcp_server_name:
            expected_lines.append(f"mcp_server: {adapter.mcp_server_name}")
        for expected in expected_lines:
            if expected not in text:
                issues.append(f"{METADATA_FILE}: platform `{platform}` missing `{expected}`")
    return issues
