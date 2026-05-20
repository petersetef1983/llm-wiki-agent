from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from llm_wiki.core.bootstrap import CONFIRM_CREATE, init_kb
from llm_wiki.core.manifest import SUPPORTED_PLATFORMS, parse_platforms
from llm_wiki.core.mirror import sync_platforms
from llm_wiki.core.upgrade import CONFIRM_UPGRADE, upgrade_kb


PLATFORMS = list(SUPPORTED_PLATFORMS)


class BootstrapMirrorUpgradeTests(unittest.TestCase):
    def test_init_rejects_ordinary_non_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "note.txt").write_text("block\n", encoding="utf-8")
            self.assertEqual(
                init_kb(root, platforms=PLATFORMS, dry_run=True, confirm="", adopt_existing=False),
                2,
            )

    def test_init_allows_runtime_only_directory_and_writes_platform_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / ".codex" / "cache"
            runtime.mkdir(parents=True)
            (runtime / "state.tmp").write_text("runtime\n", encoding="utf-8")

            self.assertEqual(
                init_kb(root, platforms=PLATFORMS, dry_run=False, confirm=CONFIRM_CREATE, adopt_existing=False),
                0,
            )
            for rel in [
                "AGENTS.md",
                "CLAUDE.md",
                ".trae/rules/project_rules.md",
                ".opencode/instructions.md",
                ".openclaw/instructions.md",
                ".hermes/instructions.md",
                "opencode.json",
                ".openclaw/openclaw.plugin.json",
                ".openclaw/mcp.yaml",
                ".hermes/config.yaml",
                ".agents/skills/query/SKILL.md",
                ".codex/skills/query/SKILL.md",
                ".claude/skills/query/SKILL.md",
                ".trae/skills/query/SKILL.md",
                ".opencode/skills/query/SKILL.md",
                ".openclaw/skills/query/SKILL.md",
                ".hermes/skills/query/SKILL.md",
                "qmd.yml",
            ]:
                self.assertTrue((root / rel).exists(), rel)
            self.assertIn('      - ".trae/**"', (root / "qmd.yml").read_text(encoding="utf-8"))
            self.assertIn('      - ".opencode/**"', (root / "qmd.yml").read_text(encoding="utf-8"))
            self.assertIn('      - ".openclaw/**"', (root / "qmd.yml").read_text(encoding="utf-8"))
            self.assertIn('      - ".hermes/**"', (root / "qmd.yml").read_text(encoding="utf-8"))
            self.assertFalse((root / ".agents/skills/bootstrap/assets/skeleton/AGENTS.md").exists())

    def test_init_can_select_only_opencode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(
                init_kb(
                    root,
                    platforms=parse_platforms("opencode"),
                    dry_run=False,
                    confirm=CONFIRM_CREATE,
                    adopt_existing=False,
                ),
                0,
            )
            self.assertTrue((root / ".opencode/instructions.md").exists())
            self.assertTrue((root / "opencode.json").exists())
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertFalse((root / ".trae/rules/project_rules.md").exists())

    def test_sync_check_reports_and_repairs_skill_mirror_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_temp_kb(Path(tmp))
            source_skill = root / ".agents" / "skills" / "query" / "SKILL.md"
            source_skill.write_text(source_skill.read_text(encoding="utf-8") + "\nlocal drift\n", encoding="utf-8")

            self.assertEqual(sync_platforms(root, platforms=PLATFORMS, check=True), 1)
            self.assertEqual(sync_platforms(root, platforms=PLATFORMS, check=False), 0)
            self.assertEqual(sync_platforms(root, platforms=PLATFORMS, check=True), 0)

    def test_upgrade_cleans_legacy_skeleton_and_preserves_user_knowledge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_temp_kb(Path(tmp))
            legacy = root / ".agents" / "skills" / "bootstrap" / "assets" / "skeleton" / "AGENTS.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("# Old AGENTS.md\n", encoding="utf-8")
            sentinel = root / "shared" / "sentinel.md"
            sentinel.write_text("user knowledge\n", encoding="utf-8")
            qmd = root / "qmd.yml"
            qmd.write_text(
                qmd.read_text(encoding="utf-8")
                .replace('      - ".trae/**"\n', "")
                .replace('      - ".opencode/**"\n', "")
                .replace('      - ".openclaw/**"\n', "")
                .replace('      - ".hermes/**"\n', ""),
                encoding="utf-8",
            )

            dry_output = self._capture(lambda: upgrade_kb(root, dry_run=True, confirm="", force_conflicts=False))
            self.assertIn("remove deprecated generated asset .agents/skills/bootstrap/assets/skeleton", dry_output)
            self.assertTrue(legacy.exists())

            self.assertEqual(upgrade_kb(root, dry_run=False, confirm=CONFIRM_UPGRADE, force_conflicts=True), 0)
            self.assertFalse(legacy.exists())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "user knowledge\n")
            self.assertIn('      - ".trae/**"', qmd.read_text(encoding="utf-8"))
            self.assertIn('      - ".opencode/**"', qmd.read_text(encoding="utf-8"))
            self.assertIn('      - ".openclaw/**"', qmd.read_text(encoding="utf-8"))
            self.assertIn('      - ".hermes/**"', qmd.read_text(encoding="utf-8"))

    def test_upgrade_blocks_user_modified_skills_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_temp_kb(Path(tmp))
            source_skill = root / ".agents" / "skills" / "query" / "SKILL.md"
            original = source_skill.read_text(encoding="utf-8")
            source_skill.write_text(original + "\nuser edit\n", encoding="utf-8")

            self.assertEqual(upgrade_kb(root, dry_run=False, confirm=CONFIRM_UPGRADE, force_conflicts=False), 1)
            self.assertIn("user edit", source_skill.read_text(encoding="utf-8"))

    def _init_temp_kb(self, root: Path) -> Path:
        code = init_kb(
            root,
            platforms=parse_platforms("all"),
            dry_run=False,
            confirm=CONFIRM_CREATE,
            adopt_existing=False,
        )
        self.assertEqual(code, 0)
        return root

    def _capture(self, fn) -> str:  # type: ignore[no-untyped-def]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            fn()
        return out.getvalue()


if __name__ == "__main__":
    unittest.main()
