# Lint Checks And Commands

Use the first available Python command in this order: `KB_PYTHON`, `python`, `py -3`, `python3`, then `conda run -n llm-wiki python` only as a fallback.

Every lint run appends an activity record to `log.md`.

## Commands

Run all checks:

```bash
<PYTHON_CMD> .agents/skills/lint/scripts/kb_lint.py --root .
```

Run one scope:

```bash
<PYTHON_CMD> .agents/skills/lint/scripts/kb_lint.py --root . --scope structure
<PYTHON_CMD> .agents/skills/lint/scripts/kb_lint.py --root . --scope graph
<PYTHON_CMD> .agents/skills/lint/scripts/kb_lint.py --root . --scope knowledge
```

JSON output:

```bash
<PYTHON_CMD> .agents/skills/lint/scripts/kb_lint.py --root . --format json
```

Fail on warnings:

```bash
<PYTHON_CMD> .agents/skills/lint/scripts/kb_lint.py --root . --strict
```

Summary mode:

```bash
<PYTHON_CMD> .agents/skills/lint/scripts/kb_lint.py --root . --summary --summary-top 5
```

## Check List

`structure` checks:

- Required root directories.
- Root misresolution, including accidentally running helpers from the parent directory or creating nested `kb/` outputs.
- qmd search index health: missing qmd across native, WSL2 HTTP, and WSL2 CLI is `info: qmd_index_missing`; stale native status metadata is `info: qmd_index_stale`; vector absence is ignored unless `qmd.yml` explicitly sets `require_vector: true` or `vector_required: true`; configured but unreachable `QMD_MCP_URL` is `info: qmd_mcp_http_down`.
- Graphify bridge and runtime hygiene: missing `tools/kb_graphify_bridge.py`, misplaced `graphify-cache/`, misplaced `graph.html`, full Git checkouts under `sources/`, and broken global graph project references.
- Always-loaded `AGENTS.md` size budget: review over 1,000 estimated tokens, regression over 1,500 estimated tokens.
- Bootstrap skeleton `AGENTS.md` drift against the root contract.
- Configured platform skill mirrors drift against `.agents/skills/`.
- Oversized `SKILL.md` entry files that should move details into `references/`.
- Theme category directories.
- Theme `README.md`, `meta.md`, `sources/`, `wiki/`, `stack/`, `outputs/`.
- Theme type and required wiki entry pages.
- Dead wikilinks.
- Placeholder-heavy and empty markdown files.
- Missing entries in `index/themes.md`.

`graph` checks:

- Canonical node required frontmatter.
- Valid `node_type`.
- Technical asset required fields, including `license_compatibility`, and allowed `reuse_level`, `reuse_cost`, and `confidence` values.
- Broken `themes`, `source_pages`, `evidence_from`, and `related_*` references.
- Orphan canonical nodes with no inbound wikilinks.
- Body shared-node links missing from `related_*` fields.

`knowledge` checks:

- Canonical nodes that still look like templates.
- Canonical nodes without evidence/source chain.
- Thin output pages.
- Output pages without wiki/shared source links.
- Missing engineering and reuse output files.
- Graphify evidence completeness: `graphify-evidence.json` must have `source_id`, `sensitivity`, `retention`, `confidence`, `graph.json`, `GRAPH_REPORT.md`, and `graphify-source-anchor.md`.
- Stale pages where frontmatter `updated` is older than referenced source/evidence file time.
- Pages that mention conflict/contradiction without `contradicts` or open-question tracking.
- Duplicate or near-duplicate canonical node titles and aliases.
- `evidence_from` entries without body-level traceability.
- Engineering outputs that may be older than the wiki pages they compile.
- Project source freshness from `outputs/freshness/latest.json` and `outputs/sync-status.md`; stale projects produce `warning: project_stale`.
- Shared concept/pattern discoverability from `shared/*/README.md` and `index/technical-assets.md`.
- Theme README/wiki backlinks for shared concept/pattern nodes that declare the theme in frontmatter.
- `reuse-candidates.md` entries with `direct` or `adapt` reuse level that are not promoted or linked to `shared/assets/` warnings.
- `reuse-candidates.md` entries with `reference` reuse level that are not promoted info findings.
- `shared/assets/*.md` assets that are not referenced by any target project `asset-match-brief.md` info findings.
- `asset-match-brief.md` references to missing `shared/assets/*` error findings.

Semantic findings are reports only. Do not auto-repair them by inventing conclusions.
