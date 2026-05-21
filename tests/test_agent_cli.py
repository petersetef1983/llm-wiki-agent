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
from src.agent import AgentRequest, CommandProvider, CONFIRM_WRITE, build_ingest_request, parse_agent_response
from src.agent.context import _load_ingest_core
from src.core.bootstrap import CONFIRM_CREATE, init_kb
from src.core.manifest import parse_platforms


class AgentCliTests(unittest.TestCase):
    def test_parser_exposes_agent_commands(self) -> None:
        parser = build_parser()
        self.assertEqual(parser.parse_args(["query", "hello"]).command, "query")
        self.assertEqual(parser.parse_args(["ingest", "note.md"]).command, "ingest")
        self.assertEqual(parser.parse_args(["ingest", "note.md", "--type", "requirement"]).type, "requirement")
        ingest = parser.parse_args(["ingest", "note.md", "--open-source", "--community-health", "--vulnerabilities"])
        self.assertTrue(ingest.open_source)
        self.assertTrue(ingest.community_health)
        self.assertTrue(ingest.vulnerabilities)
        self.assertEqual(parser.parse_args(["lint"]).command, "lint")
        self.assertEqual(parser.parse_args(["init", "--target", "kb", "--dry-run"]).command, "init")

    def test_build_ingest_request_includes_git_analysis_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_kb(Path(tmp) / "kb")
            request = build_ingest_request(
                root,
                "https://github.com/example/repo",
                git_analysis_options={
                    "open_source": True,
                    "community_health": True,
                    "vulnerabilities": True,
                },
            )
            self.assertEqual(
                request.task["git_analysis_options"],
                {
                    "open_source": True,
                    "community_health": True,
                    "vulnerabilities": True,
                },
            )

    def test_build_ingest_request_exposes_generate_output_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_kb(Path(tmp) / "kb")
            request = build_ingest_request(root, "requirements.md", ingest_type="requirement")
            generate_outputs = request.context["generate_outputs"]
            self.assertTrue(generate_outputs["enabled"])
            self.assertIn("asset-match-brief.md", generate_outputs["guide"])
            self.assertEqual(request.context["output_templates"], generate_outputs["templates"])

            templates = {item["path"]: item["content"] for item in generate_outputs["templates"]}
            self.assertIn("outputs/engineering-brief.md", templates)
            self.assertIn("## Candidate Assets", templates["outputs/engineering-brief.md"])
            self.assertIn("outputs/implementation-guide.md", templates)
            self.assertIn("## Reuse And Adaptation Plan", templates["outputs/implementation-guide.md"])
            self.assertIn("outputs/asset-match-brief.md", templates)
            self.assertIn("## Candidate Matches", templates["outputs/asset-match-brief.md"])
            self.assertIn("outputs/requirement-analysis.md", templates)

    def test_project_theme_scaffold_writes_asset_match_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_kb(Path(tmp) / "kb")
            core = _load_ingest_core(root)
            payload = core.create_theme(root, "project", "Task4 Demo")
            brief_path = root / payload["relative_path"] / "outputs" / "asset-match-brief.md"
            self.assertTrue(brief_path.exists())
            content = brief_path.read_text(encoding="utf-8")
            self.assertIn("# Asset Match Brief", content)
            self.assertIn("## Candidate Matches", content)

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

    def test_ingest_requirement_type_writes_requirement_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_kb(Path(tmp) / "kb")
            source = root / "inbox" / "to-be-filed" / "requirements.md"
            source.write_text("# PRD\n\n- Need alert rules.\n", encoding="utf-8")
            command = self._fake_agent_command(Path(tmp))
            target = root / "outputs" / "requirement-analysis.md"

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
            self.assertEqual(payload["response"]["writeback_target"], "outputs/requirement-analysis.md")
            self.assertTrue(target.exists())
            self.assertIn("Functional Requirements", target.read_text(encoding="utf-8"))

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
                    source_type = payload.get("task", {}).get("source_type", "auto")
                    if source_type == "requirement":
                        response = {
                            "answer": "Prepared requirement ingest plan.",
                            "answer_status": "inferred",
                            "sources": [payload["task"]["source"]],
                            "gaps": [],
                            "writeback_candidate": "yes",
                            "writeback_target": "outputs/requirement-analysis.md",
                            "proposed_changes": [
                                {
                                    "path": "outputs/requirement-analysis.md",
                                    "action": "write",
                                    "content": "# Requirement Analysis\\n\\n## Functional Requirements\\n\\n- ID: REQ-001\\n- Requirement: Example requirement\\n- Priority: high\\n",
                                    "rationale": "Fake provider requirement fixture.",
                                    "confidence": "tentative",
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
