---
name: reset
description: Reset the LLM Wiki knowledge base to its empty operating skeleton by clearing themes, wiki content, sources, outputs, shared canonical pages, inbox material, indexes, and activity logs while preserving schema, tools, AGENTS instructions, and agent skills. Use when the agent is asked to wipe, clear, reinitialize, reset, or start over with the whole knowledge base rather than ingest, query, or lint existing knowledge.
---

# Reset

Use this skill only for whole-knowledge-base reset requests. This is a destructive maintenance mode, not a normal ingest or cleanup flow.

## Safety Rules

1. Never execute a reset implicitly.
2. Explain what will be removed and what will be preserved.
3. Run a dry run first.
4. Require explicit user confirmation before applying the reset.
5. Do not manually edit generated platform skill mirrors; sync them from `.agents/skills/` after changing this skill.

## Skeleton Definition

Preserve:

- `AGENTS.md` and other root operating files.
- `schema/`.
- `tools/`.
- `.agents/skills/` and generated platform mirrors under `.claude/skills/`, `.codex/skills/`, `.trae/skills/`, `.opencode/skills/`, `.openclaw/skills/`, and `.hermes/skills/`.
- Top-level containers: `themes/`, `shared/`, `index/`, `inbox/`.
- Theme category directories: `themes/general/`, `themes/project/`, `themes/research/`.
- Stable shared category directories: `shared/entities/`, `shared/concepts/`, `shared/patterns/`, `shared/methods/`, `shared/tools/`, `shared/glossary/`.

Remove:

- All concrete themes under `themes/general/`, `themes/project/`, and `themes/research/`.
- All theme-local `README.md`, `meta.md`, `sources/`, `wiki/`, `stack/`, and `outputs/` content by removing the concrete theme directories.
- Shared canonical pages and extra shared folders.
- Inbox contents.
- Index page contents.
- Root `log.md`.

Recreate:

- Empty theme category directories.
- Stable shared category directories with minimal `README.md` placeholders.
- Minimal `index/home.md`, `index/themes.md`, `index/recent-updates.md`, and `index/cross-theme-map.md`.
- Empty inbox staging directories: `to-be-filed/`, `review/`, `requirements/`, `papers/`, `articles/`, `images/`, `videos/`, `audio/`, and `source-code/`.

## Workflow

1. Inspect the repository root and confirm it is the intended LLM Wiki root.
2. Run:

   ```powershell
   python .agents/skills/reset/scripts/kb_reset.py --root . --dry-run
   ```

3. Review the printed plan with the user. If the request is still clear, ask for explicit confirmation.
4. Apply only after confirmation:

   ```powershell
   python .agents/skills/reset/scripts/kb_reset.py --root . --confirm RESET-KB
   ```

5. Sync skill mirrors if `.agents/skills/` changed:

   ```powershell
   python tools/sync_agent_skills.py
   python tools/sync_agent_skills.py --check
   ```

6. Run a structure check if the lint skill is available.

## Helper

Use `scripts/kb_reset.py` for the reset. It centralizes path allowlists, dry-run behavior, confirmation checks, and skeleton recreation.
