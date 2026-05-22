from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def load_synthesize_helper():
    module_path = Path(__file__).resolve().parents[1] / "src" / "assets" / "skills" / "synthesize" / "scripts" / "kb_synthesize_helper.py"
    spec = importlib.util.spec_from_file_location("test_kb_synthesize_helper", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load synthesize helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SynthesizeHelperTests(unittest.TestCase):
    def test_match_license_reuse_and_generate_outputs(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_theme = "themes/project/00-new-crm"
            self._write(root / target_theme / "README.md", "# New CRM\n")
            self._write(
                root / target_theme / "outputs" / "requirement-analysis.md",
                "# Requirement Analysis\n\n"
                "| ID | Type | Requirement | Priority | Confidence | Evidence | Related modules/entities |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| REQ-001 | functional | Search customer leads with reusable search module. | high | confirmed | source | search, leads |\n",
            )
            self._write(root / "themes/project/01-history/README.md", "# History\n")
            self._write(
                root / "themes/project/01-history/wiki/modules/search.md",
                "# Search Module\n\nReusable search module for customer leads and filters.\n",
            )
            self._write(
                root / "themes/project/01-history/outputs/reuse-candidates.md",
                "# Reuse Candidates\n\n"
                "| Asset | Source | Reuse level | Reuse cost | Best fit | Key risk |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| search module | wiki/modules/search.md | adapt | medium | lead search | coupling review |\n",
            )
            self._write(
                root / "themes/project/02-open/README.md",
                "# Open Source Search\n",
            )
            self._write(
                root / "themes/project/02-open/outputs/document-intake/project-reverse-analysis.json",
                """{
                  "repo": {"name": "oss-search", "remote_url": "https://github.com/example/oss-search"},
                  "license_type": "GPL-3.0",
                  "license_signals": {"primary_license": "GPL-3.0", "normalized_licenses": ["GPL-3.0"], "license_risk": "review_required"},
                  "community_health": {"status": "available", "health_score": 2},
                  "known_vulnerabilities": "unavailable",
                  "vulnerability_signals": {"status": "unavailable"},
                  "reuse_assessment": [
                    {"module": "search module", "score": 5, "recommendation": "extractable with review"}
                  ]
                }""",
            )
            self._write(root / "index/technical-assets.md", "# Technical Assets\n")

            matches = helper.match_assets(root, target_theme, top=10, search_mode="keyword")
            self.assertGreaterEqual(matches["requirement_count"], 1)
            self.assertTrue(any(item["candidate_kind"] == "historical_project_page" for item in matches["matches"]))

            license_checks = helper.check_license(root, target_theme, top=10, search_mode="keyword")
            self.assertTrue(any(item["license_status"] == "incompatible_risk" for item in license_checks["checks"]))

            reuse = helper.assess_reuse(root, target_theme, top=10, search_mode="keyword")
            self.assertTrue(any(item["reuse_cost"] == "high" for item in reuse["assessments"]))

            outputs = helper.generate_outputs(root, target_theme, top=10, search_mode="keyword")
            output_paths = {item["path"] for item in outputs["proposed_changes"]}
            self.assertIn(f"{target_theme}/outputs/asset-match-brief.md", output_paths)
            self.assertIn(f"{target_theme}/outputs/engineering-brief.md", output_paths)
            self.assertTrue(any(path.startswith("shared/assets/") for path in output_paths))
            self.assertIn("themes/project/01-history/README.md", output_paths)
            self.assertIn("wikilink_validation", outputs)
            output_by_path = {item["path"]: item["content"] for item in outputs["proposed_changes"]}
            self.assertIn("## Technical Options", output_by_path[f"{target_theme}/outputs/engineering-brief.md"])
            self.assertIn("## Constraints", output_by_path[f"{target_theme}/outputs/engineering-brief.md"])
            self.assertIn("## Recommended Next Actions", output_by_path[f"{target_theme}/outputs/engineering-brief.md"])
            self.assertIn("## Module Boundaries", output_by_path[f"{target_theme}/outputs/implementation-guide.md"])
            self.assertIn("## Interfaces And Data Flow", output_by_path[f"{target_theme}/outputs/implementation-guide.md"])
            self.assertIn("## Rollout Notes", output_by_path[f"{target_theme}/outputs/implementation-guide.md"])

            applied = helper.apply_generated_outputs(root, outputs, confirm="WRITE-KB")
            self.assertEqual(applied["status"], "ok")
            self.assertTrue((root / target_theme / "outputs" / "asset-match-brief.md").exists())
            self.assertIn("[[shared/assets/", (root / "themes/project/01-history/README.md").read_text(encoding="utf-8"))
            self.assertTrue((root / "log.md").exists())

    def test_multi_route_match_assets_adds_search_signals_without_graph_query_writes(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_theme = "themes/project/00-new-crm"
            history_theme = "themes/project/01-history"
            self._write(root / target_theme / "README.md", "# New CRM\n")
            self._write(
                root / target_theme / "outputs" / "requirement-analysis.md",
                "# Requirement Analysis\n\n"
                "| ID | Type | Requirement | Priority | Confidence | Evidence | Related modules/entities |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| REQ-001 | functional | Search customer leads with reusable search module. | high | confirmed | source | search, leads |\n",
            )
            history_page = root / history_theme / "wiki" / "modules" / "search.md"
            self._write(history_page, "# Search Module\n\nCustomer lead search filters and ranking.\n")
            self._write(
                root / "shared" / "assets" / "lead-import-adapter.md",
                "---\n"
                "title: Lead Import Adapter\n"
                "node_type: asset\n"
                "status: active\n"
                "tech_stack:\n"
                "  - leads\n"
                "reuse_level: adapt\n"
                "reuse_cost: medium\n"
                "---\n\n"
                "# Lead Import Adapter\n\nStructured import adapter.\n",
            )
            self._write(
                root / history_theme / "outputs" / "document-intake" / "graphify" / "graph.json",
                '{"nodes":[{"id":"wiki/modules/search.md","label":"lead search graph node"}],"edges":[]}',
            )

            original_bm25 = helper.run_bm25_search
            original_search_bm25 = helper._search.run_bm25_search
            helper.run_bm25_search = lambda _root, _requirement, top: {  # type: ignore[assignment]
                "status": "available",
                "paths": [f"{history_theme}/wiki/modules/search.md"],
                "exit_code": 0,
            }
            try:
                matches = helper.match_assets(root, target_theme, top=10, search_mode="multi")
            finally:
                helper.run_bm25_search = original_bm25  # type: ignore[assignment]

            self.assertEqual(matches["search_diagnostics"]["routes"]["bm25"]["status"], "available")
            self.assertIs(helper._search.run_bm25_search, original_search_bm25)
            self.assertEqual(matches["search_diagnostics"]["routes"]["frontmatter"]["status"], "available")
            self.assertEqual(matches["search_diagnostics"]["routes"]["graph"]["status"], "available")
            by_ref = {item["candidate_ref"]: item for item in matches["matches"]}
            self.assertIn(f"{history_theme}/wiki/modules/search.md", by_ref)
            self.assertIn("bm25", by_ref[f"{history_theme}/wiki/modules/search.md"]["search_signals"])
            self.assertIn("graph", by_ref[f"{history_theme}/wiki/modules/search.md"]["search_signals"])
            self.assertIn("frontmatter", by_ref["shared/assets/lead-import-adapter.md"]["search_signals"])
            self.assertFalse((root / history_theme / "outputs" / "document-intake" / "graphify" / "queries").exists())

    def test_multi_route_unavailable_bridges_do_not_block_keyword_matches(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_theme = "themes/project/00-new-crm"
            self._write(root / target_theme / "README.md", "# New CRM\n")
            self._write(
                root / target_theme / "outputs" / "requirement-analysis.md",
                "# Requirement Analysis\n\n"
                "| ID | Type | Requirement | Priority | Confidence | Evidence | Related modules/entities |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| REQ-001 | functional | Search customer leads. | high | confirmed | source | search |\n",
            )
            self._write(root / "themes/project/01-history/wiki/modules/search.md", "# Search\n\nSearch customer leads.\n")
            original_bm25 = helper.run_bm25_search
            helper.run_bm25_search = lambda _root, _requirement, top: {"status": "unavailable", "error": "qmd missing", "paths": []}  # type: ignore[assignment]
            try:
                matches = helper.match_assets(root, target_theme, top=10, search_mode="multi")
            finally:
                helper.run_bm25_search = original_bm25  # type: ignore[assignment]

            self.assertTrue(matches["matches"])
            self.assertEqual(matches["search_diagnostics"]["routes"]["bm25"]["status"], "unavailable")
            self.assertEqual(matches["search_diagnostics"]["routes"]["graph"]["status"], "unavailable")
            self.assertTrue(any("keyword" in item["search_signals"] for item in matches["matches"]))

    def test_search_module_accepts_bm25_function_parameter(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_theme = "themes/project/00-new-crm"
            history_theme = "themes/project/01-history"
            self._write(root / target_theme / "README.md", "# New CRM\n")
            self._write(
                root / target_theme / "outputs" / "requirement-analysis.md",
                "# Requirement Analysis\n\n"
                "| ID | Type | Requirement | Priority | Confidence | Evidence | Related modules/entities |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| REQ-001 | functional | Search customer leads. | high | confirmed | source | search |\n",
            )
            self._write(root / history_theme / "wiki/modules/search.md", "# Search\n\nSearch customer leads.\n")

            matches = helper._search.match_assets(
                root,
                target_theme,
                top=10,
                search_mode="multi",
                bm25_search_fn=lambda _root, _requirement: {"status": "available", "paths": [f"{history_theme}/wiki/modules/search.md"], "exit_code": 0},
            )

            by_ref = {item["candidate_ref"]: item for item in matches["matches"]}
            self.assertIn("bm25", by_ref[f"{history_theme}/wiki/modules/search.md"]["search_signals"])

    def test_match_assets_handles_empty_requirements(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_theme = "themes/project/00-empty"
            self._write(root / target_theme / "README.md", "# Empty\n")
            matches = helper.match_assets(root, target_theme, search_mode="multi")
            self.assertEqual(matches["requirement_count"], 0)
            self.assertEqual(matches["matches"], [])
            self.assertEqual(matches["search_diagnostics"]["routes"]["bm25"]["status"], "skipped")

    def test_collect_synthesis_context_missing_theme_raises(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                helper.collect_synthesis_context(Path(tmp), "themes/project/missing")

    def test_apply_generated_outputs_requires_confirmation(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {"target_theme": "themes/project/00-demo", "proposed_changes": [{"path": "outputs/demo.md", "content": "# Demo\n"}]}
            result = helper.apply_generated_outputs(root, payload, confirm="")
            self.assertEqual(result["status"], "needs_confirmation")
            self.assertFalse((root / "outputs" / "demo.md").exists())

    def test_apply_generated_outputs_uses_temp_replace(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {"target_theme": "themes/project/00-demo", "proposed_changes": [{"path": "outputs/demo.md", "content": "# Demo\n"}]}

            result = helper.apply_generated_outputs(root, payload, confirm="WRITE-KB")

            self.assertEqual(result["status"], "ok")
            self.assertEqual((root / "outputs" / "demo.md").read_text(encoding="utf-8"), "# Demo\n")
            self.assertEqual(list((root / "outputs").glob("*.tmp")), [])

    def test_apply_generated_outputs_reports_replace_failure(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {"target_theme": "themes/project/00-demo", "proposed_changes": [{"path": "outputs/demo.md", "content": "# Demo\n"}]}

            with mock.patch.object(Path, "replace", side_effect=OSError("replace boom")):
                result = helper.apply_generated_outputs(root, payload, confirm="WRITE-KB")

            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["applied"], [])
            self.assertTrue(result["denied"][0]["error"].startswith("replace failed:"))
            self.assertFalse((root / "outputs" / "demo.md").exists())

    def test_safe_write_path_blocks_only_real_sources_dirs(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            allowed = helper.safe_write_path(root, "themes/project/01-sources-app/outputs/asset-match-brief.md")
            self.assertIsNotNone(allowed)
            self.assertTrue(str(allowed).endswith("01-sources-app\\outputs\\asset-match-brief.md") or str(allowed).endswith("01-sources-app/outputs/asset-match-brief.md"))

            self.assertIsNone(helper.safe_write_path(root, "sources/raw.md"))
            self.assertIsNone(helper.safe_write_path(root, "themes/project/01-app/sources/raw.md"))

    def test_bm25_unavailable_cache_expires_and_retries(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "tools" / "kb_search_bridge.py"
            self._write(script, "# bridge\n")
            root_key = str(root.resolve())
            calls = {"count": 0}

            class Result:
                def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = stderr

            try:
                helper.clear_bm25_unavailable_cache()

                def fake_run(*_args, **_kwargs):
                    calls["count"] += 1
                    if calls["count"] == 1:
                        return Result(2, "{}", "qmd missing")
                    return Result(0, '{"results":[{"path":"shared/assets/search.md"}]}')

                with mock.patch.object(helper.subprocess, "run", side_effect=fake_run):
                    first = helper.run_bm25_search(root, {"id": "REQ-001", "text": "search"}, top=5)
                    second = helper.run_bm25_search(root, {"id": "REQ-001", "text": "search"}, top=5)

                    with helper.BM25_UNAVAILABLE_LOCK:
                        helper.BM25_UNAVAILABLE_ROOTS[root_key] = helper.time.monotonic() - helper.BM25_UNAVAILABLE_TTL_SECONDS - 1
                    third = helper.run_bm25_search(root, {"id": "REQ-001", "text": "search"}, top=5)
            finally:
                helper.clear_bm25_unavailable_cache()

            self.assertEqual(first["status"], "unavailable")
            self.assertEqual(second["status"], "unavailable")
            self.assertEqual(third["status"], "available")
            self.assertEqual(third["paths"], ["shared/assets/search.md"])
            self.assertEqual(calls["count"], 2)

    def test_bm25_unavailable_cache_prunes_to_max_roots(self) -> None:
        helper = load_synthesize_helper()
        try:
            helper.clear_bm25_unavailable_cache()
            for idx in range(helper.BM25_UNAVAILABLE_MAX_ROOTS + 5):
                helper.cache_bm25_unavailable(f"root-{idx:03d}")
            with helper.BM25_UNAVAILABLE_LOCK:
                self.assertLessEqual(len(helper.BM25_UNAVAILABLE_ROOTS), helper.BM25_UNAVAILABLE_MAX_ROOTS)
                self.assertNotIn("root-000", helper.BM25_UNAVAILABLE_ROOTS)
        finally:
            helper.clear_bm25_unavailable_cache()

    def test_frontmatter_enrichment_does_not_mutate_candidate(self) -> None:
        helper = load_synthesize_helper()
        candidate = {"kind": "shared_asset", "path": "shared/assets/search.md", "title": "Search"}

        enriched = helper.enrich_candidate_with_frontmatter(candidate, {"reuse_level": "direct", "reuse_cost": "low", "license": "MIT"})

        self.assertNotIn("reuse_level", candidate)
        self.assertEqual(enriched["reuse_level"], "direct")
        self.assertEqual(enriched["reuse_cost"], "low")
        self.assertEqual(enriched["license_type"], "MIT")

    def test_bm25_low_rank_uses_lower_floor(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_theme = "themes/project/00-new-crm"
            history_theme = "themes/project/01-history"
            self._write(root / target_theme / "README.md", "# New CRM\n")
            self._write(
                root / target_theme / "outputs" / "requirement-analysis.md",
                "# Requirement Analysis\n\n"
                "| ID | Type | Requirement | Priority | Confidence | Evidence | Related modules/entities |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| REQ-001 | functional | Customer portal. | high | confirmed | source | portal |\n",
            )
            paths = []
            for idx in range(20):
                rel = f"{history_theme}/wiki/modules/module-{idx:02d}.md"
                paths.append(rel)
                self._write(root / rel, f"# Module {idx:02d}\n\nUnrelated evidence.\n")

            matches = helper._search.match_assets(
                root,
                target_theme,
                top=20,
                search_mode="multi",
                bm25_search_fn=lambda _root, _requirement: {"status": "available", "paths": paths, "exit_code": 0},
            )

            by_ref = {item["candidate_ref"]: item for item in matches["matches"]}
            self.assertEqual(by_ref[paths[-1]]["search_signals"]["bm25"]["score"], 0.1)

    def test_invalid_graph_artifact_is_reported_without_blocking(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_theme = "themes/project/00-new-crm"
            history_theme = "themes/project/01-history"
            self._write(root / target_theme / "README.md", "# New CRM\n")
            self._write(
                root / target_theme / "outputs" / "requirement-analysis.md",
                "# Requirement Analysis\n\n"
                "| ID | Type | Requirement | Priority | Confidence | Evidence | Related modules/entities |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| REQ-001 | functional | Search customer leads. | high | confirmed | source | search |\n",
            )
            self._write(root / "themes/project/02-other/wiki/search.md", "# Search\n\nSearch customer leads.\n")
            self._write(root / history_theme / "outputs/document-intake/graphify/graph.json", '{"nodes": [')
            original_bm25 = helper.run_bm25_search
            helper.run_bm25_search = lambda _root, _requirement, top: {"status": "unavailable", "paths": [], "error": "qmd missing"}  # type: ignore[assignment]
            try:
                matches = helper.match_assets(root, target_theme, search_mode="multi")
            finally:
                helper.run_bm25_search = original_bm25  # type: ignore[assignment]

            graph_diag = matches["search_diagnostics"]["routes"]["graph"]
            self.assertEqual(graph_diag["status"], "unavailable")
            self.assertTrue(graph_diag["errors"])
            self.assertTrue(matches["matches"])

    def test_reuse_candidate_column_variants_are_mapped_consistently(self) -> None:
        helper = load_synthesize_helper()
        candidates = helper.build_candidate_inventory(
            {
                "reuse_candidates": [
                    {
                        "path": "themes/project/01-history/outputs/reuse-candidates.md",
                        "theme": ("themes", "project", "01-history"),
                        "rows": [{"module": "Search Module", "reuse_mode": "direct", "effort": "low"}],
                    }
                ]
            }
        )
        self.assertEqual(candidates[0]["title"], "Search Module")
        self.assertEqual(candidates[0]["reuse_level"], "direct")
        self.assertEqual(candidates[0]["reuse_cost"], "low")

    def test_promotion_candidates_ignore_empty_theme_refs(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assessment = {
                "promotion_candidate": True,
                "candidate_title": "Search Module",
                "candidate_ref": "themes/project/01-history/wiki/modules/search.md",
                "source_theme": "",
                "evidence_paths": ["themes/project/01-history/wiki/modules/search.md"],
                "requirement_id": "REQ-001",
            }

            self.assertEqual(helper.detect_promotion_candidates(root, "themes/project/00-new", [assessment]), [])

            assessment["source_theme"] = "themes/project/01-history"
            candidates = helper.detect_promotion_candidates(root, "themes/project/00-new", [assessment])
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["themes"], ["themes/project/00-new", "themes/project/01-history"])

    def test_facade_exports_and_cli_subcommands_work_after_split(self) -> None:
        helper = load_synthesize_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_theme = "themes/project/00-new-crm"
            self._write(root / target_theme / "README.md", "# New CRM\n")
            self._write(
                root / target_theme / "outputs" / "requirement-analysis.md",
                "# Requirement Analysis\n\n"
                "| ID | Type | Requirement | Priority | Confidence | Evidence | Related modules/entities |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| REQ-001 | functional | Search customer leads. | high | confirmed | source | search |\n",
            )
            self._write(root / "themes/project/01-history/wiki/modules/search.md", "# Search\n\nSearch customer leads.\n")

            self.assertTrue(callable(helper.match_assets))
            self.assertTrue(callable(helper.generate_outputs))

            script = Path(__file__).resolve().parents[1] / "src" / "assets" / "skills" / "synthesize" / "scripts" / "kb_synthesize_helper.py"
            for command in ("match-assets", "check-license", "assess-reuse", "generate-outputs"):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        command,
                        "--root",
                        str(root),
                        "--target-theme",
                        target_theme,
                        "--search-mode",
                        "keyword",
                        "--format",
                        "json",
                    ],
                    check=False,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["target_theme"], target_theme)

    def test_license_status_extended_terms(self) -> None:
        helper = load_synthesize_helper()
        self.assertEqual(helper.license_status_for("GPL-3.0"), "incompatible_risk")
        self.assertEqual(helper.license_status_for("Elastic License 2.0"), "incompatible_risk")
        self.assertEqual(helper.license_status_for("BSL-1.1"), "incompatible_risk")
        self.assertEqual(helper.license_status_for(None), "unknown")
        self.assertEqual(helper.license_status_for("MIT"), "compatible")
        self.assertEqual(helper.license_status_for("Apache-2.0"), "compatible")
        self.assertEqual(helper.license_status_for("BSD-3-Clause"), "compatible")
        self.assertEqual(helper.license_status_for("Conda Terms of Service"), "review_required")
        self.assertEqual(helper.license_status_for("permit required"), "review_required")
        self.assertEqual(helper.license_status_for("obsidian notes"), "review_required")
        self.assertEqual(helper.license_status_for("MIT and GPL-3.0"), "incompatible_risk")

    def test_known_vulnerabilities_unavailable_is_lookup_risk_not_known_vuln(self) -> None:
        helper = load_synthesize_helper()
        risks = helper.reuse_risks(
            {"known_vulnerabilities": "unavailable", "vulnerability_signals": {"status": "unavailable"}, "match_score": 0.8},
            {"license_status": "compatible"},
            "medium",
        )
        self.assertIn("vulnerability_lookup_unavailable", risks)
        self.assertNotIn("known_vulnerabilities_present", risks)

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
