from __future__ import annotations

import argparse
from pathlib import Path

from ..mcp.server import run_server


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def register_serve(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("serve", help="Expose an LLM Wiki knowledge base as an MCP server.")
    parser.add_argument("--root", default=".", help="Knowledge base root.")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio", help="MCP transport.")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host when --transport http is used.")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port when --transport http is used.")
    parser.add_argument("--path", default="/mcp", help="HTTP MCP endpoint path.")
    parser.add_argument("--readonly", action="store_true", help="Hide write tools and expose read-only MCP tools.")
    parser.add_argument(
        "--allow-remote-http",
        action="store_true",
        help="Allow HTTP binding to non-loopback hosts. Use only on trusted networks.",
    )
    parser.set_defaults(handler=run_serve)


def run_serve(args: argparse.Namespace) -> int:
    if args.transport == "http" and args.host not in LOOPBACK_HOSTS and not args.allow_remote_http:
        raise ValueError("HTTP transport binds to loopback by default; pass --allow-remote-http for non-loopback hosts")
    if args.transport == "http" and not args.path.startswith("/"):
        raise ValueError("--path must start with /")
    run_server(
        root=Path(args.root),
        transport=args.transport,
        readonly=args.readonly,
        host=args.host,
        port=args.port,
        path=args.path,
    )
    return 0
