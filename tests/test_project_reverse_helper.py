from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


def load_helper():
    root = Path(__file__).resolve().parents[1]
    path = root / "src" / "assets" / "skills" / "project-reverse" / "scripts" / "project_reverse_helper.py"
    spec = importlib.util.spec_from_file_location("test_project_reverse_helper_module", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load project_reverse_helper.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = load_helper()


class ProjectReverseHelperTests(unittest.TestCase):
    def test_analyze_repo_collects_open_source_community_and_vulnerabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir(parents=True)
            (repo_dir / ".git").mkdir()
            (repo_dir / "package.json").write_text(
                json.dumps(
                    {
                        "name": "demo-repo",
                        "version": "1.0.0",
                        "license": "MIT",
                        "dependencies": {"lodash": "4.17.20"},
                    }
                ),
                encoding="utf-8",
            )
            (repo_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
            (repo_dir / "CONTRIBUTING.md").write_text("how to contribute\n", encoding="utf-8")
            (repo_dir / "SECURITY.md").write_text("security policy\n", encoding="utf-8")
            (repo_dir / ".github").mkdir()
            (repo_dir / ".github" / "ISSUE_TEMPLATE.md").write_text("template\n", encoding="utf-8")
            (repo_dir / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text("pr template\n", encoding="utf-8")
            (repo_dir / ".github" / "workflows").mkdir()
            (repo_dir / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "index.js").write_text("export function demo() { return true; }\n", encoding="utf-8")

            args = Namespace(
                repo="https://github.com/example/demo-repo",
                ref=None,
                output=None,
                source_anchor=None,
                max_files=3000,
                max_api_entries=800,
                exclude_globs=[],
                open_source=True,
                community_health=True,
                vulnerabilities=True,
                write_focused_artifacts=False,
                artifact_dir=None,
                git_timeout=5,
                http_timeout=5,
                source_anchor_mode="timestamp",
                keep_temp=True,
            )

            def fake_prepare_repo(repo: str, ref: str | None, keep_temp: bool):
                return repo_dir, None, []

            def fake_run_git(cmd: list[str], cwd: Path | None = None, check: bool = True, timeout: int | None = None) -> str:
                if cmd == ["rev-parse", "HEAD"]:
                    return "abc123"
                if cmd == ["branch", "--show-current"]:
                    return "main"
                if cmd == ["remote", "get-url", "origin"]:
                    return "https://github.com/example/demo-repo.git"
                if cmd == ["status", "--short"]:
                    return ""
                if cmd[:2] == ["ls-remote", "https://github.com/example/demo-repo"] or cmd[:2] == ["ls-remote", "https://github.com/example/demo-repo.git"]:
                    return "abc123\tHEAD"
                return ""

            def fake_http_json(
                url: str,
                *,
                method: str = "GET",
                data: dict[str, object] | None = None,
                headers: dict[str, str] | None = None,
                timeout: int = 15,
            ):
                if url.endswith("/repos/example/demo-repo"):
                    return {
                        "private": False,
                        "archived": False,
                        "fork": False,
                        "default_branch": "main",
                        "homepage": "https://example.com",
                        "topics": ["demo", "oss"],
                        "stargazers_count": 42,
                        "forks_count": 7,
                        "subscribers_count": 5,
                        "open_issues_count": 3,
                        "created_at": "2025-01-01T00:00:00Z",
                        "updated_at": "2026-05-20T00:00:00Z",
                        "pushed_at": "2026-05-20T00:00:00Z",
                        "has_issues": True,
                        "has_wiki": True,
                        "has_projects": True,
                        "license": {"spdx_id": "MIT"},
                    }
                if url.endswith("/repos/example/demo-repo/releases/latest"):
                    return {"published_at": "2026-05-10T00:00:00Z"}
                if url.endswith("/repos/example/demo-repo/contributors?per_page=5"):
                    return [{"login": "a"}, {"login": "b"}]
                if "osv.dev" in url:
                    return {
                        "results": [
                            {
                                "vulns": [
                                    {
                                        "id": "OSV-2026-1",
                                        "aliases": ["CVE-2026-0001"],
                                        "summary": "Demo vulnerability",
                                        "database_specific": {"severity": "HIGH"},
                                        "references": [{"url": "https://osv.dev/vulnerability/OSV-2026-1"}],
                                        "affected": [{"fixed": "4.17.21"}],
                                    }
                                ]
                            }
                        ]
                    }
                raise AssertionError(f"unexpected url: {url}")

            with patch.object(helper, "prepare_repo", side_effect=fake_prepare_repo), patch.object(
                helper, "run_git", side_effect=fake_run_git
            ), patch.object(helper, "http_json", side_effect=fake_http_json):
                payload = helper.analyze_repo(args)

            self.assertEqual(payload["open_source_signals"]["repository"], "example/demo-repo")
            self.assertTrue(payload["open_source_signals"]["is_public"])
            self.assertEqual(payload["license_signals"]["primary_license"], "MIT")
            self.assertTrue(payload["community_health"]["checks"]["has_contributing"])
            self.assertEqual(payload["community_health"]["score"], "healthy")
            self.assertEqual(payload["vulnerability_signals"]["summary"]["high"], 1)
            self.assertEqual(payload["vulnerability_signals"]["findings"][0]["package"], "lodash")


if __name__ == "__main__":
    unittest.main()
