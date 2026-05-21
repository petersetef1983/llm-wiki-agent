#!/usr/bin/env python3
"""Deterministic project reverse-engineering evidence helper.

This script emits evidence for LLM Wiki ingest. It intentionally does not
write durable wiki pages or decide canonical graph relationships.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request


SCHEMA_VERSION = "project-reverse.v1"
DEFAULT_REMOTE_GIT_TIMEOUT = 30
DEFAULT_HTTP_TIMEOUT = 15
DEFAULT_GITHUB_API_BASE = "https://api.github.com"
DEFAULT_OSV_API_URL = "https://api.osv.dev/v1/querybatch"

DEFAULT_EXCLUDES = [
    ".git/**",
    "**/.git/**",
    "node_modules/**",
    "**/node_modules/**",
    "dist/**",
    "**/dist/**",
    "build/**",
    "**/build/**",
    "target/**",
    "**/target/**",
    ".next/**",
    "**/.next/**",
    ".turbo/**",
    "**/.turbo/**",
    ".cache/**",
    "**/.cache/**",
    ".venv/**",
    "**/.venv/**",
    "venv/**",
    "**/venv/**",
    "__pycache__/**",
    "**/__pycache__/**",
]

TEXT_EXTS = {
    ".astro",
    ".c",
    ".cc",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".graphql",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".kt",
    ".md",
    ".mdx",
    ".mjs",
    ".mts",
    ".php",
    ".proto",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

BINARY_EXTS = {
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

MANIFEST_NAMES = {
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "package-lock.json",
    "pnpm-workspace.yaml",
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
    "turbo.json",
    "biome.json",
}

LICENSE_FILE_NAMES = {
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "LICENCE",
    "LICENCE.md",
    "NOTICE",
    "NOTICE.md",
    "COPYING",
    "COPYING.md",
}

FRAMEWORK_HINTS = {
    "react": ["react"],
    "nextjs": ["next"],
    "vite": ["vite"],
    "express": ["express"],
    "fastify": ["fastify"],
    "nestjs": ["@nestjs/core", "@nestjs/common"],
    "fastapi": ["fastapi"],
    "flask": ["flask"],
    "django": ["django"],
    "pydantic": ["pydantic"],
    "tokio": ["tokio"],
    "axum": ["axum"],
    "actix-web": ["actix-web"],
    "serde": ["serde"],
    "clap": ["clap"],
    "gin": ["github.com/gin-gonic/gin"],
    "cobra": ["github.com/spf13/cobra"],
}

COMMUNITY_FILE_PATTERNS = {
    "contributing": ["CONTRIBUTING*", "**/CONTRIBUTING*"],
    "code_of_conduct": ["CODE_OF_CONDUCT*", "**/CODE_OF_CONDUCT*"],
    "security_policy": ["SECURITY*", ".github/SECURITY*", "**/SECURITY*"],
    "support": ["SUPPORT*", "**/SUPPORT*"],
    "governance": ["GOVERNANCE*", "**/GOVERNANCE*"],
    "maintainers": ["MAINTAINERS*", "**/MAINTAINERS*"],
    "issue_templates": [".github/ISSUE_TEMPLATE*", ".github/ISSUE_TEMPLATE/**"],
    "pull_request_template": [".github/PULL_REQUEST_TEMPLATE*", "**/PULL_REQUEST_TEMPLATE*"],
}

KNOWN_LICENSES = {
    "mit": "MIT",
    "apache-2.0": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "mpl-2.0": "MPL-2.0",
    "mozilla public license 2.0": "MPL-2.0",
    "gpl-2.0": "GPL-2.0",
    "gpl-3.0": "GPL-3.0",
    "agpl-3.0": "AGPL-3.0",
    "lgpl-2.1": "LGPL-2.1",
    "lgpl-3.0": "LGPL-3.0",
    "isc": "ISC",
    "unlicense": "Unlicense",
    "cc0-1.0": "CC0-1.0",
    "elv2": "Elastic-2.0",
    "elastic license 2.0": "Elastic-2.0",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_git(args: list[str], cwd: Path | None = None, check: bool = True, timeout: int | None = None) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        seconds = f" after {timeout}s" if timeout else ""
        raise RuntimeError(f"git {' '.join(args)} timed out{seconds}") from exc
    if check and completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "unknown git error").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return completed.stdout.strip()


def is_local_repo(value: str) -> bool:
    path = Path(value)
    return path.exists() and ((path / ".git").exists() or (path / "HEAD").exists())


def provider_hint(repo: str) -> str:
    lowered = repo.lower()
    if "github.com" in lowered:
        return "github"
    if "gitlab" in lowered:
        return "gitlab"
    if is_local_repo(repo):
        return "local"
    return "git"


def hosted_repo_identity(*candidates: str | None) -> dict[str, str] | None:
    patterns = [
        re.compile(
            r"^(?:https?://|ssh://git@)(?P<host>[^/:]+)/(?P<owner>[^/]+)/(?P<name>[^/#?]+?)(?:\.git)?/?$",
            re.I,
        ),
        re.compile(r"^git@(?P<host>[^:]+):(?P<owner>[^/]+)/(?P<name>[^/#?]+?)(?:\.git)?/?$", re.I),
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        for pattern in patterns:
            match = pattern.match(text)
            if not match:
                continue
            host = match.group("host").lower()
            owner = match.group("owner")
            name = match.group("name")
            provider = "git"
            if "github.com" in host:
                provider = "github"
            elif "gitlab" in host:
                provider = "gitlab"
            return {
                "provider": provider,
                "host": host,
                "owner": owner,
                "name": name,
                "repository": f"{owner}/{name}",
            }
    return None


def http_json(
    url: str,
    *,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
) -> Any:
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib_request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json" if payload is not None else "application/json",
            "User-Agent": "llm-wiki-agent/project-reverse",
            **(headers or {}),
        },
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        detail = detail[:400] if detail else exc.reason
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_api_json(path: str, timeout: int = DEFAULT_HTTP_TIMEOUT) -> Any:
    base = os.environ.get("GITHUB_API_BASE", DEFAULT_GITHUB_API_BASE).rstrip("/")
    return http_json(f"{base}{path}", headers=github_headers(), timeout=timeout)


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def should_exclude(rel: str, excludes: list[str]) -> bool:
    return matches_any(rel, excludes)


def normalize_rel(path: Path) -> str:
    rel = path.as_posix()
    return rel[2:] if rel.startswith("./") else rel


def is_probably_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTS:
        return True
    try:
        data = path.read_bytes()[:4096]
    except OSError:
        return True
    return b"\x00" in data


def read_text(path: Path, max_chars: int = 120_000) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars]
    return text


def line_iter(path: Path, max_chars: int = 120_000) -> list[tuple[int, str]]:
    text = read_text(path, max_chars=max_chars)
    return list(enumerate(text.splitlines(), start=1))


def split_params(raw: str) -> list[dict[str, Any]]:
    params: list[dict[str, Any]] = []
    cleaned = raw.strip()
    if not cleaned:
        return params
    for piece in re.split(r",(?![^\[\(<{]*[\]\)>}])", cleaned):
        item = piece.strip()
        if not item or item in {"self", "&self", "mut self", "cls"}:
            continue
        default = None
        required = True
        if "=" in item:
            left, default = item.split("=", 1)
            item = left.strip()
            default = default.strip()
            required = False
        name = item
        typ = None
        if ":" in item:
            name, typ = item.split(":", 1)
            name = name.strip().lstrip("*&")
            typ = typ.strip()
        elif " " in item:
            parts = item.split()
            name = parts[-1].strip("*&")
            typ = " ".join(parts[:-1])
        params.append(
            {
                "name": name.strip().strip("{}"),
                "type": typ,
                "required": required,
                "default": default,
                "source": "signature",
            }
        )
    return params


def path_params(route: str) -> list[dict[str, Any]]:
    found = []
    for name in re.findall(r"[:{<]([A-Za-z_][A-Za-z0-9_]*)[}>]?", route):
        found.append({"name": name, "type": None, "required": True, "default": None, "source": "path"})
    return found


def merge_params(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for param in group:
            name = str(param.get("name") or "").strip()
            if not name:
                continue
            merged.setdefault(name, param)
            if not merged[name].get("type") and param.get("type"):
                merged[name]["type"] = param["type"]
    return list(merged.values())


def api_field_confidence(
    *,
    kind: str,
    parameters: list[dict[str, Any]] | None,
    request_shape: str | None,
    return_shape: str | None,
    behavior: str,
    evidence: str,
    base_confidence: str,
) -> dict[str, str]:
    """Record field-level confidence without pretending static scans know everything."""
    params = parameters or []
    lowered = f"{behavior} {evidence}".lower()
    is_type_export = any(token in evidence for token in ["export-class", "pub-struct", "pub-enum", "pub-trait"])
    is_command = kind == "cli-command"
    is_rpc = kind == "rpc-service"
    is_message = kind == "websocket-message"
    return {
        "source_location": "confirmed",
        "parameters": "not_applicable" if is_type_export else ("confirmed" if params else "tentative"),
        "request_shape": "confirmed" if request_shape else ("tentative" if kind in {"http-route", "rpc-service", "websocket-message"} else "not_observed"),
        "return_shape": (
            "confirmed"
            if return_shape
            else ("not_applicable" if is_type_export or is_command or is_message else "tentative")
        ),
        "behavior": "inferred" if "inferred" in lowered else base_confidence,
        "overall": base_confidence,
    }


def effective_api_confidence(
    *,
    kind: str,
    base_confidence: str,
    field_confidence: dict[str, str],
    evidence: str,
) -> str:
    if base_confidence == "tentative":
        return "tentative"
    if base_confidence == "inferred":
        return "inferred"
    if any(value == "tentative" for value in field_confidence.values()):
        return "tentative"
    if any(value == "inferred" for value in field_confidence.values()):
        return "inferred"
    if kind in {"library-export", "sdk-export"} and any(token in evidence for token in ["public-function", "pub-fn"]):
        return "inferred"
    return "confirmed"


def classify_area(path: str) -> list[str]:
    lowered = path.lower()
    name = Path(path).name
    areas: set[str] = set()
    if any(token in lowered for token in ["route", "router", "controller", "api", "endpoint", "proto", "graphql", "websocket"]):
        areas.add("api")
    if any(token in lowered for token in ["config", ".env", "settings", "application."]):
        areas.add("config")
    if name in MANIFEST_NAMES or "lock" in name.lower() or "requirements" in name.lower():
        areas.add("dependencies")
    if any(token in lowered for token in ["docker", "compose", ".github/", ".gitlab", "jenkins", "infra/", "terraform", ".tf", "makefile"]):
        areas.add("build-deploy")
    if any(token in lowered for token in ["migration", "schema", "model", "entity", "database", "db/", ".sql"]):
        areas.add("data-storage")
    if any(token in lowered for token in ["test", "spec", "__tests__"]):
        areas.add("tests")
    if any(token in lowered for token in ["auth", "security", "secret", "token", "password", "rbac", "oauth"]):
        areas.add("security")
    if lowered.endswith((".md", ".mdx", ".rst")) or lowered.startswith("docs/") or "readme" in name.lower():
        areas.add("docs")
    if lowered.endswith((".rs", ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".java", ".cs")):
        areas.add("module")
    if not areas:
        areas.add("unknown")
    return sorted(areas)


def collect_files(repo_dir: Path, max_files: int, excludes: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    all_paths = []
    for item in repo_dir.rglob("*"):
        if not item.is_file():
            continue
        rel = normalize_rel(item.relative_to(repo_dir))
        if should_exclude(rel, excludes):
            continue
        all_paths.append(item)
    all_paths.sort(key=lambda item: item.relative_to(repo_dir).as_posix().lower())
    if len(all_paths) > max_files:
        warnings.append(f"File inventory truncated from {len(all_paths)} to {max_files} entries.")
    files = []
    for item in all_paths[:max_files]:
        rel = normalize_rel(item.relative_to(repo_dir))
        suffix = item.suffix.lower()
        files.append(
            {
                "path": rel,
                "size_bytes": item.stat().st_size,
                "extension": suffix.lstrip(".") or "",
                "is_binary": is_probably_binary(item),
            }
        )
    return files, warnings


def select_paths(files: list[dict[str, Any]], patterns: list[str], limit: int = 120) -> list[str]:
    selected = [str(item["path"]) for item in files if matches_any(str(item["path"]), patterns)]
    return sorted(selected, key=lambda value: value.lower())[:limit]


def directory_tree(files: list[dict[str, Any]], limit: int = 350) -> list[str]:
    entries: set[str] = set()
    for item in files:
        path = Path(str(item["path"]))
        parts = path.parts
        for idx in range(1, len(parts)):
            entries.add("/".join(parts[:idx]) + "/")
        entries.add(path.as_posix())
    return sorted(entries, key=lambda value: (value.count("/"), value.lower()))[:limit]


def parse_package_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(read_text(path, max_chars=400_000))
    except Exception as exc:
        return {"path": normalize_rel(path), "parse_error": str(exc)}
    return {
        "name": data.get("name"),
        "version": data.get("version"),
        "type": data.get("type"),
        "main": data.get("main"),
        "module": data.get("module"),
        "types": data.get("types"),
        "license": data.get("license"),
        "licenses": data.get("licenses"),
        "exports": data.get("exports"),
        "scripts": data.get("scripts", {}),
        "dependencies": data.get("dependencies", {}),
        "devDependencies": data.get("devDependencies", {}),
        "peerDependencies": data.get("peerDependencies", {}),
        "bin": data.get("bin"),
    }


def parse_cargo_toml(path: Path) -> dict[str, Any]:
    text = read_text(path, max_chars=300_000)
    package: dict[str, Any] = {}
    dependencies: dict[str, str] = {}
    workspace_members: list[str] = []
    section = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.strip("[]")
            continue
        if section == "package" and "=" in stripped:
            key, value = stripped.split("=", 1)
            if key.strip() in {"name", "version", "edition", "license"}:
                package[key.strip()] = value.strip().strip('"')
        elif section in {"dependencies", "dev-dependencies", "build-dependencies"} and "=" in stripped:
            key, value = stripped.split("=", 1)
            dependencies[key.strip()] = value.strip()
        elif section == "workspace" and stripped.startswith("members"):
            match = re.search(r"\[(.*)\]", stripped)
            if match:
                workspace_members.extend([item.strip().strip('"') for item in match.group(1).split(",") if item.strip()])
    return {"package": package, "dependencies": dependencies, "workspace_members": workspace_members}


def parse_go_mod(path: Path) -> dict[str, Any]:
    text = read_text(path)
    module = None
    go_version = None
    deps = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("module "):
            module = stripped.split(None, 1)[1]
        elif stripped.startswith("go "):
            go_version = stripped.split(None, 1)[1]
        elif re.match(r"^[A-Za-z0-9_.\-/]+ v\d", stripped):
            deps.append(stripped)
    return {"module": module, "go": go_version, "dependencies": deps[:200]}


def normalize_license_name(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    lowered = text.lower()
    for key, normalized in KNOWN_LICENSES.items():
        if key in lowered:
            return normalized
    return text


def infer_license_from_preview(text: str) -> str | None:
    lowered = text.lower()
    if "permission is hereby granted, free of charge, to any person obtaining a copy" in lowered:
        return "MIT"
    if "apache license" in lowered and "version 2.0" in lowered:
        return "Apache-2.0"
    if "gnu general public license" in lowered and "version 3" in lowered:
        return "GPL-3.0"
    if "gnu general public license" in lowered and "version 2" in lowered:
        return "GPL-2.0"
    if "gnu affero general public license" in lowered:
        return "AGPL-3.0"
    if "elastic license" in lowered and "2.0" in lowered:
        return "Elastic-2.0"
    return None


def normalize_dependency_version(value: str | None, ecosystem: str) -> str | None:
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        return None
    if ecosystem == "crates.io" and "version" in text:
        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', text)
        if match:
            text = match.group(1)
    if ecosystem == "npm" and text.startswith(("file:", "link:", "workspace:", "github:", "git+", "http:", "https:")):
        return None
    if ecosystem == "PyPI" and text.startswith(("-e ", "git+", "http:", "https:")):
        return None
    match = re.search(r"\d+(?:\.\d+){0,3}(?:[-+._A-Za-z0-9]+)?", text)
    return match.group(0) if match else None


def dependency_inventory(stack: dict[str, Any], repo_dir: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for manifest in stack.get("manifests", {}).get("package_json", []):
        for section in ["dependencies", "devDependencies", "peerDependencies"]:
            for name, raw_version in (manifest.get(section) or {}).items():
                version = normalize_dependency_version(str(raw_version), "npm")
                if not version:
                    continue
                key = ("npm", str(name), version)
                if key in seen:
                    continue
                seen.add(key)
                inventory.append(
                    {
                        "ecosystem": "npm",
                        "name": str(name),
                        "version": version,
                        "manifest_path": manifest.get("path"),
                        "source": section,
                    }
                )
    for manifest in stack.get("manifests", {}).get("cargo_toml", []):
        for name, raw_version in (manifest.get("dependencies") or {}).items():
            version = normalize_dependency_version(str(raw_version), "crates.io")
            if not version:
                continue
            key = ("crates.io", str(name), version)
            if key in seen:
                continue
            seen.add(key)
            inventory.append(
                {
                    "ecosystem": "crates.io",
                    "name": str(name),
                    "version": version,
                    "manifest_path": manifest.get("path"),
                    "source": "dependencies",
                }
            )
    for manifest in stack.get("manifests", {}).get("go_mod", []):
        for dependency in manifest.get("dependencies", []):
            parts = str(dependency).split()
            if len(parts) < 2:
                continue
            version = normalize_dependency_version(parts[1], "Go")
            if not version:
                continue
            key = ("Go", parts[0], version)
            if key in seen:
                continue
            seen.add(key)
            inventory.append(
                {
                    "ecosystem": "Go",
                    "name": parts[0],
                    "version": version,
                    "manifest_path": manifest.get("path"),
                    "source": "go.mod",
                }
            )
    for path in sorted(repo_dir.glob("requirements*.txt"), key=lambda item: item.as_posix().lower())[:40]:
        rel = normalize_rel(path.relative_to(repo_dir))
        for line in read_text(repo_dir / rel, max_chars=120_000).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = re.match(r"^([A-Za-z0-9_.-]+)\s*==\s*([^\s;#]+)", stripped)
            if not match:
                continue
            name, version = match.group(1), normalize_dependency_version(match.group(2), "PyPI")
            if not version:
                continue
            key = ("PyPI", name, version)
            if key in seen:
                continue
            seen.add(key)
            inventory.append(
                {
                    "ecosystem": "PyPI",
                    "name": name,
                    "version": version,
                    "manifest_path": rel,
                    "source": "requirements",
                }
            )
    return inventory[:200]


def collect_stack(repo_dir: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    extensions = Counter(str(item.get("extension") or "[no_ext]") for item in files)
    languages = []
    ext_lang = {
        "rs": "Rust",
        "ts": "TypeScript",
        "tsx": "TypeScript/React",
        "js": "JavaScript",
        "jsx": "JavaScript/React",
        "py": "Python",
        "go": "Go",
        "java": "Java",
        "cs": "C#",
        "php": "PHP",
        "rb": "Ruby",
        "mdx": "MDX",
    }
    for ext, language in ext_lang.items():
        if extensions.get(ext):
            languages.append({"language": language, "file_count": extensions[ext], "evidence": f"*.{ext}"})

    package_managers = []
    manifest_payloads: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dependency_names: set[str] = set()
    for rel in select_paths(files, ["**/package.json", "package.json"], limit=80):
        parsed = parse_package_json(repo_dir / rel)
        parsed["path"] = rel
        manifest_payloads["package_json"].append(parsed)
        for key in ["dependencies", "devDependencies", "peerDependencies"]:
            dependency_names.update((parsed.get(key) or {}).keys())
    for rel in select_paths(files, ["**/Cargo.toml", "Cargo.toml"], limit=120):
        parsed = parse_cargo_toml(repo_dir / rel)
        parsed["path"] = rel
        manifest_payloads["cargo_toml"].append(parsed)
        dependency_names.update(parsed.get("dependencies", {}).keys())
    for rel in select_paths(files, ["**/go.mod", "go.mod"], limit=40):
        parsed = parse_go_mod(repo_dir / rel)
        parsed["path"] = rel
        manifest_payloads["go_mod"].append(parsed)
        for dep in parsed.get("dependencies", []):
            dependency_names.add(dep.split()[0])
    if select_paths(files, ["pnpm-lock.yaml", "**/pnpm-lock.yaml"]):
        package_managers.append("pnpm")
    if select_paths(files, ["package-lock.json", "**/package-lock.json"]):
        package_managers.append("npm")
    if select_paths(files, ["yarn.lock", "**/yarn.lock"]):
        package_managers.append("yarn")
    if select_paths(files, ["Cargo.lock", "**/Cargo.lock"]):
        package_managers.append("cargo")
    if select_paths(files, ["poetry.lock", "**/poetry.lock"]):
        package_managers.append("poetry")
    if select_paths(files, ["go.sum", "**/go.sum"]):
        package_managers.append("go modules")

    frameworks = []
    for name, needles in FRAMEWORK_HINTS.items():
        evidence = sorted(dep for dep in dependency_names if dep in needles or any(needle in dep for needle in needles))
        if evidence:
            frameworks.append({"name": name, "evidence": evidence[:10]})

    return {
        "languages": languages,
        "package_managers": sorted(set(package_managers)),
        "frameworks": frameworks,
        "manifests": manifest_payloads,
    }


def collect_license_signals(repo_dir: Path, files: list[dict[str, Any]], stack: dict[str, Any]) -> dict[str, Any]:
    license_files = []
    for rel in select_paths(files, list(LICENSE_FILE_NAMES) + ["**/LICENSE*", "**/LICENCE*", "**/NOTICE*", "**/COPYING*"], limit=80):
        path = repo_dir / rel
        preview = ""
        if path.exists() and not is_probably_binary(path):
            preview = read_text(path, max_chars=2000)
        license_files.append(
            {
                "path": rel,
                "preview": preview[:2000],
            }
        )

    manifest_licenses = []
    for manifest in stack.get("manifests", {}).get("package_json", []):
        if manifest.get("license") or manifest.get("licenses"):
            manifest_licenses.append(
                {
                    "path": manifest.get("path"),
                    "package": manifest.get("name"),
                    "license": manifest.get("license"),
                    "licenses": manifest.get("licenses"),
                }
            )
    for manifest in stack.get("manifests", {}).get("cargo_toml", []):
        package = manifest.get("package") or {}
        if package.get("license"):
            manifest_licenses.append(
                {
                    "path": manifest.get("path"),
                    "package": package.get("name"),
                    "license": package.get("license"),
                }
            )

    license_related_files = select_paths(
        files,
        ["**/*license*", "**/*licence*", "**/*notice*", "**/licenserc.*", "**/license-check.*"],
        limit=120,
    )
    normalized: list[str] = []
    for item in manifest_licenses:
        normalized_name = normalize_license_name(item.get("license"))
        if normalized_name and normalized_name not in normalized:
            normalized.append(normalized_name)
        for extra in item.get("licenses") or []:
            normalized_name = normalize_license_name(extra)
            if normalized_name and normalized_name not in normalized:
                normalized.append(normalized_name)
    for item in license_files:
        inferred = infer_license_from_preview(str(item.get("preview") or ""))
        if inferred and inferred not in normalized:
            normalized.append(inferred)
    primary = normalized[0] if normalized else None
    review_required = len(normalized) > 1 or any(token in str(item.get("license") or "").lower() for item in manifest_licenses for token in [" or ", " and ", "/", ","])
    return {
        "license_files": license_files,
        "manifest_licenses": manifest_licenses,
        "license_related_files": license_related_files,
        "normalized_licenses": normalized,
        "primary_license": primary,
        "license_review_required": review_required,
        "confidence": "confirmed" if license_files or manifest_licenses else "tentative",
    }


def collect_open_source_signals(
    repo: dict[str, Any],
    license_signals: dict[str, Any],
    *,
    enabled: bool,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    payload = {
        "enabled": enabled,
        "provider": repo.get("provider"),
        "remote_url": repo.get("remote_url"),
        "repository": None,
        "host": None,
        "owner": None,
        "name": None,
        "is_public": None,
        "is_open_source": bool(license_signals.get("primary_license")),
        "archived": None,
        "fork": None,
        "default_branch": repo.get("default_or_current_branch"),
        "homepage": None,
        "topics": [],
        "stars": None,
        "forks": None,
        "watchers": None,
        "open_issues": None,
        "created_at": None,
        "updated_at": None,
        "pushed_at": None,
        "source": "local-repo-signals",
        "confidence": "tentative",
    }
    identity = hosted_repo_identity(repo.get("remote_url"), repo.get("input"))
    if identity:
        payload.update(identity)
    repo_api: dict[str, Any] | None = None
    if not enabled or not identity or identity.get("provider") != "github":
        return payload, repo_api, warnings
    try:
        repo_api = github_api_json(f"/repos/{identity['owner']}/{identity['name']}", timeout=timeout)
        payload.update(
            {
                "is_public": not bool(repo_api.get("private")),
                "is_open_source": (not bool(repo_api.get("private"))) and bool(license_signals.get("primary_license") or repo_api.get("license")),
                "archived": repo_api.get("archived"),
                "fork": repo_api.get("fork"),
                "default_branch": repo_api.get("default_branch") or payload.get("default_branch"),
                "homepage": repo_api.get("homepage"),
                "topics": repo_api.get("topics") or [],
                "stars": repo_api.get("stargazers_count"),
                "forks": repo_api.get("forks_count"),
                "watchers": repo_api.get("subscribers_count") or repo_api.get("watchers_count"),
                "open_issues": repo_api.get("open_issues_count"),
                "created_at": repo_api.get("created_at"),
                "updated_at": repo_api.get("updated_at"),
                "pushed_at": repo_api.get("pushed_at"),
                "source": "github-repo-api",
                "confidence": "confirmed",
            }
        )
    except Exception as exc:
        warnings.append(f"Open-source metadata query failed: {exc}")
    return payload, repo_api, warnings


def parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def collect_community_health(
    files: list[dict[str, Any]],
    build_deploy: dict[str, Any],
    repo_api: dict[str, Any] | None,
    *,
    enabled: bool,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
    repository: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    docs = {name: select_paths(files, patterns, limit=20) for name, patterns in COMMUNITY_FILE_PATTERNS.items()}
    latest_release_at = None
    contributor_sample_count = None
    remote_signals: dict[str, Any] = {}
    if enabled and repo_api and repository:
        remote_signals = {
            "has_issues": repo_api.get("has_issues"),
            "has_wiki": repo_api.get("has_wiki"),
            "has_projects": repo_api.get("has_projects"),
            "open_issues_count": repo_api.get("open_issues_count"),
            "updated_at": repo_api.get("updated_at"),
            "pushed_at": repo_api.get("pushed_at"),
        }
        try:
            release = github_api_json(f"/repos/{repository}/releases/latest", timeout=timeout)
            latest_release_at = release.get("published_at") or release.get("created_at")
        except Exception as exc:
            warnings.append(f"Latest release query failed: {exc}")
        try:
            contributors = github_api_json(f"/repos/{repository}/contributors?per_page=5", timeout=timeout)
            if isinstance(contributors, list):
                contributor_sample_count = len(contributors)
        except Exception as exc:
            warnings.append(f"Contributor query failed: {exc}")
    checks = {
        "has_contributing": bool(docs["contributing"]),
        "has_code_of_conduct": bool(docs["code_of_conduct"]),
        "has_security_policy": bool(docs["security_policy"]),
        "has_support": bool(docs["support"]),
        "has_governance": bool(docs["governance"]),
        "has_maintainers": bool(docs["maintainers"]),
        "has_issue_templates": bool(docs["issue_templates"]),
        "has_pull_request_template": bool(docs["pull_request_template"]),
        "has_ci": bool(build_deploy.get("ci_files")),
        "has_recent_release": bool(latest_release_at),
        "has_recent_push": False,
    }
    pushed_at = parse_timestamp(remote_signals.get("pushed_at"))
    if pushed_at is not None:
        checks["has_recent_push"] = (datetime.now(timezone.utc) - pushed_at).days <= 180
    points = sum(1 for value in checks.values() if value)
    score = "unknown"
    if points >= 6:
        score = "healthy"
    elif points >= 3:
        score = "moderate"
    elif points > 0:
        score = "limited"
    return (
        {
            "enabled": enabled,
            "score": score,
            "checks": checks,
            "documents": docs,
            "remote": remote_signals,
            "latest_release_at": latest_release_at,
            "contributor_sample_count": contributor_sample_count,
            "confidence": "confirmed" if repo_api else ("inferred" if points else "tentative"),
        },
        warnings,
    )


def normalize_vulnerability_severity(item: dict[str, Any]) -> str:
    value = str((item.get("database_specific") or {}).get("severity") or "").strip().lower()
    if value in {"critical", "high", "medium", "low"}:
        return value
    return "unknown"


def collect_vulnerability_signals(
    stack: dict[str, Any],
    repo_dir: Path,
    *,
    enabled: bool,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    dependencies = dependency_inventory(stack, repo_dir)
    payload = {
        "enabled": enabled,
        "query_source": "osv",
        "queried_dependencies": [],
        "queryable_dependency_count": len(dependencies),
        "findings": [],
        "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0},
        "confidence": "tentative",
    }
    if not enabled:
        return payload, warnings
    queries = [
        {
            "package": {"name": item["name"], "ecosystem": item["ecosystem"]},
            "version": item["version"],
        }
        for item in dependencies[:100]
    ]
    payload["queried_dependencies"] = dependencies[:100]
    if not queries:
        warnings.append("No queryable dependency versions were found for OSV.")
        return payload, warnings
    try:
        response = http_json(
            os.environ.get("OSV_API_URL", DEFAULT_OSV_API_URL),
            method="POST",
            data={"queries": queries},
            timeout=timeout,
        )
    except Exception as exc:
        warnings.append(f"Vulnerability query failed: {exc}")
        return payload, warnings
    for dependency, result in zip(payload["queried_dependencies"], (response.get("results") or [])):
        for vuln in result.get("vulns") or []:
            severity = normalize_vulnerability_severity(vuln)
            finding = {
                "package": dependency["name"],
                "ecosystem": dependency["ecosystem"],
                "version": dependency["version"],
                "manifest_path": dependency.get("manifest_path"),
                "id": vuln.get("id"),
                "aliases": vuln.get("aliases") or [],
                "summary": vuln.get("summary"),
                "severity": severity,
                "fixed_versions": [item.get("fixed") for item in vuln.get("affected") or [] if item.get("fixed")],
                "reference_urls": [ref.get("url") for ref in vuln.get("references") or [] if ref.get("url")][:8],
                "confidence": "confirmed",
            }
            payload["findings"].append(finding)
            payload["summary"][severity] = payload["summary"].get(severity, 0) + 1
    payload["confidence"] = "confirmed"
    return payload, warnings


def infer_responsibility(path: str) -> str:
    name = Path(path).name.lower()
    hints = [
        ("engine", "core runtime or execution engine"),
        ("sdk", "developer SDK or client library"),
        ("api", "API surface or request handling"),
        ("console", "operator or developer console"),
        ("web", "web UI or website"),
        ("docs", "documentation"),
        ("infra", "infrastructure and deployment"),
        ("test", "tests and verification"),
        ("worker", "worker runtime or background execution"),
        ("cli", "command-line interface"),
        ("config", "configuration"),
    ]
    for token, value in hints:
        if token in name:
            return value
    return "candidate subsystem inferred from repository structure"


def local_import_targets(repo_dir: Path, module_path: str, top_levels: set[str], max_files: int = 120) -> list[str]:
    root = repo_dir / module_path
    if not root.exists() or not root.is_dir():
        return []
    deps: set[str] = set()
    scanned = 0
    for item in sorted(root.rglob("*")):
        if scanned >= max_files:
            break
        if not item.is_file() or item.suffix.lower() not in TEXT_EXTS:
            continue
        rel = normalize_rel(item.relative_to(repo_dir))
        if should_exclude(rel, DEFAULT_EXCLUDES):
            continue
        scanned += 1
        text = read_text(item, max_chars=60_000)
        for target in top_levels:
            if target == module_path.split("/")[0]:
                continue
            if re.search(rf"['\"](?:\.\./)*{re.escape(target)}(?:/|['\"])", text):
                deps.add(target)
            if re.search(rf"\buse\s+{re.escape(target)}\b|\bfrom\s+{re.escape(target)}\b|\bimport\s+{re.escape(target)}\b", text):
                deps.add(target)
    return sorted(deps)


def collect_modules(repo_dir: Path, files: list[dict[str, Any]], stack: dict[str, Any]) -> list[dict[str, Any]]:
    top_counts: Counter[str] = Counter()
    for item in files:
        parts = Path(str(item["path"])).parts
        if parts:
            top_counts[parts[0]] += 1

    candidates: set[str] = set()
    for top, count in top_counts.items():
        if count >= 3 and not top.startswith("."):
            candidates.add(top)
    for manifest in stack.get("manifests", {}).get("cargo_toml", []):
        for member in manifest.get("workspace_members", []):
            candidates.add(member.rstrip("/*"))

    modules = []
    top_levels = {candidate.split("/")[0] for candidate in candidates}
    for candidate in sorted(candidates, key=lambda value: (value.count("/"), value)):
        module_files = [str(item["path"]) for item in files if str(item["path"]) == candidate or str(item["path"]).startswith(candidate.rstrip("/") + "/")]
        if not module_files:
            continue
        entrypoints = [
            path
            for path in module_files
            if Path(path).name.lower()
            in {"main.rs", "lib.rs", "mod.rs", "index.ts", "index.tsx", "index.js", "main.ts", "app.ts", "server.ts", "__init__.py", "main.py"}
        ][:20]
        tests = [path for path in module_files if "test" in path.lower() or "spec" in path.lower()][:30]
        deps = local_import_targets(repo_dir, candidate, top_levels)
        score = 4 if not deps and entrypoints else 3
        if any(token in candidate.lower() for token in ["docs", "website", "blog"]):
            score = 2
        if any(token in candidate.lower() for token in ["engine", "core"]):
            score = min(score, 2)
        modules.append(
            {
                "name": candidate,
                "paths": [candidate],
                "responsibility": infer_responsibility(candidate),
                "entrypoints": entrypoints,
                "dependencies": deps,
                "test_files": tests,
                "file_count": len(module_files),
                "reuse_score": score,
                "confidence": "inferred",
            }
        )
    return modules[:80]


def owner_module_for(path: str, modules: list[dict[str, Any]]) -> str | None:
    for module in modules:
        for prefix in module.get("paths", []):
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                return module["name"]
    parts = Path(path).parts
    return parts[0] if parts else None


def add_api(
    entries: list[dict[str, Any]],
    *,
    kind: str,
    name: str,
    method: str | None,
    path_value: str | None,
    parameters: list[dict[str, Any]] | None,
    request_shape: str | None,
    return_shape: str | None,
    behavior: str,
    source_path: str,
    source_line: int,
    owner_module: str | None,
    confidence: str,
    evidence: str,
    max_entries: int,
) -> None:
    if len(entries) >= max_entries:
        return
    field_confidence = api_field_confidence(
        kind=kind,
        parameters=parameters,
        request_shape=request_shape,
        return_shape=return_shape,
        behavior=behavior,
        evidence=evidence,
        base_confidence=confidence,
    )
    confidence = effective_api_confidence(
        kind=kind,
        base_confidence=confidence,
        field_confidence=field_confidence,
        evidence=evidence,
    )
    field_confidence["overall"] = confidence
    entries.append(
        {
            "kind": kind,
            "name": name,
            "method": method,
            "path": path_value,
            "parameters": parameters or [],
            "request_shape": request_shape,
            "return_shape": return_shape,
            "behavior": behavior,
            "source_path": source_path,
            "source_line": source_line,
            "owner_module": owner_module,
            "confidence": confidence,
            "field_confidence": field_confidence,
            "evidence": evidence,
        }
    )


def next_signature(lines: list[tuple[int, str]], start_index: int, pattern: str) -> tuple[str | None, int | None]:
    rx = re.compile(pattern)
    for line_no, line in lines[start_index : min(len(lines), start_index + 8)]:
        match = rx.search(line)
        if match:
            return line.strip(), line_no
    return None, None


def collect_api_registry(repo_dir: Path, files: list[dict[str, Any]], modules: list[dict[str, Any]], max_entries: int) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    candidates = [
        str(item["path"])
        for item in files
        if not item.get("is_binary") and Path(str(item["path"])).suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go", ".proto", ".graphql", ".java", ".cs"}
    ]
    for rel in candidates:
        if len(entries) >= max_entries:
            warnings.append(f"API registry truncated at {max_entries} entries.")
            break
        path = repo_dir / rel
        try:
            lines = line_iter(path, max_chars=250_000)
        except OSError as exc:
            warnings.append(f"Could not scan API candidates in {rel}: {exc}")
            continue
        owner = owner_module_for(rel, modules)
        suffix = path.suffix.lower()
        for idx, (line_no, line) in enumerate(lines):
            stripped = line.strip()
            if suffix == ".graphql":
                gql = re.search(r"\b(type|extend type)\s+(Query|Mutation|Subscription)\b", stripped)
                if gql:
                    add_api(
                        entries,
                        kind="rpc-service",
                        name=f"GraphQL {gql.group(2)}",
                        method=gql.group(2).lower(),
                        path_value=gql.group(2),
                        parameters=[],
                        request_shape=gql.group(2),
                        return_shape=None,
                        behavior=f"GraphQL {gql.group(2)} root type declaration",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence="graphql-root-type",
                        max_entries=max_entries,
                    )
                field = re.search(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(([^)]*)\))?\s*:\s*([A-Za-z_][A-Za-z0-9_!\[\]]+)", line)
                if field and not stripped.startswith("#"):
                    add_api(
                        entries,
                        kind="rpc-service",
                        name=field.group(1),
                        method="graphql-field",
                        path_value=field.group(1),
                        parameters=split_params(field.group(2) or ""),
                        request_shape=field.group(2),
                        return_shape=field.group(3),
                        behavior=f"GraphQL field `{field.group(1)}`",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence="graphql-field",
                        max_entries=max_entries,
                    )
            elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
                route = re.search(r"\b(app|router|fastify)\.(get|post|put|delete|patch)\s*\(\s*['\"`]([^'\"`]+)", stripped)
                if route:
                    method = route.group(2).upper()
                    route_path = route.group(3)
                    add_api(
                        entries,
                        kind="http-route",
                        name=f"{method} {route_path}",
                        method=method,
                        path_value=route_path,
                        parameters=path_params(route_path),
                        request_shape=None,
                        return_shape=None,
                        behavior=f"{method} route handler inferred from route declaration",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence="js-route-declaration",
                        max_entries=max_entries,
                    )
                ws = re.search(r"\b(?:socket|ws|websocket|channel)\.(on|emit|send|subscribe|publish)\s*\(\s*['\"`]([^'\"`]+)", stripped, re.I)
                if ws:
                    add_api(
                        entries,
                        kind="websocket-message",
                        name=ws.group(2),
                        method=ws.group(1),
                        path_value=ws.group(2),
                        parameters=[],
                        request_shape=None,
                        return_shape=None,
                        behavior=f"WebSocket/channel `{ws.group(1)}` message inferred from handler",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="inferred",
                        evidence="js-websocket-message",
                        max_entries=max_entries,
                    )
                nest = re.search(r"@(Get|Post|Put|Delete|Patch)\s*\(\s*['\"`]([^'\"`]*)", stripped)
                if nest:
                    method = nest.group(1).upper()
                    route_path = nest.group(2)
                    sig, sig_line = next_signature(lines, idx + 1, r"\w+\s*\((.*)\)")
                    params = split_params(re.search(r"\((.*)\)", sig or "").group(1)) if sig and re.search(r"\((.*)\)", sig) else []
                    add_api(
                        entries,
                        kind="http-route",
                        name=f"{method} {route_path}",
                        method=method,
                        path_value=route_path,
                        parameters=merge_params(path_params(route_path), params),
                        request_shape=None,
                        return_shape=None,
                        behavior="NestJS controller route inferred from decorator",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence=f"nestjs-route-decorator; signature_line={sig_line}",
                        max_entries=max_entries,
                    )
                fn = re.search(r"\bexport\s+(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*(?::\s*([^{]+))?", stripped)
                if fn:
                    add_api(
                        entries,
                        kind="sdk-export",
                        name=fn.group(1),
                        method=None,
                        path_value=fn.group(1),
                        parameters=split_params(fn.group(2)),
                        request_shape=None,
                        return_shape=(fn.group(3) or "").strip() or None,
                        behavior=f"Exported function `{fn.group(1)}`",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence="typescript-export-function",
                        max_entries=max_entries,
                    )
                const_export = re.search(r"\bexport\s+const\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*([^=]+))?\s*=", stripped)
                if const_export:
                    add_api(
                        entries,
                        kind="sdk-export",
                        name=const_export.group(1),
                        method=None,
                        path_value=const_export.group(1),
                        parameters=[],
                        request_shape=None,
                        return_shape=(const_export.group(2) or "").strip() or None,
                        behavior=f"Exported constant or function value `{const_export.group(1)}`",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="inferred",
                        evidence="typescript-export-const",
                        max_entries=max_entries,
                    )
                cls = re.search(r"\bexport\s+class\s+([A-Za-z_][A-Za-z0-9_]*)", stripped)
                if cls:
                    add_api(
                        entries,
                        kind="sdk-export",
                        name=cls.group(1),
                        method=None,
                        path_value=cls.group(1),
                        parameters=[],
                        request_shape=None,
                        return_shape=None,
                        behavior=f"Exported class `{cls.group(1)}`",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence="typescript-export-class",
                        max_entries=max_entries,
                    )
                command = re.search(r"\.command\s*\(\s*['\"`]([^'\"`]+)", stripped)
                if command:
                    add_api(
                        entries,
                        kind="cli-command",
                        name=command.group(1),
                        method=None,
                        path_value=command.group(1),
                        parameters=[],
                        request_shape=None,
                        return_shape=None,
                        behavior="CLI command inferred from command registration",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence="js-cli-command",
                        max_entries=max_entries,
                    )
            elif suffix == ".py":
                route = re.search(r"@(app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)", stripped)
                flask = re.search(r"@app\.route\s*\(\s*['\"]([^'\"]+)['\"].*methods\s*=\s*\[([^\]]+)\]", stripped)
                if route or flask:
                    if route:
                        method = route.group(2).upper()
                        route_path = route.group(3)
                        evidence = "python-fastapi-route"
                    else:
                        route_path = flask.group(1)
                        method = re.sub(r"[^A-Za-z]", "", flask.group(2).split(",")[0]).upper() or None
                        evidence = "python-flask-route"
                    sig, sig_line = next_signature(lines, idx + 1, r"(async\s+def|def)\s+")
                    params = split_params(re.search(r"\((.*)\)", sig or "").group(1)) if sig and re.search(r"\((.*)\)", sig) else []
                    ret = re.search(r"->\s*([^:]+)", sig or "")
                    add_api(
                        entries,
                        kind="http-route",
                        name=f"{method or 'ROUTE'} {route_path}",
                        method=method,
                        path_value=route_path,
                        parameters=merge_params(path_params(route_path), params),
                        request_shape=None,
                        return_shape=ret.group(1).strip() if ret else None,
                        behavior="Python route handler inferred from decorator",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence=f"{evidence}; signature_line={sig_line}",
                        max_entries=max_entries,
                    )
                fn = re.search(r"^(?:async\s+def|def)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*(?:->\s*([^:]+))?", stripped)
                if fn and not fn.group(1).startswith("_") and ("__init__.py" in rel or "/api" in rel or "/sdk" in rel or rel.endswith("main.py")):
                    add_api(
                        entries,
                        kind="library-export",
                        name=fn.group(1),
                        method=None,
                        path_value=fn.group(1),
                        parameters=split_params(fn.group(2)),
                        request_shape=None,
                        return_shape=(fn.group(3) or "").strip() or None,
                        behavior=f"Public Python function `{fn.group(1)}`",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="inferred",
                        evidence="python-public-function",
                        max_entries=max_entries,
                    )
                ws = re.search(r"@(socketio|websocket|ws)\.(on|route)\s*\(\s*['\"]([^'\"]+)", stripped, re.I)
                if ws:
                    add_api(
                        entries,
                        kind="websocket-message",
                        name=ws.group(3),
                        method=ws.group(2),
                        path_value=ws.group(3),
                        parameters=[],
                        request_shape=None,
                        return_shape=None,
                        behavior="Python WebSocket/socket handler inferred from decorator",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="inferred",
                        evidence="python-websocket-handler",
                        max_entries=max_entries,
                    )
            elif suffix == ".rs":
                route = re.search(r"\.route\s*\(\s*\"([^\"]+)\"\s*,\s*(.+)\)", stripped)
                if route:
                    route_path = route.group(1)
                    methods = re.findall(r"\b(get|post|put|delete|patch)\s*\(", route.group(2))
                    if not methods:
                        methods = ["route"]
                    for method_raw in methods:
                        method = method_raw.upper()
                        add_api(
                            entries,
                            kind="http-route",
                            name=f"{method} {route_path}",
                            method=method,
                            path_value=route_path,
                            parameters=path_params(route_path),
                            request_shape=None,
                            return_shape=None,
                            behavior="Rust router route inferred from route declaration",
                            source_path=rel,
                            source_line=line_no,
                            owner_module=owner,
                            confidence="confirmed",
                            evidence="rust-axum-route",
                            max_entries=max_entries,
                        )
                actix_resource = re.search(r"web::resource\s*\(\s*\"([^\"]+)\"", stripped)
                if actix_resource:
                    add_api(
                        entries,
                        kind="http-route",
                        name=f"ROUTE {actix_resource.group(1)}",
                        method=None,
                        path_value=actix_resource.group(1),
                        parameters=path_params(actix_resource.group(1)),
                        request_shape=None,
                        return_shape=None,
                        behavior="Rust Actix web resource route inferred from resource declaration",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="inferred",
                        evidence="rust-actix-resource",
                        max_entries=max_entries,
                    )
                attr = re.search(r"#\[(get|post|put|delete|patch)\s*\(\s*\"([^\"]+)\"", stripped)
                if attr:
                    method = attr.group(1).upper()
                    route_path = attr.group(2)
                    sig, sig_line = next_signature(lines, idx + 1, r"(pub\s+)?(async\s+)?fn\s+")
                    params = split_params(re.search(r"\((.*)\)", sig or "").group(1)) if sig and re.search(r"\((.*)\)", sig) else []
                    ret = re.search(r"->\s*([^{]+)", sig or "")
                    add_api(
                        entries,
                        kind="http-route",
                        name=f"{method} {route_path}",
                        method=method,
                        path_value=route_path,
                        parameters=merge_params(path_params(route_path), params),
                        request_shape=None,
                        return_shape=ret.group(1).strip() if ret else None,
                        behavior="Rust route handler inferred from attribute",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence=f"rust-route-attribute; signature_line={sig_line}",
                        max_entries=max_entries,
                    )
                fn = re.search(r"\bpub\s+(?:async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*(?:->\s*([^{;]+))?", stripped)
                if fn:
                    add_api(
                        entries,
                        kind="library-export",
                        name=fn.group(1),
                        method=None,
                        path_value=fn.group(1),
                        parameters=split_params(fn.group(2)),
                        request_shape=None,
                        return_shape=(fn.group(3) or "").strip() or None,
                        behavior=f"Public Rust function `{fn.group(1)}`",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence="rust-pub-fn",
                        max_entries=max_entries,
                    )
                typ = re.search(r"\bpub\s+(struct|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]*)", stripped)
                if typ:
                    add_api(
                        entries,
                        kind="library-export",
                        name=typ.group(2),
                        method=None,
                        path_value=typ.group(2),
                        parameters=[],
                        request_shape=None,
                        return_shape=None,
                        behavior=f"Public Rust {typ.group(1)} `{typ.group(2)}`",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence=f"rust-pub-{typ.group(1)}",
                        max_entries=max_entries,
                    )
            elif suffix == ".go":
                route = re.search(r"\.(GET|POST|PUT|DELETE|PATCH)\s*\(\s*\"([^\"]+)\"", stripped)
                if route:
                    method = route.group(1)
                    route_path = route.group(2)
                    add_api(
                        entries,
                        kind="http-route",
                        name=f"{method} {route_path}",
                        method=method,
                        path_value=route_path,
                        parameters=path_params(route_path),
                        request_shape=None,
                        return_shape=None,
                        behavior="Go route inferred from router registration",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence="go-route",
                        max_entries=max_entries,
                    )
                handle = re.search(r"HandleFunc\s*\(\s*\"([^\"]+)\"", stripped)
                if handle:
                    add_api(
                        entries,
                        kind="http-route",
                        name=f"ROUTE {handle.group(1)}",
                        method=None,
                        path_value=handle.group(1),
                        parameters=path_params(handle.group(1)),
                        request_shape=None,
                        return_shape=None,
                        behavior="Go handler route inferred from HandleFunc",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="inferred",
                        evidence="go-handlefunc",
                        max_entries=max_entries,
                    )
            elif suffix == ".proto":
                svc = re.search(r"\brpc\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*returns\s*\(([^)]*)\)", stripped)
                if svc:
                    add_api(
                        entries,
                        kind="rpc-service",
                        name=svc.group(1),
                        method="rpc",
                        path_value=svc.group(1),
                        parameters=[{"name": "request", "type": svc.group(2).strip(), "required": True, "default": None, "source": "proto"}],
                        request_shape=svc.group(2).strip(),
                        return_shape=svc.group(3).strip(),
                        behavior=f"gRPC method `{svc.group(1)}`",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence="proto-rpc",
                        max_entries=max_entries,
                    )
            elif suffix == ".java":
                spring = re.search(r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*(?:\(\s*)?(?:value\s*=\s*)?[\"']([^\"']*)", stripped)
                if spring:
                    method_map = {
                        "GetMapping": "GET",
                        "PostMapping": "POST",
                        "PutMapping": "PUT",
                        "DeleteMapping": "DELETE",
                        "PatchMapping": "PATCH",
                        "RequestMapping": None,
                    }
                    method = method_map.get(spring.group(1))
                    route_path = spring.group(2)
                    add_api(
                        entries,
                        kind="http-route",
                        name=f"{method or 'ROUTE'} {route_path}",
                        method=method,
                        path_value=route_path,
                        parameters=path_params(route_path),
                        request_shape=None,
                        return_shape=None,
                        behavior="Spring controller route inferred from mapping annotation",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence="java-spring-route",
                        max_entries=max_entries,
                    )
            elif suffix == ".cs":
                http_attr = re.search(r"\[(HttpGet|HttpPost|HttpPut|HttpDelete|HttpPatch)(?:\(\s*\"([^\"]*)\")?", stripped)
                minimal = re.search(r"\bMap(Get|Post|Put|Delete|Patch)\s*\(\s*\"([^\"]+)\"", stripped)
                if http_attr or minimal:
                    if minimal:
                        method = minimal.group(1).upper()
                        route_path = minimal.group(2)
                        evidence = "csharp-minimal-api"
                    else:
                        method = http_attr.group(1).replace("Http", "").upper()
                        route_path = http_attr.group(2) or ""
                        evidence = "csharp-controller-route"
                    add_api(
                        entries,
                        kind="http-route",
                        name=f"{method} {route_path}",
                        method=method,
                        path_value=route_path,
                        parameters=path_params(route_path),
                        request_shape=None,
                        return_shape=None,
                        behavior=".NET HTTP route inferred from route declaration",
                        source_path=rel,
                        source_line=line_no,
                        owner_module=owner,
                        confidence="confirmed",
                        evidence=evidence,
                        max_entries=max_entries,
                    )
    return entries, warnings


def collect_configuration(repo_dir: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    config_files = select_paths(
        files,
        [
            "**/*config*.yml",
            "**/*config*.yaml",
            "**/*config*.json",
            "**/*config*.toml",
            "**/.env*",
            "**/settings*.py",
            "config/**",
            "**/application*.yml",
            "**/application*.yaml",
        ],
        limit=160,
    )
    env_vars: list[dict[str, Any]] = []
    feature_flags: list[dict[str, Any]] = []
    validation_schemas: list[str] = []
    secret_signals: list[dict[str, Any]] = []
    env_patterns = [
        re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(r"os\.getenv\(['\"]([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(r"os\.environ(?:\.get)?\(['\"]([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(r"std::env::var\([\"']([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(r"env!\([\"']([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(r"os\.Getenv\([\"']([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(r"System\.getenv\([\"']([A-Za-z_][A-Za-z0-9_]*)"),
    ]
    secret_rx = re.compile(r"(secret|token|password|api[_-]?key|private[_-]?key)", re.I)
    flag_rx = re.compile(r"(feature[_-]?flag|enable[_-]?[A-Za-z0-9_]+|disable[_-]?[A-Za-z0-9_]+|flag[_-]?[A-Za-z0-9_]+)", re.I)
    validation_rx = re.compile(r"(pydantic|BaseSettings|z\.object|joi\.object|serde::Deserialize|ConfigurationProperties|viper)", re.I)
    scan_paths = [str(item["path"]) for item in files if not item.get("is_binary") and Path(str(item["path"])).suffix.lower() in TEXT_EXTS]
    for rel in scan_paths[:1600]:
        path = repo_dir / rel
        try:
            lines = line_iter(path, max_chars=160_000)
        except OSError:
            continue
        for line_no, line in lines:
            for rx in env_patterns:
                for match in rx.finditer(line):
                    env_vars.append({"name": match.group(1), "source_path": rel, "source_line": line_no})
            if flag_rx.search(line):
                feature_flags.append({"source_path": rel, "source_line": line_no, "evidence": line.strip()[:240]})
            if validation_rx.search(line):
                validation_schemas.append(rel)
            if secret_rx.search(line) and re.search(r"[:=]\s*['\"][^'\"]{12,}", line):
                secret_signals.append({"source_path": rel, "source_line": line_no, "risk": "possible hardcoded secret-like value"})
            if len(env_vars) > 500 and len(secret_signals) > 50:
                break
    dedup_env = []
    seen = set()
    for item in env_vars:
        key = (item["name"], item["source_path"], item["source_line"])
        if key not in seen:
            seen.add(key)
            dedup_env.append(item)
    dedup_validation = sorted(set(validation_schemas))[:120]
    return {
        "config_files": config_files,
        "environment_variables": dedup_env[:500],
        "feature_flags": feature_flags[:120],
        "validation_schemas": dedup_validation,
        "secret_signals": secret_signals[:80],
    }


def collect_build_deploy(repo_dir: Path, files: list[dict[str, Any]], stack: dict[str, Any]) -> dict[str, Any]:
    package_scripts = []
    for manifest in stack.get("manifests", {}).get("package_json", []):
        if manifest.get("scripts"):
            package_scripts.append({"path": manifest.get("path"), "scripts": manifest.get("scripts")})
    make_targets = []
    for rel in select_paths(files, ["Makefile", "**/Makefile"], limit=20):
        try:
            for line_no, line in line_iter(repo_dir / rel, max_chars=120_000):
                match = re.match(r"^([A-Za-z0-9_.-]+):(?:\s|$)", line)
                if match and not match.group(1).startswith("."):
                    make_targets.append({"target": match.group(1), "source_path": rel, "source_line": line_no})
        except OSError:
            pass
    return {
        "package_scripts": package_scripts,
        "make_targets": make_targets[:120],
        "docker_files": select_paths(files, ["Dockerfile", "**/Dockerfile", "**/Dockerfile.*", "docker-compose*.yml", "**/docker-compose*.yml"], limit=80),
        "ci_files": select_paths(files, [".github/**", ".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"], limit=160),
        "infra_files": select_paths(files, ["infra/**", "**/*.tf", "**/helm/**", "**/k8s/**", "**/kubernetes/**"], limit=160),
    }


def collect_data_storage(files: list[dict[str, Any]], stack: dict[str, Any]) -> dict[str, Any]:
    data_files = select_paths(
        files,
        [
            "**/migrations/**",
            "**/*migration*",
            "**/schema.prisma",
            "**/*.sql",
            "**/*model*.py",
            "**/*models*.py",
            "**/*entity*.ts",
            "**/*entity*.rs",
            "**/*schema*.ts",
            "**/*schema*.py",
            "**/*schema*.rs",
        ],
        limit=200,
    )
    dependency_names = set()
    for manifest in stack.get("manifests", {}).get("package_json", []):
        for key in ["dependencies", "devDependencies", "peerDependencies"]:
            dependency_names.update((manifest.get(key) or {}).keys())
    for manifest in stack.get("manifests", {}).get("cargo_toml", []):
        dependency_names.update((manifest.get("dependencies") or {}).keys())
    storage_deps = sorted(
        dep
        for dep in dependency_names
        if any(token in dep.lower() for token in ["sql", "postgres", "mysql", "redis", "mongo", "sqlite", "prisma", "diesel", "sea-orm", "queue", "kafka", "s3"])
    )
    return {"data_files": data_files, "storage_dependency_signals": storage_deps}


def collect_risks(files: list[dict[str, Any]], modules: list[dict[str, Any]], configuration: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    if warnings:
        risks.append({"type": "evidence-truncation-or-scan-warning", "severity": "medium", "evidence": warnings[:10]})
    modules_without_tests = [module["name"] for module in modules if module.get("file_count", 0) > 10 and not module.get("test_files")]
    if modules_without_tests:
        risks.append({"type": "missing-module-tests", "severity": "medium", "modules": modules_without_tests[:30]})
    if configuration.get("secret_signals"):
        risks.append({"type": "possible-hardcoded-secret", "severity": "high", "evidence": configuration["secret_signals"][:20]})
    large_files = [item for item in files if not item.get("is_binary") and int(item.get("size_bytes") or 0) > 200_000]
    if large_files:
        risks.append({"type": "large-source-files", "severity": "low", "files": [item["path"] for item in large_files[:20]]})
    high_coupling = [module["name"] for module in modules if len(module.get("dependencies") or []) >= 4]
    if high_coupling:
        risks.append({"type": "high-module-coupling", "severity": "medium", "modules": high_coupling[:20]})
    if not configuration.get("validation_schemas") and configuration.get("config_files"):
        risks.append({"type": "config-validation-not-detected", "severity": "low", "evidence": configuration.get("config_files", [])[:20]})
    return risks


def prepare_repo(repo: str, ref: str | None, keep_temp: bool) -> tuple[Path, tempfile.TemporaryDirectory[str] | None, list[str]]:
    warnings: list[str] = []
    if is_local_repo(repo) and ref is None:
        return Path(repo).resolve(), None, warnings
    if shutil.which("git") is None:
        raise RuntimeError("git is required but was not found on PATH")
    temp_obj = None if keep_temp else tempfile.TemporaryDirectory(prefix="project-reverse-")
    temp_root = Path(tempfile.mkdtemp(prefix="project-reverse-")) if keep_temp else Path(temp_obj.name)
    repo_dir = temp_root / "repo"
    run_git(["clone", repo, str(repo_dir)])
    if ref:
        run_git(["checkout", ref], cwd=repo_dir)
    if (repo_dir / ".gitmodules").exists():
        try:
            run_git(["submodule", "update", "--init", "--recursive"], cwd=repo_dir)
        except RuntimeError as exc:
            warnings.append(f"Submodule update failed: {exc}")
    return repo_dir, temp_obj, warnings


def remote_head(repo: str, ref: str | None = None, git_timeout: int = DEFAULT_REMOTE_GIT_TIMEOUT) -> tuple[str | None, str | None]:
    try:
        if is_local_repo(repo):
            repo_path = Path(repo).resolve()
            if ref:
                return run_git(["rev-parse", ref], cwd=repo_path, timeout=git_timeout), None
            branch = run_git(["branch", "--show-current"], cwd=repo_path, check=False, timeout=git_timeout)
            if branch:
                tracked = run_git(
                    ["rev-parse", f"refs/remotes/origin/{branch}"],
                    cwd=repo_path,
                    check=False,
                    timeout=git_timeout,
                )
                if tracked:
                    return tracked, None
            remote = run_git(["remote", "get-url", "origin"], cwd=repo_path, check=False, timeout=git_timeout)
            if remote:
                target_ref = f"refs/heads/{branch}" if branch else "HEAD"
                output = run_git(["ls-remote", remote, target_ref], timeout=git_timeout)
                first = output.splitlines()[0] if output else ""
                sha = first.split()[0] if first else None
                return sha, None
            return run_git(["rev-parse", "HEAD"], cwd=repo_path, timeout=git_timeout), None
        output = run_git(["ls-remote", repo, ref or "HEAD"], timeout=git_timeout)
        first = output.splitlines()[0] if output else ""
        sha = first.split()[0] if first else None
        return sha, None
    except Exception as exc:
        return None, str(exc)


def repo_identity(repo_dir: Path, repo: str, ref: str | None, git_timeout: int = DEFAULT_REMOTE_GIT_TIMEOUT) -> dict[str, Any]:
    commit = run_git(["rev-parse", "HEAD"], cwd=repo_dir, timeout=git_timeout)
    branch = run_git(["branch", "--show-current"], cwd=repo_dir, check=False, timeout=git_timeout) or None
    remote = run_git(["remote", "get-url", "origin"], cwd=repo_dir, check=False, timeout=git_timeout) or None
    dirty = run_git(["status", "--short"], cwd=repo_dir, check=False, timeout=git_timeout)
    latest, error = remote_head(repo, ref, git_timeout=git_timeout)
    freshness = "unknown"
    if latest:
        freshness = "current" if latest == commit else "stale"
    return {
        "input": repo,
        "provider": provider_hint(repo),
        "remote_url": remote,
        "requested_ref": ref,
        "default_or_current_branch": branch,
        "analyzed_commit": commit,
        "captured_at": utc_now(),
        "working_tree_dirty": bool(dirty),
        "working_tree_status": dirty.splitlines()[:80],
        "latest_checked_commit": latest,
        "freshness_check_error": error,
    }


def source_anchor_target(path: Path, mode: str, captured_at: str) -> Path | None:
    if mode == "skip":
        return None
    if not path.exists():
        return path
    if mode == "error":
        raise FileExistsError(f"Source anchor already exists and will not be overwritten: {path}")
    if mode != "timestamp":
        raise ValueError(f"Unknown source anchor mode: {mode}")
    stamp = re.sub(r"[^0-9]", "", captured_at)[:14] or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return path.with_name(f"{path.stem}-{stamp}{path.suffix}")


def write_source_anchor(path: Path, payload: dict[str, Any], output_path: Path | None, mode: str = "timestamp") -> Path | None:
    path = source_anchor_target(path, mode, payload["repo"]["captured_at"])
    if path is None:
        return None
    if path.exists():
        raise FileExistsError(f"Source anchor already exists and will not be overwritten: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    repo = payload["repo"]
    lines = [
        "# Project Reverse Source Anchor",
        "",
        "## Repository",
        f"- input: `{repo['input']}`",
        f"- provider: `{repo['provider']}`",
        f"- remote_url: `{repo.get('remote_url') or 'unknown'}`",
        f"- requested_ref: `{repo.get('requested_ref') or 'default/current'}`",
        f"- analyzed_commit: `{repo['analyzed_commit']}`",
        f"- latest_checked_commit: `{repo.get('latest_checked_commit') or 'unknown'}`",
        f"- freshness_status: `{payload['freshness']['status']}`",
        f"- captured_at: `{repo['captured_at']}`",
        "",
        "## Evidence Artifact",
        f"- path: `{output_path.as_posix() if output_path else 'stdout'}`",
        "",
        "## Source Policy",
        "- This anchor intentionally contains no source code.",
        "- Full repository checkouts are temporary analyzer inputs, not durable KB sources.",
        "- Durable knowledge belongs in `wiki/`, graph nodes, and `outputs/` after `ingest` compiles this evidence.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_focused_artifacts(payload: dict[str, Any], artifact_dir: Path) -> dict[str, str]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "api_registry": artifact_dir / "api-registry.json",
        "module_map": artifact_dir / "module-map.json",
    }
    api_payload = {
        "schema_version": payload["schema_version"],
        "source_type": payload["source_type"],
        "repo": payload["repo"],
        "api_registry": payload["api_registry"],
        "warnings": [warning for warning in payload.get("warnings", []) if "API registry" in warning],
    }
    module_payload = {
        "schema_version": payload["schema_version"],
        "source_type": payload["source_type"],
        "repo": payload["repo"],
        "modules": payload["modules"],
        "reuse_assessment": payload["reuse_assessment"],
    }
    artifacts["api_registry"].write_text(json.dumps(api_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    artifacts["module_map"].write_text(json.dumps(module_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {name: path.as_posix() for name, path in artifacts.items()}


def analyze_repo(args: argparse.Namespace) -> dict[str, Any]:
    repo_dir, temp_obj, prep_warnings = prepare_repo(args.repo, args.ref, args.keep_temp)
    try:
        excludes = DEFAULT_EXCLUDES + (args.exclude_globs or [])
        files, warnings = collect_files(repo_dir, args.max_files, excludes)
        warnings.extend(prep_warnings)
        repo = repo_identity(repo_dir, args.repo, args.ref, git_timeout=args.git_timeout)
        stack = collect_stack(repo_dir, files)
        modules = collect_modules(repo_dir, files, stack)
        license_signals = collect_license_signals(repo_dir, files, stack)
        api_registry, api_warnings = collect_api_registry(repo_dir, files, modules, args.max_api_entries)
        warnings.extend(api_warnings)
        configuration = collect_configuration(repo_dir, files)
        build_deploy = collect_build_deploy(repo_dir, files, stack)
        data_storage = collect_data_storage(files, stack)
        open_source_signals, repo_api, open_source_warnings = collect_open_source_signals(
            repo,
            license_signals,
            enabled=args.open_source or args.community_health,
            timeout=args.http_timeout,
        )
        warnings.extend(open_source_warnings)
        community_health, community_warnings = collect_community_health(
            files,
            build_deploy,
            repo_api,
            enabled=args.community_health,
            timeout=args.http_timeout,
            repository=open_source_signals.get("repository"),
        )
        warnings.extend(community_warnings)
        vulnerability_signals, vulnerability_warnings = collect_vulnerability_signals(
            stack,
            repo_dir,
            enabled=args.vulnerabilities,
            timeout=args.http_timeout,
        )
        warnings.extend(vulnerability_warnings)
        risks = collect_risks(files, modules, configuration, warnings)
        reuse = [
            {
                "module": module["name"],
                "score": module["reuse_score"],
                "recommendation": "extractable with review" if module["reuse_score"] >= 4 else "keep local or refactor before extraction",
                "evidence": {
                    "dependencies": module.get("dependencies", []),
                    "entrypoints": module.get("entrypoints", []),
                    "test_files": module.get("test_files", [])[:8],
                },
            }
            for module in modules
        ]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "source_type": "git-repository",
            "source_policy": {
                "temporary_full_clone": not is_local_repo(args.repo) or args.ref is not None,
                "source_code_saved_to_sources": False,
                "full_archive_saved": False,
                "source_anchor_contains_code": False,
            },
            "repo": repo,
            "freshness": {
                "status": "unknown"
                if repo.get("latest_checked_commit") is None
                else ("current" if repo["latest_checked_commit"] == repo["analyzed_commit"] else "stale"),
                "analyzed_commit": repo["analyzed_commit"],
                "latest_checked_commit": repo.get("latest_checked_commit"),
                "check_error": repo.get("freshness_check_error"),
            },
            "inventory": {
                "file_count": len(files),
                "extension_counts": dict(Counter(str(item.get("extension") or "[no_ext]") for item in files).most_common()),
                "tree": directory_tree(files),
                "files": files,
                "manifest_files": select_paths(files, ["**/" + name for name in MANIFEST_NAMES] + list(MANIFEST_NAMES), limit=200),
                "documentation_files": select_paths(files, ["README*", "**/README*", "docs/**", "**/*.md", "**/*.mdx"], limit=200),
                "test_files": select_paths(files, ["tests/**", "test/**", "**/*test*", "**/*spec*"], limit=200),
                "config_files": configuration["config_files"],
                "ci_files": build_deploy["ci_files"],
                "build_deploy_files": build_deploy["docker_files"] + build_deploy["infra_files"],
                "data_storage_files": data_storage["data_files"],
            },
            "stack": stack,
            "open_source_signals": open_source_signals,
            "license_signals": license_signals,
            "community_health": community_health,
            "modules": modules,
            "api_registry": api_registry,
            "configuration": configuration,
            "build_deploy": build_deploy,
            "data_storage": data_storage,
            "vulnerability_signals": vulnerability_signals,
            "risks": risks,
            "reuse_assessment": reuse,
            "warnings": warnings,
        }
        if args.write_focused_artifacts:
            artifact_dir = Path(args.artifact_dir) if args.artifact_dir else (Path(args.output).parent if args.output else Path.cwd())
            payload["focused_artifacts"] = write_focused_artifacts(payload, artifact_dir)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Wrote project reverse evidence to {output_path}")
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        if args.source_anchor:
            anchor_path = write_source_anchor(
                Path(args.source_anchor),
                payload,
                Path(args.output) if args.output else None,
                mode=args.source_anchor_mode,
            )
            if anchor_path is not None:
                payload["source_anchor_path"] = anchor_path.as_posix()
                if args.output:
                    output_path = Path(args.output)
                    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"Wrote source anchor to {anchor_path}")
        return payload
    finally:
        if temp_obj is not None and not args.keep_temp:
            temp_obj.cleanup()


def check_freshness(args: argparse.Namespace) -> dict[str, Any]:
    latest, error = remote_head(args.repo, args.ref, git_timeout=args.git_timeout)
    status = "unknown"
    if latest and args.analyzed_commit:
        status = "current" if latest == args.analyzed_commit else "stale"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "source_type": "git-repository",
        "repo": {"input": args.repo, "provider": provider_hint(args.repo), "requested_ref": args.ref},
        "freshness": {
            "status": status,
            "analyzed_commit": args.analyzed_commit,
            "latest_checked_commit": latest,
            "checked_at": utc_now(),
            "check_error": error,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def affected_pages_for_areas(area_counts: dict[str, int]) -> list[str]:
    mapping = {
        "api": ["wiki/api.md", "wiki/architecture.md"],
        "module": ["wiki/architecture.md", "wiki/modules/README.md", "wiki/modules/*.md"],
        "config": ["wiki/configuration.md", "outputs/sync-status.md"],
        "data-storage": ["wiki/data-storage.md", "wiki/technical-notes.md"],
        "build-deploy": ["wiki/build-deployment.md", "stack/infra.md", "outputs/implementation-guide.md"],
        "docs": ["README.md", "wiki/overview.md", "wiki/glossary.md", "wiki/open-questions.md"],
        "tests": ["wiki/technical-notes.md", "outputs/implementation-guide.md"],
        "dependencies": ["stack/backend.md", "stack/frontend.md", "stack/tools.md", "wiki/build-deployment.md"],
        "security": ["wiki/configuration.md", "wiki/technical-notes.md", "outputs/engineering-brief.md"],
        "unknown": ["wiki/open-questions.md", "outputs/backlog.md"],
    }
    pages: list[str] = []
    for area in sorted(area_counts):
        for page in mapping.get(area, mapping["unknown"]):
            if page not in pages:
                pages.append(page)
    if "outputs/sync-status.md" not in pages:
        pages.append("outputs/sync-status.md")
    return pages


def next_update_scope(changed: list[dict[str, Any]], area_counts: dict[str, int]) -> str:
    if not changed:
        return "No changed files detected; keep current durable wiki content and refresh sync status only."
    primary = ", ".join(f"{area}={count}" for area, count in sorted(area_counts.items()))
    return f"Update only durable pages mapped from changed areas ({primary}); avoid full project-theme rewrite unless semantic review finds cross-cutting drift."


def diff_repo(args: argparse.Namespace) -> dict[str, Any]:
    repo_dir, temp_obj, prep_warnings = prepare_repo(args.repo, None, args.keep_temp)
    try:
        diff_output = run_git(
            ["diff", "--name-status", args.old_commit, args.new_commit],
            cwd=repo_dir,
            timeout=args.git_timeout,
        )
        changed = []
        areas: Counter[str] = Counter()
        for line in diff_output.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            status = parts[0]
            path = parts[-1]
            item_areas = classify_area(path)
            for area in item_areas:
                areas[area] += 1
            changed.append({"status": status, "path": path, "areas": item_areas})
        area_counts = dict(areas)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "source_type": "git-repository",
            "repo": {"input": args.repo, "provider": provider_hint(args.repo), "old_commit": args.old_commit, "new_commit": args.new_commit, "captured_at": utc_now()},
            "diff": {
                "changed_files": changed,
                "changed_area_counts": area_counts,
                "affected_pages": affected_pages_for_areas(area_counts),
                "next_update_scope": next_update_scope(changed, area_counts),
                "warnings": prep_warnings,
            },
        }
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Wrote project reverse diff evidence to {output_path}")
        if args.sync_diff_output:
            sync_path = Path(args.sync_diff_output)
            sync_path.parent.mkdir(parents=True, exist_ok=True)
            sync_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Wrote sync diff evidence to {sync_path}")
        if not args.output and not args.sync_diff_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return payload
    finally:
        if temp_obj is not None and not args.keep_temp:
            temp_obj.cleanup()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project reverse-engineering evidence helper")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Analyze a Git repository into structured evidence")
    analyze.add_argument("--repo", required=True, help="Git URL or local repository path")
    analyze.add_argument("--ref", help="Optional branch, tag, or commit to analyze")
    analyze.add_argument("--output", help="JSON evidence output path")
    analyze.add_argument("--source-anchor", help="Optional source anchor path")
    analyze.add_argument("--max-files", type=int, default=3000)
    analyze.add_argument("--max-api-entries", type=int, default=800)
    analyze.add_argument("--exclude-globs", action="append", default=[])
    analyze.add_argument("--open-source", action="store_true", help="Query hosted repository open-source metadata when available.")
    analyze.add_argument("--community-health", action="store_true", help="Collect community health evidence from repo files and hosted metadata.")
    analyze.add_argument("--vulnerabilities", action="store_true", help="Query dependency vulnerability signals from OSV when versions are available.")
    analyze.add_argument("--write-focused-artifacts", action="store_true", help="Write api-registry.json and module-map.json beside the main artifact")
    analyze.add_argument("--artifact-dir", help="Directory for focused artifacts. Defaults to the main output directory.")
    analyze.add_argument("--git-timeout", type=int, default=DEFAULT_REMOTE_GIT_TIMEOUT, help="Seconds per remote freshness git operation.")
    analyze.add_argument("--http-timeout", type=int, default=DEFAULT_HTTP_TIMEOUT, help="Seconds per hosted metadata or vulnerability query.")
    analyze.add_argument(
        "--source-anchor-mode",
        choices=["timestamp", "error", "skip"],
        default="timestamp",
        help="How to handle an existing source anchor path.",
    )
    analyze.add_argument("--keep-temp", action="store_true")

    fresh = sub.add_parser("check-freshness", help="Check whether a repo has moved since analyzed commit")
    fresh.add_argument("--repo", required=True)
    fresh.add_argument("--analyzed-commit", required=True)
    fresh.add_argument("--ref")
    fresh.add_argument("--git-timeout", type=int, default=DEFAULT_REMOTE_GIT_TIMEOUT, help="Seconds per remote freshness git operation.")

    diff = sub.add_parser("diff", help="Emit changed-file and changed-area evidence between commits")
    diff.add_argument("--repo", required=True)
    diff.add_argument("--old-commit", required=True)
    diff.add_argument("--new-commit", required=True)
    diff.add_argument("--output")
    diff.add_argument("--sync-diff-output", help="Optional path for a sync-diff.json copy of the diff evidence")
    diff.add_argument("--keep-temp", action="store_true")
    diff.add_argument("--git-timeout", type=int, default=DEFAULT_REMOTE_GIT_TIMEOUT, help="Seconds for the local diff git operation.")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "analyze":
        analyze_repo(args)
    elif args.command == "check-freshness":
        check_freshness(args)
    elif args.command == "diff":
        diff_repo(args)
    else:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
