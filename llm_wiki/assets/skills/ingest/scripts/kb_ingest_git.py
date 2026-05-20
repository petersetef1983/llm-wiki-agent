#!/usr/bin/env python3
"""Deterministic Git repository evidence extraction for ingest workflows."""

from __future__ import annotations

from kb_ingest_core import *

import fnmatch
import os
import shutil
import subprocess
import tempfile


DEFAULT_EXCLUDE_GLOBS = [
    ".git/**",
    "**/.git/**",
    "node_modules/**",
    "**/node_modules/**",
    "dist/**",
    "**/dist/**",
    "build/**",
    "**/build/**",
    ".venv/**",
    "**/.venv/**",
    "venv/**",
    "**/venv/**",
    "__pycache__/**",
    "**/__pycache__/**",
    ".next/**",
    "**/.next/**",
    ".turbo/**",
    "**/.turbo/**",
    "target/**",
    "**/target/**",
    ".cache/**",
    "**/.cache/**",
]
DEFAULT_INCLUDE_GLOBS = [
    "README*",
    "STRUCTURE*",
    "CHANGELOG*",
    "LICENSE*",
    "docs/**",
    ".github/**",
    ".gitlab-ci.yml",
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "package-lock.json",
    "Cargo.toml",
    "Cargo.lock",
    "pyproject.toml",
    "requirements*.txt",
    "poetry.lock",
    "go.mod",
    "go.sum",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    "Makefile",
    "Dockerfile",
    "docker-compose*.yml",
    "src/**",
    "lib/**",
    "app/**",
    "packages/**",
    "crates/**",
    "services/**",
    "apps/**",
    "tests/**",
    "test/**",
]
MANIFEST_NAMES = {
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "package-lock.json",
    "Cargo.toml",
    "Cargo.lock",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "poetry.lock",
    "go.mod",
    "go.sum",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".gitlab-ci.yml",
}
DOC_PATTERNS = ["README*", "STRUCTURE*", "CHANGELOG*", "docs/**"]
CI_PATTERNS = [".github/**", ".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"]
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tgz",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".wasm",
    ".mp3",
    ".mp4",
    ".mov",
    ".wav",
    ".sqlite",
    ".db",
}
MAX_BINARY_PROBE_BYTES = 4096


def run_git(args: list[str], cwd: Path | None = None) -> str:
    command = ["git", *args]
    completed = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        error_text = normalize_text(completed.stderr or completed.stdout or "")
        raise RuntimeError(f"`{' '.join(command)}` failed: {error_text or 'unknown git error'}")
    return completed.stdout.strip()


def is_probably_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        data = path.read_bytes()[:MAX_BINARY_PROBE_BYTES]
    except OSError:
        return True
    return b"\x00" in data


def normalize_repo_rel(path: Path) -> str:
    return path.as_posix().lstrip("./")


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def should_exclude(path: str, exclude_globs: list[str]) -> bool:
    return matches_any(path, exclude_globs)


def should_include_excerpt(path: str, include_globs: list[str], exclude_globs: list[str]) -> bool:
    if should_exclude(path, exclude_globs):
        return False
    return matches_any(path, include_globs)


def collect_repo_files(repo_dir: Path, max_files: int, exclude_globs: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    files: list[dict[str, Any]] = []
    all_paths: list[Path] = []
    for item in repo_dir.rglob("*"):
        if not item.is_file():
            continue
        rel = normalize_repo_rel(item.relative_to(repo_dir))
        if should_exclude(rel, exclude_globs):
            continue
        all_paths.append(item)

    all_paths.sort(key=lambda item: item.relative_to(repo_dir).as_posix().lower())
    if len(all_paths) > max_files:
        warnings.append(f"File inventory truncated from {len(all_paths)} to {max_files} entries.")
    for item in all_paths[:max_files]:
        rel = normalize_repo_rel(item.relative_to(repo_dir))
        size = item.stat().st_size
        suffix = item.suffix.lower()
        files.append(
            {
                "path": rel,
                "size_bytes": size,
                "extension": suffix.lstrip(".") or "",
                "is_binary": is_probably_binary(item),
            }
        )
    return files, warnings


def build_directory_tree(files: list[dict[str, Any]], max_entries: int = 300) -> list[str]:
    entries: set[str] = set()
    for file_info in files:
        path = Path(str(file_info["path"]))
        parts = path.parts
        for idx in range(1, len(parts)):
            entries.add("/".join(parts[:idx]) + "/")
        entries.add(path.as_posix())
    return sorted(entries, key=lambda item: (item.count("/"), item.lower()))[:max_entries]


def count_extensions(files: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for file_info in files:
        ext = str(file_info.get("extension") or "[no_ext]")
        counts[ext] = counts.get(ext, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def excerpt_file(path: Path, max_chars: int) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    return {
        "text": truncate_text(text, max_chars),
        "char_count": len(text),
        "truncated": truncated,
    }


def select_excerpts(
    repo_dir: Path,
    files: list[dict[str, Any]],
    include_globs: list[str],
    exclude_globs: list[str],
    max_excerpt_files: int,
    max_file_chars: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    candidates = [
        file_info
        for file_info in files
        if not file_info.get("is_binary") and should_include_excerpt(str(file_info["path"]), include_globs, exclude_globs)
    ]
    candidates.sort(key=lambda item: (excerpt_priority(str(item["path"])), str(item["path"]).lower()))
    if len(candidates) > max_excerpt_files:
        warnings.append(f"Excerpt candidates truncated from {len(candidates)} to {max_excerpt_files} files.")

    excerpts: list[dict[str, Any]] = []
    for file_info in candidates[:max_excerpt_files]:
        rel = str(file_info["path"])
        path = repo_dir / rel
        try:
            excerpt = excerpt_file(path, max_file_chars)
        except OSError as exc:
            warnings.append(f"Could not read excerpt file `{rel}`: {exc}")
            continue
        excerpts.append(
            {
                "path": rel,
                "size_bytes": file_info["size_bytes"],
                "extension": file_info["extension"],
                **excerpt,
            }
        )
    return excerpts, warnings


def excerpt_priority(path: str) -> int:
    name = Path(path).name.lower()
    lowered = path.lower()
    if name.startswith("readme"):
        return 0
    if name.startswith("structure"):
        return 1
    if name in {item.lower() for item in MANIFEST_NAMES}:
        return 2
    if lowered.startswith("docs/"):
        return 3
    if lowered.startswith((".github/", ".gitlab")):
        return 4
    if "/src/" in f"/{lowered}" or lowered.startswith("src/"):
        return 5
    if "/test" in f"/{lowered}" or lowered.startswith(("test/", "tests/")):
        return 6
    return 9


def select_paths(files: list[dict[str, Any]], patterns: list[str], limit: int = 80) -> list[str]:
    selected = [str(file_info["path"]) for file_info in files if matches_any(str(file_info["path"]), patterns)]
    return sorted(selected, key=lambda item: item.lower())[:limit]


def clone_repo(url: str, destination: Path) -> None:
    run_git(["clone", url, str(destination)])


def update_submodules(repo_dir: Path) -> list[str]:
    if not (repo_dir / ".gitmodules").exists():
        return []
    try:
        run_git(["submodule", "update", "--init", "--recursive"], cwd=repo_dir)
    except RuntimeError as exc:
        return [f"Submodule update failed after clone; main repository snapshot still continued: {exc}"]
    return []


def checkout_ref(repo_dir: Path, ref: str | None) -> None:
    if ref:
        run_git(["checkout", ref], cwd=repo_dir)


def current_branch(repo_dir: Path) -> str | None:
    try:
        branch = run_git(["branch", "--show-current"], cwd=repo_dir)
    except RuntimeError:
        return None
    return branch or None


def remote_url(repo_dir: Path) -> str | None:
    try:
        return run_git(["remote", "get-url", "origin"], cwd=repo_dir) or None
    except RuntimeError:
        return None


def worktree_status(repo_dir: Path) -> str:
    return run_git(["status", "--short"], cwd=repo_dir)


def extract_git_repo(
    *,
    url: str,
    ref: str | None,
    output_path: Path | None,
    source_anchor_path: Path | None,
    output_format: str,
    max_files: int,
    max_excerpt_files: int,
    max_file_chars: int,
    include_globs: list[str],
    exclude_globs: list[str],
    keep_temp: bool,
) -> dict[str, Any]:
    git_path = shutil.which("git")
    if not git_path:
        raise RuntimeError("`git` is required for extract-git-repo but was not found on PATH.")

    effective_include_globs = include_globs or DEFAULT_INCLUDE_GLOBS
    effective_exclude_globs = DEFAULT_EXCLUDE_GLOBS + (exclude_globs or [])
    warnings: list[str] = []
    temp_dir_obj = None if keep_temp else tempfile.TemporaryDirectory(prefix="kb-ingest-git-")
    temp_root = Path(tempfile.mkdtemp(prefix="kb-ingest-git-")) if keep_temp else Path(temp_dir_obj.name)
    repo_dir = temp_root / "repo"

    try:
        clone_repo(url, repo_dir)
        checkout_ref(repo_dir, ref)
        warnings.extend(update_submodules(repo_dir))
        commit_sha = run_git(["rev-parse", "HEAD"], cwd=repo_dir)
        files, file_warnings = collect_repo_files(repo_dir, max_files, effective_exclude_globs)
        warnings.extend(file_warnings)
        excerpts, excerpt_warnings = select_excerpts(
            repo_dir,
            files,
            effective_include_globs,
            effective_exclude_globs,
            max_excerpt_files,
            max_file_chars,
        )
        warnings.extend(excerpt_warnings)
        status = worktree_status(repo_dir)
        if status:
            warnings.append("Temporary clone has non-empty status after checkout; submodule or line-ending changes may exist.")

        payload = {
            "source_type": "git-repo",
            "source_policy": {
                "temporary_full_clone": True,
                "source_code_saved_to_sources": False,
                "full_archive_saved": False,
                "source_anchor_contains_code": False,
            },
            "repo": {
                "url": url,
                "remote_url": remote_url(repo_dir),
                "requested_ref": ref,
                "resolved_commit": commit_sha,
                "current_branch": current_branch(repo_dir),
                "captured_at": datetime.now().isoformat(timespec="seconds"),
            },
            "limits": {
                "max_files": max_files,
                "max_excerpt_files": max_excerpt_files,
                "max_file_chars": max_file_chars,
                "include_globs": effective_include_globs,
                "exclude_globs": effective_exclude_globs,
            },
            "inventory": {
                "file_count": len(files),
                "extension_counts": count_extensions(files),
                "tree": build_directory_tree(files),
                "files": files,
                "manifest_files": select_paths(files, ["**/" + name for name in MANIFEST_NAMES] + list(MANIFEST_NAMES)),
                "documentation_files": select_paths(files, DOC_PATTERNS),
                "ci_config_files": select_paths(files, CI_PATTERNS),
                "module_candidate_files": select_paths(
                    files,
                    ["src/**", "lib/**", "app/**", "packages/**", "crates/**", "services/**", "apps/**"],
                    limit=160,
                ),
                "test_files": select_paths(files, ["tests/**", "test/**", "**/*test*", "**/*spec*"], limit=120),
            },
            "analysis_pack": {
                "purpose": "Temporary LLM source analysis support. Excerpts are truncated and should not be treated as durable source replacement.",
                "excerpts": excerpts,
            },
            "warnings": warnings,
        }
        if keep_temp:
            payload["temporary_clone"] = {
                "path": str(repo_dir),
                "cleanup_performed": False,
                "cleanup_responsibility": "Caller requested --keep-temp; remove this directory after analysis.",
            }
        else:
            payload["temporary_clone"] = {
                "path": None,
                "cleanup_performed": True,
                "cleanup_responsibility": "Helper removed the temporary clone after creating the artifact.",
            }

        if source_anchor_path:
            write_source_anchor(source_anchor_path, payload, output_path)
        if output_path:
            emit_git_payload(payload, output_path, output_format)
        return payload
    finally:
        if not keep_temp and temp_dir_obj is not None:
            temp_dir_obj.cleanup()


def write_source_anchor(anchor_path: Path, payload: dict[str, Any], output_path: Path | None) -> None:
    if anchor_path.exists():
        raise FileExistsError(f"Source anchor already exists and will not be overwritten: {anchor_path}")
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    repo = payload["repo"]
    policy = payload["source_policy"]
    lines = [
        "# Git Repository Source Anchor",
        "",
        "## Repository",
        f"- url: `{repo['url']}`",
        f"- remote_url: `{repo.get('remote_url') or 'unknown'}`",
        f"- requested_ref: `{repo.get('requested_ref') or 'default'}`",
        f"- resolved_commit: `{repo['resolved_commit']}`",
        f"- current_branch: `{repo.get('current_branch') or 'detached-or-unknown'}`",
        f"- captured_at: `{repo['captured_at']}`",
        "",
        "## Evidence Artifact",
        f"- path: `{output_path.as_posix() if output_path else 'stdout'}`",
        "",
        "## Source Policy",
        f"- temporary_full_clone: `{policy['temporary_full_clone']}`",
        f"- source_code_saved_to_sources: `{policy['source_code_saved_to_sources']}`",
        f"- full_archive_saved: `{policy['full_archive_saved']}`",
        f"- source_anchor_contains_code: `{policy['source_anchor_contains_code']}`",
        "",
        "## Notes",
        "- This anchor intentionally contains no source code.",
        "- Re-run `extract-git-repo` with the same URL and commit if source-level verification is needed.",
        "- Durable knowledge belongs in `wiki/` and `outputs/`, not in this anchor.",
        "",
    ]
    anchor_path.write_text("\n".join(lines), encoding="utf-8")


def emit_git_payload(payload: dict[str, Any], output_path: Path, output_format: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        output_path.write_text(render_git_markdown(payload), encoding="utf-8")
    print(f"Wrote git repo extraction to {output_path}")


def render_git_markdown(payload: dict[str, Any]) -> str:
    repo = payload["repo"]
    inventory = payload["inventory"]
    lines = [
        "# Git Repository Extraction",
        "",
        "## Repository",
        f"- url: `{repo['url']}`",
        f"- remote_url: `{repo.get('remote_url') or 'unknown'}`",
        f"- requested_ref: `{repo.get('requested_ref') or 'default'}`",
        f"- resolved_commit: `{repo['resolved_commit']}`",
        f"- current_branch: `{repo.get('current_branch') or 'detached-or-unknown'}`",
        f"- captured_at: `{repo['captured_at']}`",
        "",
        "## Source Policy",
        "- temporary full clone was used for analysis",
        "- source code was not saved to `sources/`",
        "- full archive/checkouts are not preserved by default",
        "",
        "## Inventory",
        f"- file_count: `{inventory['file_count']}`",
        "- extension_counts:",
    ]
    for ext, count in inventory["extension_counts"].items():
        lines.append(f"  - `{ext}`: {count}")
    lines.extend(["", "## Documentation Files"])
    lines.extend([f"- `{path}`" for path in inventory["documentation_files"]] or ["- none"])
    lines.extend(["", "## Manifest Files"])
    lines.extend([f"- `{path}`" for path in inventory["manifest_files"]] or ["- none"])
    lines.extend(["", "## Module Candidate Files"])
    lines.extend([f"- `{path}`" for path in inventory["module_candidate_files"][:80]] or ["- none"])
    lines.extend(["", "## Analysis Pack Excerpts"])
    for excerpt in payload["analysis_pack"]["excerpts"]:
        lines.extend(
            [
                f"### `{excerpt['path']}`",
                "",
                f"- size_bytes: `{excerpt['size_bytes']}`",
                f"- char_count: `{excerpt['char_count']}`",
                f"- truncated: `{excerpt['truncated']}`",
                "",
                "```text",
                excerpt["text"],
                "```",
                "",
            ]
        )
    lines.extend(["## Warnings"])
    lines.extend([f"- {warning}" for warning in payload["warnings"]] or ["- none"])
    lines.extend(
        [
            "",
            "## Suggested Deep Ingest Use",
            "- Use this artifact plus the temporary clone during the current run to update durable project wiki pages.",
            "- Do not treat excerpts as a replacement for the original repository.",
            "- Do not save full source code under `sources/`.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
