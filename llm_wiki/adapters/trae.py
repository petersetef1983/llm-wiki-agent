from __future__ import annotations

from pathlib import Path

from .base import PlatformAdapter


class TraeAdapter(PlatformAdapter):
    name = "trae"
    instruction_file = Path(".trae/rules/project_rules.md")
    skill_root = Path(".trae/skills")
    template_name = "trae-project-rules.md.j2"
