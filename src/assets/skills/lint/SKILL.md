---
name: lint
description: Audit the LLM Wiki for structure, graph, and knowledge health. Use when the agent needs to check or repair knowledge-base quality, including missing theme files, dead wikilinks, placeholder pages, canonical node frontmatter, orphan shared nodes, broken evidence links, stale or missing engineering outputs, duplicate/empty content, or readiness before/after ingest and query workflows.
---

# Lint

Check whether the knowledge base is structurally valid, graph-connected, and useful for future work.

## Core Workflow

1. Run `.agents/skills/lint/scripts/kb_lint.py --root .`.
2. Review findings by scope: `structure`, `graph`, and `knowledge`.
3. Fix only low-risk structural issues automatically when the user asked for repair.
4. Treat semantic findings as editorial work: report them or update pages with evidence, never invent content.
5. Record the lint result through the helper's activity log.

## Scopes

- `structure`: root directories, root misresolution, qmd search index health, Graphify bridge/runtime hygiene, theme files, required wiki pages, dead wikilinks, placeholders, empty files, theme index coverage, always-loaded `AGENTS.md` size budget, bootstrap skeleton drift, and skill mirror drift.
- `graph`: canonical node frontmatter, related fields, reverse links, orphan shared nodes, broken `source_pages` / `evidence_from`, and technical asset field validity.
- `knowledge`: empty template canonical nodes, thin outputs, missing engineering/reuse outputs, Graphify evidence completeness, weak evidence chains, stale pages, stale project sources, duplicate nodes, contradiction gaps, source drift, stale engineering outputs, and reuse-chain completeness from `reuse-candidates` through `shared/assets` to `asset-match-brief`.

## Summary Mode

Use `--summary --summary-top 5` when the user needs the most important knowledge gaps instead of a long issue list.

## Commands

Read `references/checks-and-commands.md` for exact commands.
Read `references/workflow.md` when interpreting severity or deciding what is safe to fix.
