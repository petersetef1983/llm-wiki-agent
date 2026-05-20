from __future__ import annotations

from pathlib import Path

from llm_wiki.core.manifest import CANONICAL_SKILL_ROOT

from .base import PlatformAdapter


class CodexAdapter(PlatformAdapter):
    name = "codex"
    instruction_file = Path("AGENTS.md")
    skill_root = Path(".codex/skills")
    instruction_skill_root = CANONICAL_SKILL_ROOT
    template_name = "AGENTS.md.j2"
