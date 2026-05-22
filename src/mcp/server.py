from __future__ import annotations

from pathlib import Path
from typing import Any

from .service import LLMWikiService


INSTALL_HINT = (
    "MCP support requires the optional dependency. Install with "
    "`pipx install 'llm-wiki-agent[mcp]'` or run with "
    "`uvx --from 'llm-wiki-agent[mcp]' llm-wiki serve ...`."
)


def create_server(
    *,
    root: Path,
    readonly: bool = False,
    host: str = "127.0.0.1",
    port: int = 8765,
    path: str = "/mcp",
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised by CLI smoke tests.
        raise RuntimeError(INSTALL_HINT) from exc

    service = LLMWikiService(root, readonly=readonly)
    instructions = (
        "Expose an LLM Wiki personal knowledge base through safe MCP tools. "
        "Read tools may inspect markdown knowledge pages and indexes. "
        f"Write tools are limited and require confirm=\"WRITE-KB\". Root: {service.root}"
    )
    mcp = _new_fastmcp(FastMCP, host=host, port=port, path=path, instructions=instructions)

    @mcp.resource("llm-wiki://manifest")
    def manifest() -> str:
        """Return the raw llm-wiki.yaml manifest."""
        return service.manifest_text()

    @mcp.resource("llm-wiki://index/home")
    def index_home() -> str:
        """Return index/home.md from the knowledge base."""
        return service.index_home_text()

    @mcp.resource("llm-wiki://page/{page_path}")
    def page(page_path: str) -> str:
        """Return a safe markdown page by path relative to the KB root."""
        return service.page_text(page_path)

    @mcp.tool()
    def kb_status(include_platform_drift: bool = True, include_search_status: bool = True) -> dict[str, Any]:
        """Report root health, manifest drift, platform drift, and search capability."""
        return service.status(
            include_platform_drift=include_platform_drift,
            include_search_status=include_search_status,
        )

    @mcp.tool()
    def kb_search(query: str, mode: str = "auto", top: int = 10, allow_fallback: bool = True) -> dict[str, Any]:
        """Search the knowledge base through the packaged qmd bridge."""
        return service.search(query=query, mode=mode, top=top, allow_fallback=allow_fallback)

    @mcp.tool()
    def kb_list_pages(
        prefix: str = "",
        node_type: str = "",
        theme: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List indexed markdown pages, optionally filtered by prefix, node_type, or theme."""
        return service.list_pages(prefix=prefix, node_type=node_type, theme=theme, limit=limit, offset=offset)

    @mcp.tool()
    def kb_read_page(path: str, max_chars: int = 20_000) -> dict[str, Any]:
        """Read a markdown page by path relative to the KB root."""
        return service.read_page(path, max_chars=max_chars)

    @mcp.tool()
    def kb_filter_pages(filters: dict[str, str], limit: int = 50) -> dict[str, Any]:
        """Filter pages by frontmatter fields, for example {"node_type": "asset"}."""
        return service.filter_pages(filters=filters, limit=limit)

    @mcp.tool()
    def kb_aggregate(field: str, limit: int = 50) -> dict[str, Any]:
        """Aggregate indexed pages by one frontmatter field."""
        return service.aggregate(field=field, limit=limit)

    @mcp.tool()
    def kb_synthesize(target_theme: str, top: int = 20, search_mode: str = "auto", confirm: str = "") -> dict[str, Any]:
        """Run deterministic demand synthesis for a target theme; writes require confirm=\"WRITE-KB\"."""
        return service.synthesize(target_theme=target_theme, top=top, search_mode=search_mode, confirm=confirm)

    if not readonly:

        @mcp.tool()
        def kb_record_query(
            question: str,
            summary: str = "",
            themes: list[str] | None = None,
            answer_status: str = "",
            writeback_candidate: str = "",
            writeback_target: str = "",
            gaps: list[str] | None = None,
            status: str = "completed",
            confirm: str = "",
        ) -> dict[str, Any]:
            """Append a structured query activity entry to log.md."""
            return service.record_query(
                question=question,
                summary=summary,
                themes=themes,
                answer_status=answer_status,
                writeback_candidate=writeback_candidate,
                writeback_target=writeback_target,
                gaps=gaps,
                status=status,
                confirm=confirm,
            )

        @mcp.tool()
        def kb_create_inbox_note(
            title: str,
            content: str,
            source: str = "",
            tags: list[str] | None = None,
            confirm: str = "",
        ) -> dict[str, Any]:
            """Create a new markdown note under inbox/to-be-filed without overwriting files."""
            return service.create_inbox_note(
                title=title,
                content=content,
                source=source,
                tags=tags,
                confirm=confirm,
            )

    return mcp


def run_server(
    *,
    root: Path,
    transport: str = "stdio",
    readonly: bool = False,
    host: str = "127.0.0.1",
    port: int = 8765,
    path: str = "/mcp",
) -> None:
    server = create_server(root=root, readonly=readonly, host=host, port=port, path=path)
    if transport == "stdio":
        server.run(transport="stdio")
        return
    if transport == "http":
        server.run(transport="streamable-http")
        return
    raise ValueError(f"unsupported MCP transport: {transport}")


def _new_fastmcp(FastMCP: Any, *, host: str, port: int, path: str, instructions: str) -> Any:
    kwargs = {
        "instructions": instructions,
        "host": host,
        "port": port,
        "streamable_http_path": path,
        "stateless_http": True,
        "json_response": True,
    }
    try:
        return FastMCP("LLM Wiki", **kwargs)
    except TypeError:
        server = FastMCP("LLM Wiki", instructions=instructions)
        settings = getattr(server, "settings", None)
        if settings is not None:
            for key, value in kwargs.items():
                if key != "instructions" and hasattr(settings, key):
                    setattr(settings, key, value)
        return server
