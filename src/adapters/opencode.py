from __future__ import annotations

import json
from pathlib import Path

from ..core.manifest import CANONICAL_SKILL_ROOT

from .base import PlatformAdapter, RenderContext


class OpenCodeAdapter(PlatformAdapter):
    name = "opencode"
    instruction_file = Path(".opencode/instructions.md")
    skill_root = Path(".opencode/skills")
    instruction_skill_root = CANONICAL_SKILL_ROOT
    template_name = "opencode-instructions.md.j2"
    mcp_server_name = "llm-wiki"

    def generated_config_files(self, context: RenderContext) -> dict[Path, str]:
        payload = {
            "$schema": "https://opencode.ai/config.json",
            "generated_by": "llm-wiki-agent",
            "generated_notice": context.generated_notice,
            "instructions": [self.instruction_file.as_posix()],
            "mcp": {
                self.mcp_server_name: {
                    "type": "local",
                    "command": ["llm-wiki", "serve", "--root", ".", "--transport", "stdio"],
                    "enabled": True,
                }
            },
        }
        return {Path("opencode.json"): json.dumps(payload, ensure_ascii=True, indent=2) + "\n"}

    def generated_file_paths(self) -> tuple[Path, ...]:
        return (Path("opencode.json"),)
