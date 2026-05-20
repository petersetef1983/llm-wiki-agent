from __future__ import annotations

import json
from pathlib import Path

from .base import PlatformAdapter, RenderContext


class OpenClawAdapter(PlatformAdapter):
    name = "openclaw"
    instruction_file = Path(".openclaw/instructions.md")
    skill_root = Path(".openclaw/skills")
    template_name = "openclaw-instructions.md.j2"
    mcp_server_name = "llm-wiki"

    def generated_config_files(self, context: RenderContext) -> dict[Path, str]:
        plugin = {
            "name": "llm-wiki-agent",
            "generated_by": "llm-wiki-agent",
            "generated_notice": context.generated_notice,
            "instructions": self.instruction_file.as_posix(),
            "skill_root": self.skill_root.as_posix(),
            "mcpServers": {
                self.mcp_server_name: {
                    "command": "llm-wiki",
                    "args": ["serve", "--root", ".", "--transport", "stdio"],
                }
            },
        }
        mcp_yaml = "\n".join(
            [
                f"# {context.generated_notice}",
                "mcp_servers:",
                f"  {self.mcp_server_name}:",
                "    command: llm-wiki",
                "    args:",
                "      - serve",
                "      - --root",
                "      - .",
                "      - --transport",
                "      - stdio",
                f"instructions: {self.instruction_file.as_posix()}",
                f"skill_root: {self.skill_root.as_posix()}",
                "",
            ]
        )
        return {
            Path(".openclaw/openclaw.plugin.json"): json.dumps(plugin, ensure_ascii=True, indent=2) + "\n",
            Path(".openclaw/mcp.yaml"): mcp_yaml,
        }

    def generated_file_paths(self) -> tuple[Path, ...]:
        return (Path(".openclaw/openclaw.plugin.json"), Path(".openclaw/mcp.yaml"))
