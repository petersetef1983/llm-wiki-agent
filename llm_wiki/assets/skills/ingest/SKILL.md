---
name: ingest
description: Ingest raw materials into the LLM Wiki by preserving raw sources, converting sources to evidence artifacts when useful, and having the LLM update durable theme wiki pages, canonical graph links, and engineering outputs. Use when the agent needs to process inbox files, notes, PDFs, URLs, transcripts, recordings, videos, research materials, meeting notes, Git repositories, or any new evidence into persistent knowledge rather than answer a one-off question.
---

# Ingest

Maintain the wiki as a compounding LLM-written knowledge base.

## Core Model

Use the five-layer LLM Wiki model:

1. Raw sources live in `sources/` or `inbox/` and stay immutable.
2. Evidence artifacts live in `outputs/document-intake/` and support reading.
3. Durable wiki pages hold synthesized knowledge.
4. Canonical graph pages in `shared/` hold stable cross-theme nodes.
5. Engineering outputs in `outputs/` turn wiki knowledge into future project guidance.
6. Technical assets in `shared/assets/` capture stable, source-backed capabilities that can be matched to future projects.

The LLM owns semantic work: synthesis, page selection, contradiction handling, graph links, uncertainty, and engineering implications. Scripts only handle deterministic support.

## Default Flow

1. Classify the material into an existing theme, `shared/`, or `inbox/to-be-filed/`.
2. Inspect structure with `inventory` only when destination is unclear.
3. Convert files or URLs with `extract-document` when preprocessing helps; for Git repositories, run Graphify first for structural graph evidence when available, then run `project-reverse` for API/config/reuse/freshness evidence. Treat `extract-git-repo` only as a lightweight fallback.
4. Read the smallest useful context: `schema/entity-relationship-model.md`, indexes, target `README.md`, `meta.md`, `wiki/overview.md`, and relevant pages.
5. Update existing durable wiki pages before creating new pages.
6. Update canonical graph links only when the node is stable enough.
7. If the material affects software development, architecture, evaluation, tooling, or project planning, update or recommend updates to `engineering-brief.md`, `implementation-guide.md`, `decision-brief.md`, `backlog.md`, `reuse-candidates.md`, `asset-match-brief.md`, or `sync-status.md`.
8. For Git repositories and requirements documents, decide whether the material creates a reusable technical asset; update `outputs/reuse-candidates.md` first, then promote stable cross-project capabilities to `shared/assets/`.
9. For new project themes, scan existing `shared/assets/`, `index/technical-assets.md`, and other projects' `outputs/reuse-candidates.md`; when matches are found, update the target project's `outputs/asset-match-brief.md` and record the match rationale.
10. Refresh local query support when durable pages or frontmatter changed: run `python tools/kb_query_index.py index --root .`; if qmd is installed, run `python tools/kb_search_bridge.py status --root .` and refresh lexical search state with `python tools/kb_search_bridge.py index --root . --kind lexical`. On native Windows without WSL2 qmd, do not run qmd embed/vector/hybrid commands during ingest; if WSL2 qmd is available, `--kind vector` or `--kind all` routes embed through WSL2 CLI.
11. For project-source ingest, run or refresh source registry/freshness support when relevant: `python tools/kb_source_registry.py init --root .` and `python tools/kb_freshness_check.py check --root . --timeout 60 --git-timeout 30 --write-report outputs/freshness/latest.json`.
12. Run the post-ingest checklist: wiki pages updated, graph links updated or deferred, outputs updated or deferred, query gaps resolved or recorded.
13. Record uncertainty, source paths, changed pages, and follow-up gaps.

## Deterministic Helpers

Use `.agents/skills/ingest/scripts/kb_ingest_helper.py` only for:

- `inventory`
- `suggest-theme-dir`
- `create-theme`
- `extract-document`
- `extract-git-repo`
- `append-update`
- `scan-reuse`

Use `.agents/skills/project-reverse/scripts/project_reverse_helper.py` for Git repository reverse-engineering evidence before compiling it into wiki pages.

Use `tools/kb_graphify_bridge.py` for Graphify structural graph evidence. Graphify artifacts are routing and relationship evidence only; the LLM must still decide whether each relationship belongs in durable wiki pages or `shared/`.

For full Git project ingest, compile Graphify `graphify-evidence.json` / `graph.json` / `GRAPH_REPORT.md`, `project-reverse-analysis.json`, optional `api-registry.json` / `module-map.json`, and any diff evidence into README/meta, project wiki pages, theme-local concepts, `wiki/reuse-assessment.md`, `outputs/reuse-candidates.md`, engineering outputs, and `outputs/sync-status.md`.

Treat `.query-index/`, `.data-sources/`, qmd local indexes, Graphify runtime/cache files, and `outputs/freshness/latest.*` as runtime support. They can guide ingest and lint, but they do not replace semantic review and must not automatically rewrite durable wiki pages.

Do not use helper scripts to decide which entities, concepts, conclusions, or graph relationships are semantically correct.

## Read More

- Read `references/workflow.md` for non-trivial ingest decisions, confidence handling, and output updates.
- Read `references/commands.md` for exact helper commands.
