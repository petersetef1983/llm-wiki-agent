---
name: synthesize
description: Generate demand-driven cross-project engineering outputs from an ingested requirement analysis, historical project knowledge, open-source project evidence, shared technical assets, and reuse candidates. Use when a target project needs asset matching, implementation guidance, risk/license assessment, or decision briefs after requirements have been ingested.
---

# Synthesize

Turn compiled wiki knowledge into delivery guidance for a target project.

## Role

`ingest` compiles sources into durable wiki pages and `outputs/requirement-analysis.md`.
`synthesize` starts after that: it reads the target requirement analysis, historical project themes, open-source evidence, shared assets, and reuse candidates, then proposes target-theme-local engineering outputs.

## Default Flow

1. Read the target project's `outputs/requirement-analysis.md`.
2. Read `index/technical-assets.md`, relevant `shared/assets/`, and source project `outputs/reuse-candidates.md`.
3. Read source project evidence only when needed for license, freshness, API, module, or dependency risk.
4. Match requirements to candidate assets, patterns, modules, or methods.
5. Mark each match as `direct`, `adapt`, `reference`, or `reject`.
6. Mark reuse cost as `low`, `medium`, or `high`.
7. Record license, coupling, freshness, vulnerability, and evidence risks without making legal claims.
8. Generate or update target-theme-local:
   - `outputs/asset-match-brief.md`
   - `outputs/engineering-brief.md`
   - `outputs/implementation-guide.md`
   - `outputs/decision-brief.md`
   - optionally `outputs/backlog.md`
9. Recommend shared asset or pattern promotion only when evidence is stable, source-backed, and useful across themes.

## Boundaries

- Do not treat a target requirement as a proven reusable asset.
- Do not write raw source files or runtime indexes.
- Do not silently promote shared assets from a single weak match.
- Use `outputs/asset-match-brief.md` for demand-side synthesis.
- Use `shared/assets/` only for source-backed, cross-project reusable capabilities.

## Helper

Use `scripts/kb_synthesize_helper.py` for the deterministic baseline before asking the LLM to polish or deepen conclusions:

- `context --target-theme <theme>` gathers synthesis context.
- `match-assets --target-theme <theme>` matches requirements to historical, shared, and open-source assets. It defaults to `--search-mode auto`, combining keyword overlap, BM25/qmd, frontmatter filters, and read-only Graphify hints with graceful fallback.
- `check-license --target-theme <theme>` adds engineering license-risk labels.
- `assess-reuse --target-theme <theme>` adds reuse level, cost, risk, and validation tasks.
- `generate-outputs --target-theme <theme>` emits target-theme output proposals; it writes only with `--confirm WRITE-KB`.

The helper provides evidence-backed structure; semantic judgment still belongs to the agent.

## Read More

- Read `references/workflow.md` for output expectations and conservative write-back rules.
