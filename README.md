# LLM Wiki Agent

Cross-platform initializer and adapter for a personal LLM Wiki knowledge base, inspired by Andrej Karpathy's [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) concept: a source-backed, agent-friendly knowledge base that helps LLMs keep project context structured and reusable.

## What is LLM Wiki?

LLM Wiki is a personal knowledge management system designed for the AI era. Unlike traditional wikis, it is built from the ground up to be **agent-friendly** — every piece of knowledge is structured so that LLM agents (Claude Code, Codex, Trae, etc.) can efficiently read, query, and maintain your knowledge base.

### Core Concepts

- **Source-Backed**: Every knowledge entry is anchored to its original source material, ensuring traceability and trustworthiness.
- **Agent-First**: The knowledge base is structured with LLM consumption in mind — layered loading discipline (L0→L1→L2→L3) prevents context window bloat.
- **Cross-Platform**: A single knowledge base works across multiple AI coding agents through platform adapters.
- **Schema-Driven**: Templates and schemas enforce consistent structure across all knowledge entries.

### Knowledge Base Structure

```
my-knowledge-base/
├── AGENTS.md                 # Codex instruction file (auto-generated)
├── CLAUDE.md                 # Claude Code instruction file (auto-generated)
├── .trae/rules/project_rules.md  # Trae instruction file (auto-generated)
├── llm-wiki.yaml             # Knowledge base manifest & version metadata
├── .agents/skills/           # Canonical skill source (editable)
├── .claude/skills/           # Claude skill mirror
├── .codex/skills/            # Codex skill mirror
├── .trae/skills/             # Trae skill mirror
├── .opencode/skills/         # OpenCode skill mirror
├── .openclaw/skills/         # OpenClaw skill mirror
├── .hermes/skills/           # Hermes skill mirror
├── themes/                   # Themed knowledge (project/, domain/, etc.)
├── shared/                   # Cross-theme knowledge
├── schema/                   # Page templates and schema docs
├── index/                    # Navigation pages
├── inbox/                    # Unclassified material
├── sources/                  # Raw source anchors
└── outputs/                  # Generated outputs
```

## Installation

### pip (Recommended)

```bash
pip install llm-wiki-agent
```

### pipx (Isolated environment)

```bash
pipx install llm-wiki-agent
```

### uvx (Zero-install)

```bash
uvx llm-wiki-agent init --target ./my-kb --dry-run
```

### With MCP Server support

```bash
pip install "llm-wiki-agent[mcp]"
# or
pipx install "llm-wiki-agent[mcp]"
```

### From source

```bash
git clone https://github.com/petersetef1983/llm-wiki-agent.git
cd llm-wiki-agent
pip install -e .
```

## Quick Start

### 1. Initialize a new knowledge base

```bash
# Preview what will be created (dry-run)
llm-wiki init --target ./my-kb --dry-run

# Create the knowledge base
llm-wiki init --target ./my-kb --confirm CREATE-KB

# Initialize with specific platforms only
llm-wiki init --target ./my-kb --platform codex,claude,trae --confirm CREATE-KB
```

### 2. Check knowledge base health

```bash
llm-wiki doctor --root ./my-kb
```

### 3. Sync platform mirrors

```bash
# Check for drift between canonical skills and platform mirrors
llm-wiki sync --root ./my-kb --check

# Sync all platforms
llm-wiki sync --root ./my-kb
```

### 4. Upgrade knowledge base assets

```bash
# Preview upgrade actions
llm-wiki upgrade --root ./my-kb --dry-run

# Apply upgrades
llm-wiki upgrade --root ./my-kb --confirm UPGRADE-KB
```

## Commands Reference

### `llm-wiki init`

Initialize a new LLM Wiki knowledge base.

```bash
llm-wiki init --target <path> [options]
```

| Option | Description |
|--------|-------------|
| `--target TARGET` | Target directory for the knowledge base |
| `--platform PLATFORM` | Comma-separated platforms or `all` (default: `all`) |
| `--dry-run` | Print planned actions without writing files |
| `--confirm CREATE-KB` | Required write confirmation token |
| `--adopt-existing` | Add agent metadata/platform files to an existing KB |

### `llm-wiki sync`

Sync platform instruction files and skill mirrors.

```bash
llm-wiki sync --root <path> [options]
```

| Option | Description |
|--------|-------------|
| `--root ROOT` | Knowledge base root directory |
| `--platform PLATFORM` | Comma-separated platforms or `all` |
| `--check` | Check drift only, do not write |

### `llm-wiki doctor`

Run agent-kit health checks.

```bash
llm-wiki doctor --root <path> [options]
```

| Option | Description |
|--------|-------------|
| `--root ROOT` | Knowledge base root directory |
| `--platform PLATFORM` | Comma-separated platforms or `all` |

Diagnostics include:
- Manifest validation
- Asset drift detection
- Platform mirror drift
- Instruction file consistency
- Skill integrity checks

### `llm-wiki upgrade`

Check or apply bundled runtime asset upgrades.

```bash
llm-wiki upgrade --root <path> [options]
```

| Option | Description |
|--------|-------------|
| `--root ROOT` | Knowledge base root directory |
| `--dry-run` | Print planned upgrade actions without writing files |
| `--confirm UPGRADE-KB` | Required write confirmation token |
| `--force-conflicts` | Overwrite conflicting canonical skill files |

### `llm-wiki serve`

Expose an LLM Wiki knowledge base as an MCP server.

```bash
llm-wiki serve --root <path> [options]
```

| Option | Description |
|--------|-------------|
| `--root ROOT` | Knowledge base root directory |
| `--transport {stdio,http}` | MCP transport protocol (default: `stdio`) |
| `--host HOST` | HTTP host (default: `127.0.0.1`) |
| `--port PORT` | HTTP port (default: `8765`) |
| `--path PATH` | HTTP MCP endpoint path (default: `/mcp`) |
| `--readonly` | Hide write tools, expose read-only MCP tools only |
| `--allow-remote-http` | Allow binding to non-loopback hosts (use with caution) |

MCP tools exposed:
- **Read**: `kb_status`, `kb_search`, `kb_list_pages`, `kb_read_page`, `kb_filter_pages`, `kb_aggregate`
- **Write**: `kb_record_query`, `kb_create_inbox_note` (require `confirm="WRITE-KB"`)

MCP resources:
- `llm-wiki://manifest`
- `llm-wiki://index/home`
- `llm-wiki://page/{path}`

## Supported Platforms

| Platform | Instruction File | Skill Mirror | MCP Config |
|----------|-----------------|-------------|------------|
| **Codex** | `AGENTS.md` | `.codex/skills/` | — |
| **Claude Code** | `CLAUDE.md` | `.claude/skills/` | — |
| **Trae** | `.trae/rules/project_rules.md` | `.trae/skills/` | — |
| **OpenCode** | `.opencode/instructions.md` | `.opencode/skills/` | `opencode.json` |
| **OpenClaw** | `.openclaw/instructions.md` | `.openclaw/skills/` | `openclaw.plugin.json`, `mcp.yaml` |
| **Hermes** | `.hermes/instructions.md` | `.hermes/skills/` | `.hermes/config.yaml` |

## Skills

The knowledge base includes 6 built-in skills (located in `.agents/skills/`):

| Skill | Description |
|-------|-------------|
| **ingest** | Bring new material into durable wiki knowledge |
| **query** | Answer from existing wiki, graph, outputs, and evidence |
| **lint** | Quality audit and consistency checks |
| **reset** | Reset knowledge base state |
| **bootstrap** | Self-initialization and setup |
| **project-reverse** | Reverse-engineer and document existing projects |

## MCP Client Configuration

For stdio MCP clients (e.g., Claude Desktop, Cursor):

```json
{
  "mcpServers": {
    "llm-wiki": {
      "command": "llm-wiki",
      "args": ["serve", "--root", "/path/to/my-kb", "--transport", "stdio"]
    }
  }
}
```

For HTTP-capable clients:

```
http://127.0.0.1:8765/mcp
```

## Development

### Build from source

```bash
git clone https://github.com/petersetef1983/llm-wiki-agent.git
cd llm-wiki-agent
pip install build
python -m build
```

### Publish to PyPI

```bash
pip install twine
twine check dist/*
twine upload dist/*
```

## Documentation

- [Installation Guide](docs/INSTALL.md)
- [MCP Server Guide](docs/MCP_SERVER.md)
- [Migration Guide](docs/MIGRATION.md)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)

## License

MIT License. See [LICENSE](LICENSE) for details.
