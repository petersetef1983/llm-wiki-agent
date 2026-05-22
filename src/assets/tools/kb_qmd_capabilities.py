#!/usr/bin/env python3
"""Shared qmd capability detection and execution helpers."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


WINDOWS_VECTOR_DISABLED_REASON = (
    "Windows native qmd vector/hybrid mode is disabled because qmd embed can hang when sqlite-vec cannot load. "
    "Use BM25 search on Windows, or run qmd vector/hybrid from WSL2/Linux."
)
DEFAULT_MCP_URL = "http://localhost:8181"
DEFAULT_MCP_TIMEOUT = 5


def path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def is_windows_native() -> bool:
    return sys.platform == "win32"


def qmd_js_candidates() -> list[Path]:
    candidates: list[Path] = []
    resolved = shutil.which("qmd")
    if resolved:
        cmd_path = Path(resolved).resolve()
        for parent in [cmd_path.parent, *cmd_path.parents]:
            js = parent / "node_modules" / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"
            if path_exists(js):
                candidates.append(js)
                break
    nvm_root = Path(os.environ.get("NVM_HOME", Path.home() / "AppData" / "Local" / "nvm"))
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    module_roots = [
        nvm_root / "node_modules",
        Path("C:/nvm4w/nodejs/node_modules"),
        appdata / "npm" / "node_modules",
        Path.home() / "AppData" / "Roaming" / "npm" / "node_modules",
    ]
    for module_root in module_roots:
        js = module_root / "@tobilu" / "qmd" / "dist" / "cli" / "qmd.js"
        if js not in candidates:
            candidates.append(js)
    return candidates


def qmd_path() -> str | None:
    resolved = shutil.which("qmd")
    if resolved:
        return resolved
    for candidate in qmd_js_candidates():
        if path_exists(candidate):
            return str(candidate)
    return None


def qmd_command() -> list[str]:
    resolved = shutil.which("qmd")
    if resolved and not is_windows_native():
        return [resolved]
    for candidate in qmd_js_candidates():
        if path_exists(candidate):
            return ["node", str(candidate)]
    if resolved:
        return [resolved]
    return ["qmd"]


def run_native_qmd(root: Path, args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*qmd_command(), *args],
        cwd=str(root),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def run_probe(root: Path, args: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str] | None:
    try:
        return run_native_qmd(root, args, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def windows_to_wsl_path(root: Path) -> str:
    explicit = os.environ.get("QMD_WSL_ROOT")
    if explicit:
        return explicit
    resolved = str(root.resolve())
    if len(resolved) >= 2 and resolved[1] == ":":
        drive = resolved[0].lower()
        rest = resolved[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    return resolved.replace("\\", "/")


def wsl_base_command() -> list[str] | None:
    wsl = shutil.which("wsl")
    if not wsl:
        return None
    command = [wsl]
    distro = os.environ.get("QMD_WSL_DISTRO")
    if distro:
        command.extend(["-d", distro])
    return command


def run_wsl_script(script: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    base = wsl_base_command()
    if base is None:
        return subprocess.CompletedProcess(["wsl"], 127, "", "wsl executable not found")
    completed = subprocess.run(
        [*base, "bash", "-lc", script],
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        decode_process_output(completed.stdout),
        decode_process_output(completed.stderr),
    )


def decode_process_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.replace("\x00", "")
    for encoding in ["utf-8", "utf-16le", "gb18030"]:
        try:
            text = value.decode(encoding)
            if encoding != "utf-8" or "\x00" not in text:
                return text.replace("\x00", "")
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace").replace("\x00", "")


def run_wsl_qmd(root: Path, args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    wsl_root = windows_to_wsl_path(root)
    quoted_args = " ".join(shlex.quote(item) for item in args)
    script = f"cd {shlex.quote(wsl_root)} && qmd {quoted_args}"
    try:
        return run_wsl_script(script, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["wsl", "qmd", *args], 1, "", str(exc))


def run_wsl_qmd_embed(root: Path, extra_args: list[str] | None = None, timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    extra_args = extra_args or []
    wsl_root = windows_to_wsl_path(root)
    quoted_embed = " ".join(["qmd", "embed", *(shlex.quote(item) for item in extra_args)])
    script = f"cd {shlex.quote(wsl_root)} && qmd update && {quoted_embed}"
    try:
        return run_wsl_script(script, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["wsl", "qmd", "embed", *extra_args], 1, "", str(exc))


def mcp_url() -> str:
    return os.environ.get("QMD_MCP_URL", DEFAULT_MCP_URL).rstrip("/")


def mcp_timeout() -> int:
    try:
        return int(os.environ.get("QMD_MCP_TIMEOUT", str(DEFAULT_MCP_TIMEOUT)))
    except ValueError:
        return DEFAULT_MCP_TIMEOUT


def wsl_probe_timeout() -> int:
    try:
        return int(os.environ.get("QMD_WSL_PROBE_TIMEOUT", "5"))
    except ValueError:
        return 5


def http_json(url: str, payload: dict[str, Any], timeout: int) -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
        try:
            return response.status, json.loads(raw)
        except json.JSONDecodeError:
            return response.status, raw


def mcp_rpc(method: str, params: dict[str, Any] | None = None, timeout: int | None = None) -> tuple[int, Any]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    return http_json(f"{mcp_url()}/mcp", payload, timeout or mcp_timeout())


def _tool_names(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("result") or payload
    tools = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(tools, list):
        return []
    names = []
    for tool in tools:
        if isinstance(tool, dict) and tool.get("name"):
            names.append(str(tool["name"]))
    return names


def _best_query_tool(names: list[str], want_vector: bool) -> str | None:
    preferred = ["query", "deep_search", "qmd_query", "qmd_deep_search"]
    if want_vector:
        preferred = ["query", "vector_search", "qmd_vector_search", "deep_search", "qmd_deep_search"]
    lowered = {name.lower(): name for name in names}
    for name in preferred:
        if name in lowered:
            return lowered[name]
    for name in names:
        lower = name.lower()
        if "query" in lower or "search" in lower:
            return name
    return None


def probe_mcp_http() -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "bm25_available": False,
        "vector_available": False,
        "hybrid_available": False,
        "mcp_http_url": mcp_url(),
        "mcp_query_endpoint": None,
        "mcp_query_tool": None,
        "error": None,
    }
    timeout = mcp_timeout()
    try:
        status, _payload = http_json(f"{mcp_url()}/query", {"query": "__kb_capability_probe__", "n": 1}, timeout)
        if status == 200:
            result.update(
                {
                    "available": True,
                    "bm25_available": True,
                    "vector_available": True,
                    "hybrid_available": True,
                    "mcp_query_endpoint": "/query",
                }
            )
            return result
    except Exception as exc:
        result["error"] = str(exc)

    try:
        mcp_rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "kb-qmd-capability-probe", "version": "1"},
            },
            timeout,
        )
    except Exception:
        pass

    try:
        status, payload = mcp_rpc("tools/list", {}, timeout)
        names = _tool_names(payload)
        tool = _best_query_tool(names, want_vector=True)
        if status == 200 and tool:
            result.update(
                {
                    "available": True,
                    "bm25_available": True,
                    "vector_available": True,
                    "hybrid_available": True,
                    "mcp_query_endpoint": "/mcp",
                    "mcp_query_tool": tool,
                    "mcp_tools": names,
                    "error": None,
                }
            )
    except Exception as exc:
        result["error"] = str(exc)
    return result


def run_mcp_http_search(
    query: str,
    *,
    top: int,
    want_vector: bool,
    json_output: bool,
    timeout: int = 120,
    caps: dict[str, Any] | None = None,
) -> subprocess.CompletedProcess[str]:
    caps = caps or probe_mcp_http()
    try:
        if caps.get("mcp_query_endpoint") == "/query":
            status, payload = http_json(f"{mcp_url()}/query", {"query": query, "n": top}, timeout)
            stdout = json.dumps(payload, ensure_ascii=False) if json_output else str(payload)
            return subprocess.CompletedProcess(["qmd-mcp-http", "/query", query], 0 if status == 200 else 1, stdout, "")
        tool = caps.get("mcp_query_tool") or _best_query_tool(list(caps.get("mcp_tools") or []), want_vector=want_vector)
        if not tool:
            return subprocess.CompletedProcess(["qmd-mcp-http", query], 1, "", "No query-capable MCP tool was detected")
        arguments = {"query": query, "n": top}
        status, payload = mcp_rpc("tools/call", {"name": tool, "arguments": arguments}, timeout)
        stdout = json.dumps(payload, ensure_ascii=False) if json_output else _mcp_payload_to_text(payload)
        return subprocess.CompletedProcess(["qmd-mcp-http", str(tool), query], 0 if status == 200 else 1, stdout, "")
    except Exception as exc:
        return subprocess.CompletedProcess(["qmd-mcp-http", query], 1, "", str(exc))


def _mcp_payload_to_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return str(payload)
    result = payload.get("result") or payload
    content = result.get("content") if isinstance(result, dict) else None
    if isinstance(content, list):
        texts = [str(item.get("text")) for item in content if isinstance(item, dict) and item.get("text")]
        if texts:
            return "\n".join(texts)
    return json.dumps(payload, ensure_ascii=False)


def probe_native(root: Path) -> dict[str, Any]:
    caps: dict[str, Any] = {
        "native_qmd_path": qmd_path(),
        "native_qmd_command": qmd_command() if qmd_path() else None,
        "bm25_available": False,
        "vector_available": False,
        "hybrid_available": False,
        "native_status": None,
        "native_error": None,
    }
    if not qmd_path():
        return caps
    status = run_probe(root, ["status", "--json"], timeout=30)
    if status is not None:
        caps["native_status_exit_code"] = status.returncode
        caps["native_status_stderr"] = (status.stderr or "").strip()
        caps["native_status"] = (status.stdout or "").strip()
    probe = run_probe(root, ["search", "__kb_capability_probe__", "-n", "1"], timeout=15)
    if probe is not None:
        caps["native_bm25_probe_exit_code"] = probe.returncode
        caps["native_bm25_probe_stderr"] = (probe.stderr or "").strip()
        caps["bm25_available"] = probe.returncode == 0
    if caps["bm25_available"] and not is_windows_native():
        vector_probe = run_probe(root, ["vsearch", "__kb_capability_probe__", "--json", "-n", "1"], timeout=20)
        caps["native_vector_probe_exit_code"] = vector_probe.returncode if vector_probe is not None else None
        if vector_probe is not None:
            caps["native_vector_probe_stderr"] = (vector_probe.stderr or "").strip()
        caps["vector_available"] = bool(vector_probe and vector_probe.returncode == 0)
        caps["hybrid_available"] = caps["vector_available"]
    return caps


def probe_wsl_cli(root: Path) -> dict[str, Any]:
    caps: dict[str, Any] = {
        "available": False,
        "bm25_available": False,
        "vector_available": False,
        "hybrid_available": False,
        "wsl_available": bool(wsl_base_command()),
        "wsl_root": windows_to_wsl_path(root),
        "wsl_error": None,
    }
    if not caps["wsl_available"]:
        return caps
    try:
        version = run_wsl_script("command -v qmd >/dev/null 2>&1 && qmd --version", timeout=wsl_probe_timeout())
    except Exception as exc:
        caps["wsl_error"] = str(exc)
        return caps
    caps["wsl_probe_exit_code"] = version.returncode
    caps["wsl_probe_stderr"] = (version.stderr or "").strip()
    if version.returncode == 0:
        caps.update({"available": True, "bm25_available": True, "vector_available": True, "hybrid_available": True})
    return caps


def detect_qmd_capability(root: Path) -> dict[str, Any]:
    root = root.resolve()
    native = probe_native(root)
    mcp = probe_mcp_http() if is_windows_native() else {"available": False}
    if is_windows_native() and not mcp.get("vector_available"):
        wsl = probe_wsl_cli(root)
    else:
        wsl = {
            "available": False,
            "wsl_available": bool(wsl_base_command()) if is_windows_native() else False,
            "wsl_root": windows_to_wsl_path(root) if is_windows_native() else None,
        }

    capability_mode = "none"
    execution_paths: list[str] = []
    bm25_available = False
    vector_available = False
    hybrid_available = False
    degraded_reason = None

    if native.get("bm25_available"):
        capability_mode = "native_bm25"
        execution_paths.append("native_bm25")
        bm25_available = True
        if native.get("vector_available"):
            capability_mode = "native_full"
            execution_paths.append("native_vector")
            vector_available = True
            hybrid_available = True

    if mcp.get("vector_available"):
        capability_mode = "wsl_http_query" if capability_mode == "none" else f"{capability_mode}+wsl_http_query"
        execution_paths.append("wsl_http_query")
        bm25_available = True
        vector_available = True
        hybrid_available = True
        degraded_reason = None
    elif wsl.get("vector_available"):
        capability_mode = "wsl_cli_query" if capability_mode == "none" else f"{capability_mode}+wsl_cli_query"
        execution_paths.append("wsl_cli_query")
        bm25_available = True
        vector_available = True
        hybrid_available = True
        degraded_reason = None
    elif bm25_available and is_windows_native():
        degraded_reason = "BM25 search available; vector/hybrid requires WSL2 qmd HTTP daemon or WSL2 qmd CLI."
    elif bm25_available:
        degraded_reason = "BM25 search is available; qmd vector/hybrid capability was not detected."

    status = "ok" if hybrid_available else ("degraded" if bm25_available else "missing")
    return {
        "schema_version": "kb-qmd-capability.v1",
        "root": str(root),
        "platform": sys.platform,
        "windows_native": is_windows_native(),
        "status": status,
        "capability_mode": capability_mode,
        "execution_paths": execution_paths,
        "bm25_available": bm25_available,
        "vector_available": vector_available,
        "hybrid_available": hybrid_available,
        "degraded_reason": degraded_reason,
        "native": native,
        "mcp_http": mcp,
        "mcp_http_url": mcp_url(),
        "wsl": wsl,
        "wsl_available": bool(wsl.get("available")),
        "wsl_executable_available": bool(wsl.get("wsl_available")),
        "wsl_root": wsl.get("wsl_root"),
        "workflow_capabilities": [
            "query.search",
            "synthesize.match-assets",
            "synthesize.check-license",
            "synthesize.assess-reuse",
            "synthesize.generate-outputs",
        ],
    }
