# LLM Wiki Agent

Cross-platform initializer and adapter for a personal LLM Wiki knowledge base.

Inspired by Andrej Karpathy's [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) concept: a source-backed, agent-friendly knowledge base that helps LLMs keep project context structured and reusable.

## Quick Start

```powershell
python -m src init --target C:\path\to\my-kb --dry-run
python -m src init --target C:\path\to\my-kb --confirm CREATE-KB
python -m src doctor --root C:\path\to\my-kb
```

The generated knowledge base keeps `.agents/skills/` as the canonical skill source and mirrors platform-specific assets for Codex, Claude Code, Trae, OpenCode, OpenClaw, and Hermes. Default initialization enables all six platforms; pass `--platform codex,opencode` or similar to choose a subset.

## Commands

```powershell
python -m src init --target C:\path\to\my-kb --dry-run
python -m src sync --root C:\path\to\my-kb --check
python -m src doctor --root C:\path\to\my-kb
python -m src upgrade --root C:\path\to\my-kb --dry-run
python -m src serve --root C:\path\to\my-kb --transport stdio
```

Install MCP support with `pipx install "llm-wiki-agent[mcp]"`.

See [docs/INSTALL.md](docs/INSTALL.md), [docs/MIGRATION.md](docs/MIGRATION.md), [docs/MCP_SERVER.md](docs/MCP_SERVER.md), and [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).
