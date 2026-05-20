---
name: query
description: Answer grounded questions from the LLM Wiki by reading theme pages, canonical graph nodes, engineering outputs, and evidence when needed. Use when the agent needs to explain a project, research direction, concept, decision, incident, pattern, glossary term, previous conclusion, or software-development guidance from the existing knowledge base rather than ingest new materials or run a quality audit.
---

# Query

Answer from the compiled wiki first.

## Core Workflow

1. Identify the likely theme, shared node, or cross-theme boundary.
2. For broad questions or unclear routing, use the qmd bridge first: `python tools/kb_search_bridge.py search --root . --query "<question>" --mode auto --top 10`. On Windows this uses BM25 by default and upgrades to WSL2 qmd HTTP/CLI vector or hybrid only when detected.
3. For code-structure, module-relationship, or concept-path questions, use Graphify graph helpers as routing hints when a target theme has `outputs/document-intake/graphify/graph.json`: `python tools/kb_graphify_bridge.py query --root . --theme <theme> --question "<question>"`.
4. For metadata filtering, use `python tools/kb_query_index.py filter --root . --<field> <value>` before opening candidate pages.
5. Read in order: `index/`, `index/technical-assets.md` for reuse questions, target theme pages, shared graph nodes, relevant `outputs/`, then evidence only when verification is needed.
6. Separate confirmed knowledge, reasonable inference, and missing evidence.
7. For software development questions, include engineering implications, next actions, risks, and source pages.
8. Call out graph gaps, thin outputs, stale pages, or missing evidence.
9. Decide whether the answer has durable wiki value.
10. Record the query with `scripts/kb_query_helper.py`, including answer status and write-back candidate when useful.

## Answer Shape

For substantive answers, prefer:

- Short answer.
- `answer_status: confirmed | inferred | insufficient`.
- `writeback_candidate: yes | no`.
- Confirmed knowledge.
- Engineering implications or recommended actions when relevant.
- Risks, unknowns, or graph/output gaps.
- Source wiki pages.
- For reuse questions: candidate assets, matched requirement, reuse level, reuse cost, license/coupling risks, evidence, and validation tasks.

## Write-Back

Write back, or explicitly recommend a target page, when the answer clarifies a durable decision, pattern, constraint, glossary term, failure mode, project seed, or engineering recommendation.

For software development questions, if `outputs/engineering-brief.md` or `outputs/implementation-guide.md` is missing or thin, treat the answer as a candidate draft for that output rather than leaving it only in chat.

For historical or open-source reuse questions, prefer `shared/assets/`, `outputs/reuse-candidates.md`, and `outputs/asset-match-brief.md`; if they are missing or thin, report an `output_gap` and propose a write-back target.

Read `references/writeback.md` before editing.

Read `references/workflow.md` for cross-theme or engineering-heavy queries.

## Search Tools

- qmd handles BM25 keyword search over compiled wiki pages on all supported local environments.
- qmd vector/hybrid search is optional; use it when `tools/kb_search_bridge.py status --root .` reports `vector_available=true`.
- Preferred vector paths are WSL2 qmd HTTP/MCP daemon first, WSL2 qmd CLI fallback second, and Linux/WSL native qmd when running inside Linux.
- When vector is unavailable, `--mode auto` falls back to BM25; use `--allow-fallback` for explicit `hybrid` or `vector` requests that may degrade to BM25.
- `tools/kb_query_index.py` handles frontmatter filtering by `node_type`, `themes`, `reuse_level`, `reuse_cost`, `confidence`, `tech_stack`, and license compatibility.
- `tools/kb_graphify_bridge.py query/path/explain` handles structural graph routing for themes with Graphify evidence.
- Search and graph results are routing hints, not final evidence; synthesize answers from durable wiki pages and source-linked outputs.
