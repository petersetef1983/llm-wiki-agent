from __future__ import annotations

from pathlib import Path

from .base import PlatformAdapter, RenderContext


class HermesAdapter(PlatformAdapter):
    name = "hermes"
    instruction_file = Path(".hermes/instructions.md")
    skill_root = Path(".hermes/skills")
    template_name = "hermes-instructions.md.j2"
    mcp_server_name = "llm-wiki"

    def generated_config_files(self, context: RenderContext) -> dict[Path, str]:
        config = "\n".join(
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
                "instructions:",
                f"  - {self.instruction_file.as_posix()}",
                f"skill_root: {self.skill_root.as_posix()}",
                "",
            ]
        )
        return {Path(".hermes/config.yaml"): config}

    def generated_file_paths(self) -> tuple[Path, ...]:
        return (Path(".hermes/config.yaml"),)
