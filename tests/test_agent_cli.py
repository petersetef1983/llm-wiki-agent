from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from src.cli import build_parser, main
from src.agent import AgentRequest, CommandProvider, CONFIRM_WRITE, parse_agent_response
from src.core.bootstrap import CONFIRM_CREATE, init_kb
from src.core.manifest import parse_platforms


class AgentCliTests(unittest.TestCase):
    def test_parser_exposes_agent_commands(self) -> None:
        parser = build_parser()
        self.assertEqual(parser.parse_args(["query", "hello"]).command, "query")
        self.assertEqual(parser.parse_args(["ingest", "note.md"]).command, "ingest")
        ingest_args = parser.parse_args(["ingest", "prd.md", "--type", "requirement", "--target-theme", "themes/project/00-product", "--open-source"])
        self.assertEqual(ingest_args.type, "requirement")
        self.assertEqual(ingest_args.target_theme, "themes/project/00-product")
        self.assertTrue(ingest_args.open_source)
        synthesize_args = parser.parse_args(["synthesize", "--target-theme", "themes/project/00-product", "--search-mode", "keyword"])
        self.assertEqual(synthesize_args.command, "synthesize")
        self.assertEqual(synthesize_args.search_mode, "keyword")
        self.assertEqual(parser.parse_args(["lint"]).command, "lint")
        self.assertEqual(parser.parse_args(["init", "--target", "kb", "--dry-run"]).command, "init")

    def test_parse_agent_response_normalizes_schema(self) -> None:
        response = parse_agent_response(
            json.dumps(
                {
                    "answer": "Done",
                    "answer_status": "confirmed",
                    "sources": ["index/home.md"],
                    "gaps": ["output_gap"],
                    "writeback_candidate": True,
                    "proposed_changes": [{"path": "index/home.md", "content": "# Home"}],
                }
            ),
            provider="fake",
        )
        self.assertEqual(response.answer_status, "confirmed")
        self.assertEqual(response.writeback_candidate, "yes")
        self.assertEqual(response.proposed_changes[0].path, "index/home.md")

    def test_command_provider_receives_request_and_returns_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = self._fake_agent_command(Path(tmp))
            provider = CommandProvider(command)
            request = AgentRequest(
                operation="query",
                root=Path(tmp),
                task={"question": "What is here?"},
                instructions="Return JSON.",
                context={"pages": []},
            )
            response = provider.complete(request)
            self.assertEqual(response.answer_status, "confirmed")
            self.assertIn("query", response.answer.lower())

    def test_query_records_with_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_kb(Path(tmp) / "kb")
            command = self._fake_agent_command(Path(tmp))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "query",
                        "What changed?",
                        "--root",
                        str(root),
                        "--provider",
                        "command",
                        "--agent-command",
                        command,
                        "--record",
                        "--confirm",
                        CONFIRM_WRITE,
                        "--format",
                        "json",
                    ]
                )
            self.assertEqual(code, 0, output.getvalue())
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["record"]["status"], "ok")
            self.assertTrue((root / "log.md").exists())

    def test_ingest_dry_run_and_confirmed_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_kb(Path(tmp) / "kb")
            source = root / "inbox" / "to-be-filed" / "source.md"
            source.write_text("# Source\n\nNew fact.\n", encoding="utf-8")
            command = self._fake_agent_command(Path(tmp))
            target = root / "inbox" / "to-be-filed" / "agent-ingested.md"

            dry_output = io.StringIO()
            with contextlib.redirect_stdout(dry_output):
                dry_code = main(
                    [
                        "ingest",
                        str(source),
                        "--root",
                        str(root),
                        "--provider",
                        "command",
                        "--agent-command",
                        command,
                        "--format",
                        "json",
                    ]
                )
            self.assertEqual(dry_code, 0, dry_output.getvalue())
            self.assertFalse(target.exists())

            apply_output = io.StringIO()
            with contextlib.redirect_stdout(apply_output):
                apply_code = main(
                    [
                        "ingest",
                        str(source),
                        "--root",
                        str(root),
                        "--provider",
                        "command",
                        "--agent-command",
                        command,
                        "--confirm",
                        CONFIRM_WRITE,
                        "--format",
                        "json",
                    ]
                )
            self.assertEqual(apply_code, 0, apply_output.getvalue())
            self.assertTrue(target.exists())
            self.assertIn("New ingested note", target.read_text(encoding="utf-8"))

    def test_requirement_ingest_writes_theme_local_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_kb(Path(tmp) / "kb")
            source = root / "inbox" / "requirements" / "prd.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# PRD\n\n## Functional Requirements\n\n- 用户可以检索历史项目。\n", encoding="utf-8")
            command = self._fake_agent_command(Path(tmp))
            target_theme = "themes/project/00-product"
            target = root / target_theme / "outputs" / "requirement-analysis.md"

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "ingest",
                        str(source),
                        "--root",
                        str(root),
                        "--type",
                        "requirement",
                        "--target-theme",
                        target_theme,
                        "--provider",
                        "command",
                        "--agent-command",
                        command,
                        "--confirm",
                        CONFIRM_WRITE,
                        "--format",
                        "json",
                    ]
                )
            self.assertEqual(code, 0, output.getvalue())
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["type"], "requirement")
            self.assertTrue(target.exists())
            content = target.read_text(encoding="utf-8")
            self.assertIn("REQ-001", content)
            self.assertIn("confidence", content.lower())

    def test_synthesize_dry_run_and_confirmed_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_kb(Path(tmp) / "kb")
            target_theme = "themes/project/00-product"
            theme_dir = root / target_theme
            (theme_dir / "outputs").mkdir(parents=True, exist_ok=True)
            (theme_dir / "README.md").write_text("# Product\n", encoding="utf-8")
            (theme_dir / "outputs" / "requirement-analysis.md").write_text(
                "# Requirement Analysis\n\n| ID | Type | Requirement | Priority | Confidence | Evidence | Related modules/entities |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| REQ-001 | functional | Reuse historical search. | high | confirmed | source | search |\n",
                encoding="utf-8",
            )
            command = self._fake_agent_command(Path(tmp))
            target = theme_dir / "outputs" / "asset-match-brief.md"

            dry_output = io.StringIO()
            with contextlib.redirect_stdout(dry_output):
                dry_code = main(
                    [
                        "synthesize",
                        "--root",
                        str(root),
                        "--target-theme",
                        target_theme,
                        "--search-mode",
                        "keyword",
                        "--provider",
                        "command",
                        "--agent-command",
                        command,
                        "--format",
                        "json",
                    ]
                )
            self.assertEqual(dry_code, 0, dry_output.getvalue())
            self.assertFalse(target.exists())

            apply_output = io.StringIO()
            with contextlib.redirect_stdout(apply_output):
                apply_code = main(
                    [
                        "synthesize",
                        "--root",
                        str(root),
                        "--target-theme",
                        target_theme,
                        "--search-mode",
                        "keyword",
                        "--provider",
                        "command",
                        "--agent-command",
                        command,
                        "--confirm",
                        CONFIRM_WRITE,
                        "--format",
                        "json",
                    ]
                )
            self.assertEqual(apply_code, 0, apply_output.getvalue())
            self.assertTrue(target.exists())
            self.assertIn("Candidate Matches", target.read_text(encoding="utf-8"))

    def test_lint_fix_plan_is_dry_run_without_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_kb(Path(tmp) / "kb")
            command = self._fake_agent_command(Path(tmp))
            target = root / "index" / "agent-lint-note.md"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "lint",
                        "--root",
                        str(root),
                        "--fix-plan",
                        "--provider",
                        "command",
                        "--agent-command",
                        command,
                        "--format",
                        "json",
                    ]
                )
            self.assertIn(code, {0, 1}, output.getvalue())
            payload = json.loads(output.getvalue())
            self.assertIn("response", payload)
            self.assertFalse(target.exists())

    def _init_kb(self, root: Path) -> Path:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = init_kb(
                root,
                platforms=parse_platforms("codex"),
                dry_run=False,
                confirm=CONFIRM_CREATE,
                adopt_existing=False,
            )
        self.assertEqual(code, 0, out.getvalue())
        return root

    def _fake_agent_command(self, directory: Path) -> str:
        script = directory / "fake_agent.py"
        script.write_text(
            textwrap.dedent(
                """
                import json
                import sys

                payload = json.load(sys.stdin)
                operation = payload["operation"]
                if operation == "ingest":
                    source_type = payload["task"].get("source_type")
                    if source_type == "requirement":
                        target_path = "outputs/requirement-analysis.md"
                        for template in payload["context"].get("output_templates", []):
                            if template["path"].endswith("requirement-analysis.md"):
                                target_path = template["path"]
                                break
                        response = {
                            "answer": "Prepared requirement analysis.",
                            "answer_status": "inferred",
                            "sources": [payload["task"]["source"]],
                            "gaps": [],
                            "writeback_candidate": "yes",
                            "proposed_changes": [
                                {
                                    "path": target_path,
                                    "action": "write",
                                    "content": "# Requirement Analysis\\n\\n## Requirement Items\\n\\n| ID | Type | Requirement | Priority | Confidence | Evidence | Related modules/entities |\\n| --- | --- | --- | --- | --- | --- | --- |\\n| REQ-001 | functional | 用户可以检索历史项目。 | high | confirmed | source | search |\\n",
                                    "rationale": "Fake requirement ingest.",
                                    "confidence": "inferred",
                                }
                            ],
                        }
                    else:
                        response = {
                            "answer": "Prepared ingest plan.",
                            "answer_status": "inferred",
                            "sources": [payload["task"]["source"]],
                            "gaps": [],
                            "writeback_candidate": "yes",
                            "proposed_changes": [
                                {
                                    "path": "inbox/to-be-filed/agent-ingested.md",
                                    "action": "write",
                                    "content": "# New ingested note\\n\\nSource-backed draft.\\n",
                                    "rationale": "Fake provider test fixture.",
                                    "confidence": "tentative",
                                }
                            ],
                        }
                elif operation == "synthesize":
                    target_path = f"{payload['task']['target_theme']}/outputs/asset-match-brief.md"
                    for template in payload["context"].get("output_templates", []):
                        if template["path"].endswith("asset-match-brief.md"):
                            target_path = template["path"]
                            break
                    response = {
                        "answer": "Prepared synthesis outputs.",
                        "answer_status": "inferred",
                        "sources": [target_path],
                        "gaps": [],
                        "writeback_candidate": "yes",
                        "proposed_changes": [
                            {
                                "path": target_path,
                                "action": "write",
                                "content": "# Asset Match Brief\\n\\n## Candidate Matches\\n\\n| Requirement ID | Candidate asset | Reuse level | Reuse cost | License status | Validation task |\\n| --- | --- | --- | --- | --- | --- |\\n| REQ-001 | shared search pattern | adapt | medium | review_required | build spike |\\n",
                                "rationale": "Fake synthesis test fixture.",
                                "confidence": "inferred",
                            }
                        ],
                    }
                elif operation == "lint":
                    response = {
                        "answer": "Lint findings triaged.",
                        "answer_status": "inferred",
                        "sources": [],
                        "gaps": [],
                        "writeback_candidate": "no",
                        "proposed_changes": [
                            {
                                "path": "index/agent-lint-note.md",
                                "action": "write",
                                "content": "# Lint Note\\n",
                                "rationale": "Fake provider test fixture.",
                                "confidence": "tentative",
                            }
                        ],
                    }
                else:
                    response = {
                        "answer": "Query answered from fake provider.",
                        "answer_status": "confirmed",
                        "sources": ["index/home.md"],
                        "gaps": [],
                        "writeback_candidate": "no",
                    }
                print(json.dumps(response))
                """
            ).lstrip(),
            encoding="utf-8",
        )
        return subprocess.list2cmdline([sys.executable, str(script)])


if __name__ == "__main__":
    unittest.main()
