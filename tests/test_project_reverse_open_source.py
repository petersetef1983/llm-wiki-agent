from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


def load_project_reverse_helper():
    module_path = Path(__file__).resolve().parents[1] / "src" / "assets" / "skills" / "project-reverse" / "scripts" / "project_reverse_helper.py"
    spec = importlib.util.spec_from_file_location("test_project_reverse_helper_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load project reverse helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ProjectReverseOpenSourceTests(unittest.TestCase):
    def test_license_dependency_and_open_source_signals_are_engineering_risks(self) -> None:
        helper = load_project_reverse_helper()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE\n", encoding="utf-8")
            (repo / "package.json").write_text(
                '{"name":"demo","version":"1.0.0","license":"GPL-3.0","dependencies":{"left-pad":"1.3.0"}}',
                encoding="utf-8",
            )
            files = [
                {"path": "LICENSE", "extension": "", "is_binary": False, "size_bytes": 24},
                {"path": "package.json", "extension": "json", "is_binary": False, "size_bytes": 100},
            ]
            stack = helper.collect_stack(repo, files)
            license_signals = helper.collect_license_signals(repo, files, stack)
            dependencies = helper.dependency_inventory(repo, files, stack)
            community = {"status": "available", "commit_count_90d": 0, "contributor_sample_count": 0, "health_score": 0}
            open_source = helper.collect_open_source_signals(
                {"remote_url": "https://github.com/example/demo", "provider": "github"},
                license_signals,
                dependencies,
                community,
                enabled=True,
            )

            self.assertTrue(license_signals["license_review_required"])
            self.assertEqual(license_signals["license_risk"], "review_required")
            self.assertEqual(dependencies[0]["ecosystem"], "npm")
            self.assertEqual(open_source["license_risk"], "review_required")
            self.assertIn("not legal advice", license_signals["engineering_note"].lower())

    def test_vulnerability_lookup_failure_is_unavailable_not_blocking(self) -> None:
        helper = load_project_reverse_helper()
        payload = helper.collect_vulnerability_signals(
            [{"ecosystem": "npm", "name": "left-pad", "version": "1.3.0"}],
            enabled=True,
            api_url="http://127.0.0.1:9/querybatch",
            timeout=1,
        )
        self.assertEqual(payload["status"], "unavailable")
        self.assertFalse(payload["blocking"])
        self.assertEqual(payload["queried_dependency_count"], 1)

    def test_open_source_alias_fields_match_checklist_schema(self) -> None:
        helper = load_project_reverse_helper()
        aliases = helper.open_source_alias_fields(
            {"primary_license": "MIT"},
            {"status": "available", "vulnerabilities": [{"id": "OSV-1"}]},
        )
        self.assertEqual(aliases["license_type"], "MIT")
        self.assertEqual(aliases["known_vulnerabilities"], [{"id": "OSV-1"}])

        unavailable = helper.open_source_alias_fields({"primary_license": None}, {"status": "unavailable"})
        self.assertEqual(unavailable["license_type"], "unknown")
        self.assertEqual(unavailable["known_vulnerabilities"], "unavailable")


if __name__ == "__main__":
    unittest.main()
