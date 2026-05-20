from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from llm_wiki.core.manifest import CANONICAL_SKILL_ROOT


@dataclass(frozen=True)
class RenderContext:
    core_contract: str
    generated_notice: str


class PlatformAdapter:
    name: str
    instruction_file: Path
    skill_root: Path
    instruction_skill_root: Path | None = None
    template_name: str
    mirror_skills: bool = True
    mcp_server_name: str | None = None

    def render_vars(self, context: RenderContext) -> dict[str, str]:
        instruction_skill_root = self.instruction_skill_root or self.skill_root
        return {
            "GENERATED_NOTICE": context.generated_notice,
            "CORE_CONTRACT": context.core_contract,
            "SKILL_ROOT": instruction_skill_root.as_posix(),
            "CANONICAL_SKILL_ROOT": CANONICAL_SKILL_ROOT.as_posix(),
            "MCP_SERVER_NAME": self.mcp_server_name or "",
        }

    def manifest_skill_root(self) -> Path:
        return self.instruction_skill_root or self.skill_root

    def generated_config_files(self, context: RenderContext) -> dict[Path, str]:
        return {}

    def generated_file_paths(self) -> tuple[Path, ...]:
        return tuple()

    def expected_mirror_state(self) -> dict[str, str]:
        return {
            "generated_from": CANONICAL_SKILL_ROOT.as_posix(),
            "generated_by": "llm-wiki sync",
            "platform": self.name,
        }

    def write_mirror_state(self, root: Path) -> None:
        state_path = root / self.skill_root / ".mirror-state.json"
        payload = {
            **self.expected_mirror_state(),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        state_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    def mirror_state_drift(self, root: Path) -> list[str]:
        state_path = root / self.skill_root / ".mirror-state.json"
        if not state_path.exists():
            return [f"{self.skill_root.as_posix()}/.mirror-state.json"]
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return [f"{self.skill_root.as_posix()}/.mirror-state.json"]
        expected = self.expected_mirror_state()
        return [
            f"{self.skill_root.as_posix()}/.mirror-state.json:{key}"
            for key, value in expected.items()
            if payload.get(key) != value
        ]
