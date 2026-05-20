# LLM Wiki MCP Server

`llm-wiki serve` exposes an initialized LLM Wiki knowledge base through MCP tools and resources.

## Install

The core package keeps MCP as an optional dependency:

```powershell
pipx install "llm-wiki-agent[mcp]"
```

or:

```powershell
uvx --from "llm-wiki-agent[mcp]" llm-wiki serve --root C:\path\to\my-kb
```

Without the `mcp` extra, `init`, `sync`, `doctor`, and `upgrade` still work, while `serve` prints an install hint.

## Run

Stdio is the default and is the preferred local agent integration:

```powershell
llm-wiki serve --root C:\path\to\my-kb --transport stdio
```

Local Streamable HTTP is available for clients that support it:

```powershell
llm-wiki serve --root C:\path\to\my-kb --transport http --host 127.0.0.1 --port 8765 --path /mcp
```

HTTP binds to loopback by default. Binding to another host requires `--allow-remote-http` and should only be used on trusted networks.

## Tools

Read tools:

- `kb_status`
- `kb_search`
- `kb_list_pages`
- `kb_read_page`
- `kb_filter_pages`
- `kb_aggregate`

Write tools:

- `kb_record_query`
- `kb_create_inbox_note`

Write tools are deliberately narrow and require `confirm="WRITE-KB"`. Run with `--readonly` to hide write tools entirely.

## Resources

- `llm-wiki://manifest`
- `llm-wiki://index/home`
- `llm-wiki://page/{path}`

Runtime directories such as `.agents`, `.claude`, `.codex`, `.trae`, `.opencode`, `.openclaw`, `.hermes`, `.qmd`, and `.query-index` are not exposed as readable pages.

## Client Configuration

For stdio MCP clients, use the installed `llm-wiki` command:

```json
{
  "mcpServers": {
    "llm-wiki": {
      "command": "llm-wiki",
      "args": ["serve", "--root", "C:\\path\\to\\my-kb", "--transport", "stdio"]
    }
  }
}
```

For HTTP-capable clients, point the client at:

```text
http://127.0.0.1:8765/mcp
```

The server does not write MCP runtime state into the knowledge base.

## Platform Notes

`llm-wiki init` generates local MCP configuration for OpenCode, OpenClaw, and Hermes:

- OpenCode: `opencode.json` starts `llm-wiki serve --root . --transport stdio` and points to `.opencode/instructions.md`.
- OpenClaw: `.openclaw/openclaw.plugin.json` and `.openclaw/mcp.yaml` declare the same stdio server and `.openclaw/instructions.md`.
- Hermes: `.hermes/config.yaml` declares the same stdio server and `.hermes/instructions.md`.

OpenClaw and Hermes native marketplace/plugin packaging is intentionally left for a later release; the v1 integration is project-local MCP plus generated instructions.
