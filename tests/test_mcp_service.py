from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.mcp.service import CONFIRM_WRITE, LLMWikiService


class LLMWikiServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel in ["themes/general/demo", "shared", "schema", ".agents/skills", "index", "inbox/to-be-filed"]:
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        (self.root / "AGENTS.md").write_text("agent instructions\n", encoding="utf-8")
        (self.root / "index" / "home.md").write_text("# Home\n", encoding="utf-8")
        (self.root / "llm-wiki.yaml").write_text(
            '\n'.join(
                [
                    'kit_version: "0.1.0"',
                    'schema_version: "0.1.0"',
                    'skills_version: "0.1.0"',
                    'created_at: "2026-05-20T00:00:00+00:00"',
                    "platforms:",
                    "  codex:",
                    "    enabled: true",
                    "    instruction_file: AGENTS.md",
                    "    skill_root: .agents/skills",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "themes" / "general" / "demo" / "asset.md").write_text(
            '\n'.join(
                [
                    "---",
                    "title: Demo Asset",
                    "node_type: asset",
                    "themes:",
                    "  - themes/general/demo",
                    "status: active",
                    "---",
                    "",
                    "# Demo Asset",
                    "",
                    "Body",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.service = LLMWikiService(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_read_page_blocks_runtime_and_traversal(self) -> None:
        self.assertEqual(self.service.read_page("../AGENTS.md")["status"], "denied")
        self.assertEqual(self.service.read_page(".agents/skills/private.md")["status"], "denied")
        self.assertEqual(self.service.read_page(".opencode/instructions.md")["status"], "denied")
        self.assertEqual(self.service.read_page("themes/general/demo/asset.md")["status"], "ok")

    def test_list_filter_and_aggregate_pages(self) -> None:
        listed = self.service.list_pages(node_type="asset")
        self.assertEqual(listed["count"], 1)
        filtered = self.service.filter_pages(filters={"status": "active"})
        self.assertEqual(filtered["count"], 1)
        aggregate = self.service.aggregate(field="node_type")
        self.assertEqual(aggregate["groups"][0]["value"], "asset")

    def test_write_tools_require_confirmation(self) -> None:
        before_log = self.root / "log.md"
        result = self.service.record_query(question="What changed?")
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertFalse(before_log.exists())

        ok = self.service.record_query(question="What changed?", confirm=CONFIRM_WRITE)
        self.assertEqual(ok["status"], "ok")
        self.assertTrue(before_log.exists())

        blocked = self.service.create_inbox_note(title="Draft", content="Body")
        self.assertEqual(blocked["status"], "needs_confirmation")
        created = self.service.create_inbox_note(title="Draft", content="Body", confirm=CONFIRM_WRITE)
        self.assertEqual(created["status"], "ok")
        self.assertTrue((self.root / created["path"]).exists())

    def test_readonly_disables_writes(self) -> None:
        readonly = LLMWikiService(self.root, readonly=True)
        result = readonly.create_inbox_note(title="Draft", content="Body", confirm=CONFIRM_WRITE)
        self.assertEqual(result["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
