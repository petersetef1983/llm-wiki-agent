# Migration

Use `--adopt-existing` for an existing LLM Wiki root. This adds agent-kit metadata and platform adapters without touching user knowledge under `themes/`, `shared/`, `index/`, or `inbox/`.

```powershell
python -m llm_wiki init --target kb --adopt-existing --dry-run
python -m llm_wiki init --target kb --adopt-existing --confirm CREATE-KB
python -m llm_wiki doctor --root kb
```

Default migration enables Codex, Claude Code, Trae, OpenCode, OpenClaw, and Hermes. Use `--platform` if the KB should expose only a subset of platform adapters.

After migration, edit `.agents/skills/` as the canonical skill source and regenerate platform mirrors with:

```powershell
python -m llm_wiki sync --root kb
```
