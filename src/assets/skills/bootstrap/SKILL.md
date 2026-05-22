---
name: bootstrap
description: Create a complete LLM Wiki knowledge base through the packaged llm-wiki initializer. Use when the agent needs to initialize a brand-new KB with cross-platform instructions, schema, tools, canonical skills, mirrors, metadata, theme containers, shared directories, index pages, and inbox scaffolding.
---

# Bootstrap

Use this skill to create a new LLM Wiki from an empty directory. The package CLI is the single source of truth for initialization logic; this skill only provides the agent workflow and a compatibility helper.

Do not use it for clearing an existing knowledge base; use `reset` for that.

## Safety Rules

1. Never bootstrap implicitly.
2. Run a dry run first.
3. Require explicit confirmation before writing files.
4. Refuse to bootstrap an existing LLM Wiki root.
5. Refuse to bootstrap a directory with ordinary user files or unknown runtime content.

## Equivalent-Empty Directory

Treat a directory as bootstrap-safe when it is physically empty or contains only safe runtime directories:

- `.codex/`
- `.agents/`
- `.claude/`
- `.trae/`
- `.opencode/`
- `.openclaw/`
- `.hermes/`

Only ignore those directories when their contents are empty or recognized runtime/cache metadata. Refuse if they contain unknown user files.

## Workflow

1. Inspect the target directory.
2. Run:

   ```powershell
   python -m src init --target <target-dir> --dry-run
   ```

3. Review the planned created files and any ignored runtime directories.
4. Apply only after confirmation:

   ```powershell
   python -m src init --target <target-dir> --confirm CREATE-KB
   ```

5. In the newly bootstrapped knowledge base, verify:

   ```powershell
   python -m src sync --root <target-dir> --check
   ```

## Created Skeleton

The initializer copies packaged assets from `src/assets/` into the target directory. The created knowledge base includes:

- `AGENTS.md`
- `schema/`
- `tools/`
- `.agents/skills/`
- `.claude/skills/`
- `.codex/skills/`
- `.trae/skills/`
- `.opencode/skills/`
- `.openclaw/skills/`
- `.hermes/skills/`
- `CLAUDE.md`
- `.trae/rules/project_rules.md`
- `.opencode/instructions.md`
- `.openclaw/instructions.md`
- `.hermes/instructions.md`
- `opencode.json`
- `.openclaw/openclaw.plugin.json`
- `.openclaw/mcp.yaml`
- `.hermes/config.yaml`
- `.agents/templates/`
- `llm-wiki.yaml`
- `themes/general/`, `themes/project/`, `themes/research/`
- stable `shared/` category directories
- `index/` entry pages
- inbox staging directories: `to-be-filed/`, `review/`, `requirements/`, `papers/`, `articles/`, `images/`, `videos/`, `audio/`, and `source-code/`

## Helper

Use `scripts/kb_bootstrap.py` only when an older workflow expects the skill-local helper path. It delegates to `src.core.bootstrap`.

```powershell
python .agents/skills/bootstrap/scripts/kb_bootstrap.py create --root <target-dir> --dry-run
```

For asset maintenance, use the package commands:

```powershell
python -m src upgrade --root <kb-root> --dry-run
python -m src doctor --root <kb-root>
```
