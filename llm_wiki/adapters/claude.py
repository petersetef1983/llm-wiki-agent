from __future__ import annotations

from pathlib import Path

from .base import PlatformAdapter


class ClaudeAdapter(PlatformAdapter):
    name = "claude"
    instruction_file = Path("CLAUDE.md")
    skill_root = Path(".claude/skills")
    template_name = "CLAUDE.md.j2"
