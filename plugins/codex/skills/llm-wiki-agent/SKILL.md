---
name: llm-wiki-agent
description: Initialize, sync, diagnose, and upgrade LLM Wiki knowledge bases through the packaged llm-wiki-agent CLI. Use when working with the Codex Plugin distribution skeleton for LLM Wiki.
---

# LLM Wiki Agent

Use the Python package as the canonical runtime:

```powershell
pipx install llm-wiki-agent
llm-wiki init --target <kb-root> --confirm CREATE-KB
```

For existing knowledge bases:

```powershell
llm-wiki init --target <kb-root> --adopt-existing --confirm CREATE-KB
llm-wiki sync --root <kb-root> --check
llm-wiki doctor --root <kb-root>
llm-wiki upgrade --root <kb-root> --dry-run
```

Keep `.agents/skills/` as the editable skill source. Treat `.codex/skills/`, `.claude/skills/`, `.trae/skills/`, `.opencode/skills/`, `.openclaw/skills/`, and `.hermes/skills/` as generated mirrors.
