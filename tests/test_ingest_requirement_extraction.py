from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def load_ingest_documents():
    scripts_dir = Path(__file__).resolve().parents[1] / "src" / "assets" / "skills" / "ingest" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    module_path = scripts_dir / "kb_ingest_documents.py"
    spec = importlib.util.spec_from_file_location("test_kb_ingest_documents", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load ingest documents helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RequirementExtractionTests(unittest.TestCase):
    def test_requirement_document_draft_has_ids_confidence_and_evidence(self) -> None:
        docs = load_ingest_documents()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "inbox" / "requirements" / "crm-prd.md"
            source.parent.mkdir(parents=True)
            source.write_text(
                "# CRM PRD\n\n"
                "## Functional Requirements\n\n"
                "- Must import customer leads from CSV.\n\n"
                "## Non-Functional Constraints\n\n"
                "- Import 100k rows within 5 minutes.\n\n"
                "## Acceptance Criteria\n\n"
                "- Given a valid CSV, the user sees imported leads.\n",
                encoding="utf-8",
            )

            payload = docs.extract_requirement_document(source, root=root, target_theme="themes/project/00-crm")
            self.assertEqual(payload["artifact_kind"], "requirement-analysis")
            markdown = payload["markdown"]
            self.assertIn("REQ-001", markdown)
            self.assertIn("NFR-001", markdown)
            self.assertIn("AC-001", markdown)
            self.assertIn("Confidence", markdown)
            self.assertIn("inbox/requirements/crm-prd.md#L", markdown)

    def test_numbered_mixed_language_headings_are_classified(self) -> None:
        docs = load_ingest_documents()
        payload = docs.infer_requirement_items(
            "# PRD\n\n"
            "1. 功能需求\n\n"
            "- 必须支持客户检索。\n\n"
            "2. 非功能性需求\n\n"
            "- 查询延迟必须低于 500ms。\n\n"
            "3) Technical Constraints\n\n"
            "- Must integrate with the existing index service.\n\n"
            "4. Acceptance Criteria\n\n"
            "- Given a query, the user sees matching customers.\n",
            source_ref="inbox/requirements/numbered.md",
        )
        self.assertEqual(payload["functional"][0]["id"], "REQ-001")
        self.assertEqual(payload["non_functional"][0]["id"], "NFR-001")
        self.assertEqual(payload["technical"][0]["id"], "TECH-001")
        self.assertEqual(payload["acceptance"][0]["id"], "AC-001")

    def test_extract_document_cli_accepts_requirement_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "prd.md"
            output = root / "requirement-analysis.md"
            source.write_text("# PRD\n\n## Functional Requirements\n\n- Must search historical projects.\n", encoding="utf-8")
            script = Path(__file__).resolve().parents[1] / "src" / "assets" / "skills" / "ingest" / "scripts" / "kb_ingest_cli.py"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--root",
                    str(root),
                    "extract-document",
                    "--type",
                    "requirement",
                    "--target-theme",
                    "themes/project/00-product",
                    "--input",
                    str(source),
                    "--output",
                    str(output),
                    "--format",
                    "markdown",
                ],
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            content = output.read_text(encoding="utf-8")
            self.assertIn("# Requirement Analysis", content)
            self.assertIn("REQ-001", content)
            self.assertIn("confidence", content.lower())


if __name__ == "__main__":
    unittest.main()
