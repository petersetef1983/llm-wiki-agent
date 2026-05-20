# LLM Wiki Agent Codex Plugin

This directory is the Codex plugin packaging skeleton for the LLM Wiki Agent.

The Python CLI remains the canonical installer:

```powershell
pipx install llm-wiki-agent
llm-wiki init --target C:\path\to\my-kb
```

The plugin skeleton exists so the same agent assets can later be published through Codex plugin distribution. Marketplace publishing automation is intentionally out of scope for this iteration. The Python package now generates project-local assets for Codex, Claude Code, Trae, OpenCode, OpenClaw, and Hermes.

Current contents:

- `.codex-plugin/plugin.json`: Codex plugin manifest skeleton.
- `skills/llm-wiki-agent/SKILL.md`: Codex-facing wrapper that points back to the packaged CLI.

Optional MCP server support is provided by the Python package:

```powershell
pipx install "llm-wiki-agent[mcp]"
llm-wiki serve --root C:\path\to\my-kb --transport stdio
```

For HTTP-capable local clients:

```powershell
llm-wiki serve --root C:\path\to\my-kb --transport http --host 127.0.0.1 --port 8765 --path /mcp
```

The MCP server does not write runtime state into the KB. Write tools are limited to `log.md` and new `inbox/to-be-filed/` notes, and require `confirm="WRITE-KB"`.

OpenCode, OpenClaw, and Hermes support is provided through generated MCP configuration and instruction files in the initialized KB, not through separate native plugin packages in this release.
