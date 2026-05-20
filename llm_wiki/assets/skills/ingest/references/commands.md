# Ingest Commands

Use the first available Python command in this order: `KB_PYTHON`, `python`, `py -3`, `python3`, then `conda run -n llm-wiki python` only as a fallback.

Every helper appends an activity record to `log.md`.

## Inventory

Use when destination scope is unclear.

```bash
<PYTHON_CMD> .agents/skills/ingest/scripts/kb_ingest_helper.py --root . inventory
<PYTHON_CMD> .agents/skills/ingest/scripts/kb_ingest_helper.py --root . inventory --format json
```

## Suggest Theme Directory

Use only after deciding a new theme may be needed.

```bash
<PYTHON_CMD> .agents/skills/ingest/scripts/kb_ingest_helper.py --root . suggest-theme-dir --category general --title "LLM Agent Skills"
```

## Create Theme

Use only after deciding no existing theme or shared location fits.

```bash
<PYTHON_CMD> .agents/skills/ingest/scripts/kb_ingest_helper.py --root . create-theme --category research --title "Agent Observability"
```

## Extract Document

Use when a file or URL needs a markdown/json evidence artifact before wiki maintenance.

```bash
<PYTHON_CMD> .agents/skills/ingest/scripts/kb_ingest_helper.py --root . extract-document --input inbox/to-be-filed/example.pdf --output themes/general/00-topic/outputs/document-intake/example.extracted.md --format markdown
```

Notes:

- `markitdown` is the primary converter.
- Local video may require `ffmpeg`.
- URL transcript fallback depends on available transcript tooling.
- The artifact is evidence only; the LLM still updates the wiki.

## Project Reverse Git Analysis

Use Graphify first when a GitHub, GitLab, internal Git service, or local Git repository needs structural graph evidence. Then use `project-reverse` for API registry, configuration, build/deploy, data/storage, reuse scoring, freshness, and diff evidence. `ingest` compiles both evidence layers into durable wiki pages.

## Graphify Structural Graph Evidence

```bash
<PYTHON_CMD> tools/kb_graphify_bridge.py status --root .
```

Run Graphify extraction:

```bash
<PYTHON_CMD> tools/kb_graphify_bridge.py extract \
  --repo <git-url-or-local-path> \
  --theme themes/project/NN-repo \
  --backend ollama \
  --sensitivity internal \
  --retention review \
  --root .
```

Update an existing graph:

```bash
<PYTHON_CMD> tools/kb_graphify_bridge.py update \
  --theme themes/project/NN-repo \
  --root .
```

Register a project graph and produce cross-project structural evidence:

```bash
<PYTHON_CMD> tools/kb_graphify_bridge.py global-add \
  --theme themes/project/NN-repo \
  --tag project-repo \
  --root .
<PYTHON_CMD> tools/kb_graphify_bridge.py global-report --root .
```

Graph query helpers:

```bash
<PYTHON_CMD> tools/kb_graphify_bridge.py query --theme themes/project/NN-repo --question "what connects Trigger and Function?" --root .
<PYTHON_CMD> tools/kb_graphify_bridge.py path --theme themes/project/NN-repo --source Trigger --target Function --root .
<PYTHON_CMD> tools/kb_graphify_bridge.py explain --theme themes/project/NN-repo --concept Engine --root .
```

Notes:

- Graphify output lives under `outputs/document-intake/graphify/` and is evidence only.
- Do not copy full repository checkouts, `graphify-cache/`, `graph.html`, or MCP server state into durable wiki pages.
- Graphify findings are structural routing hints until `ingest` confirms them in durable wiki pages, `shared/`, or engineering outputs.
- If Graphify is not installed or its backend is unavailable, continue with `project-reverse` and record the missing graph evidence as a gap.

```bash
<PYTHON_CMD> .agents/skills/project-reverse/scripts/project_reverse_helper.py analyze \
  --repo https://github.com/iii-hq/iii \
  --output themes/project/01-iii/outputs/document-intake/project-reverse-analysis.json \
  --source-anchor themes/project/01-iii/sources/project-reverse-source-anchor.md \
  --write-focused-artifacts
```

Optional ref:

```bash
<PYTHON_CMD> .agents/skills/project-reverse/scripts/project_reverse_helper.py analyze \
  --repo <git-url-or-local-path> \
  --ref <branch-tag-or-sha> \
  --output themes/project/NN-repo/outputs/document-intake/project-reverse-analysis.json \
  --source-anchor themes/project/NN-repo/sources/project-reverse-source-anchor.md \
  --source-anchor-mode timestamp \
  --write-focused-artifacts
```

Freshness check:

```bash
<PYTHON_CMD> .agents/skills/project-reverse/scripts/project_reverse_helper.py check-freshness \
  --repo <git-url-or-local-path> \
  --analyzed-commit <sha> \
  --git-timeout 30
```

Incremental diff evidence:

```bash
<PYTHON_CMD> .agents/skills/project-reverse/scripts/project_reverse_helper.py diff \
  --repo <git-url-or-local-path> \
  --old-commit <old-sha> \
  --new-commit <new-sha> \
  --output themes/project/NN-repo/outputs/document-intake/project-reverse-diff.json \
  --sync-diff-output themes/project/NN-repo/outputs/document-intake/sync-diff.json \
  --git-timeout 30
```

Notes:

- The analyzer may temporarily clone the full repository for current-run analysis.
- Do not save full source code, archives, or checkouts under `sources/`.
- `sources/` should contain only the source anchor, not project source files.
- The LLM must still write durable project wiki pages, API registry, graph links, `outputs/sync-status.md`, and engineering outputs.
- If a source anchor already exists, timestamp mode writes a sibling anchor rather than overwriting the existing anchor.
- Diff evidence includes `affected_pages` and `next_update_scope`; update only those durable pages unless review finds wider drift.
- The legacy `extract-git-repo` helper remains available for lightweight snapshots, but full project ingest should use `project-reverse`.

## Runtime Query And Freshness Support

Use after durable wiki or frontmatter changes.

```bash
<PYTHON_CMD> tools/kb_query_index.py index --root .
<PYTHON_CMD> tools/kb_source_registry.py init --root .
<PYTHON_CMD> tools/kb_freshness_check.py check --root . --timeout 60 --git-timeout 30 --write-report outputs/freshness/latest.json
<PYTHON_CMD> tools/kb_search_bridge.py status --root .
<PYTHON_CMD> tools/kb_search_bridge.py index --root . --kind lexical
```

If qmd is installed and status indicates the search index needs setup:

```bash
<PYTHON_CMD> tools/kb_search_bridge.py init --root . --name wiki --context "LLM Wiki 个人知识库：项目、shared graph、技术资产和工程输出"
<PYTHON_CMD> tools/kb_search_bridge.py search --root . --query "告警分级分类" --mode auto --top 10
```

On native Windows, keep qmd in BM25 mode. Do not run `qmd embed`, `qmd vsearch`, or `qmd query` from ingest; use WSL2/Linux if vector or hybrid search is required.

Optional WSL2 vector refresh:

```bash
<PYTHON_CMD> tools/kb_search_bridge.py index --root . --kind vector
<PYTHON_CMD> tools/kb_search_bridge.py search --root . --query "持久记忆 AI 代理" --mode vector --top 10 --allow-fallback
```

Set `QMD_MCP_URL` for a WSL2 qmd HTTP/MCP daemon, or let the bridge fall back to WSL2 CLI when `wsl` and `qmd` are available.

## Cross-Project Reuse Scan

Use after compiling a new project theme or before updating a target project's asset-match brief.

```bash
<PYTHON_CMD> .agents/skills/ingest/scripts/kb_ingest_helper.py --root . scan-reuse --format json
```

Notes:

- This command is read-only; it does not promote assets or edit match briefs.
- The output lists shared assets, reuse candidate files, target match briefs, missing match briefs, unpromoted candidates, unmatched assets, and broken shared asset references.
- The LLM still decides whether a candidate should become `shared/assets/` or remain project-local.

## Append Update

Use after a meaningful durable wiki change.

```bash
<PYTHON_CMD> .agents/skills/ingest/scripts/kb_ingest_helper.py --root . append-update --message "Updated prompt engineering implementation guidance."
```
