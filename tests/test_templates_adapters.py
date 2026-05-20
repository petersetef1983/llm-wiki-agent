from __future__ import annotations

import unittest

from src.adapters import get_adapter
from src.core.mirror import expected_instruction


class TemplateAdapterTests(unittest.TestCase):
    def test_platform_instruction_titles_are_unique(self) -> None:
        expected_titles = {
            "codex": "# AGENTS.md",
            "claude": "# CLAUDE.md",
            "trae": "# Trae Project Rules",
            "opencode": "# OpenCode Instructions",
            "openclaw": "# OpenClaw Instructions",
            "hermes": "# Hermes Instructions",
        }
        for platform, title in expected_titles.items():
            with self.subTest(platform=platform):
                text = expected_instruction(get_adapter(platform))
                headings = [line for line in text.splitlines() if line.startswith("# ")]
                self.assertEqual(headings, [title])
                self.assertNotIn("{{", text)
                self.assertNotIn("}}", text)

    def test_platform_skill_roots_are_rendered(self) -> None:
        expectations = {
            "codex": ".agents/skills/ingest/SKILL.md",
            "claude": ".claude/skills/ingest/SKILL.md",
            "trae": ".trae/skills/ingest/SKILL.md",
            "opencode": ".agents/skills/ingest/SKILL.md",
            "openclaw": ".openclaw/skills/ingest/SKILL.md",
            "hermes": ".hermes/skills/ingest/SKILL.md",
        }
        for platform, skill_ref in expectations.items():
            with self.subTest(platform=platform):
                text = expected_instruction(get_adapter(platform))
                self.assertIn(skill_ref, text)

    def test_new_platform_config_files_include_mcp_server(self) -> None:
        for platform, expected_files in {
            "opencode": ("opencode.json",),
            "openclaw": (".openclaw/openclaw.plugin.json", ".openclaw/mcp.yaml"),
            "hermes": (".hermes/config.yaml",),
        }.items():
            with self.subTest(platform=platform):
                adapter = get_adapter(platform)
                self.assertEqual(tuple(path.as_posix() for path in adapter.generated_file_paths()), expected_files)


if __name__ == "__main__":
    unittest.main()
