# Query Workflow

## Reading Order

Start narrow and follow links:

1. `index/themes.md`.
2. `index/cross-theme-map.md`.
3. `index/technical-assets.md` when the question asks about reuse, historical project capabilities, open-source adoption, or new-project matching.
4. `schema/entity-relationship-model.md` when graph or output interpretation matters.
5. Target theme `README.md`, `meta.md`, and `wiki/overview.md`.
6. Relevant theme pages such as `architecture.md`, `glossary.md`, `open-questions.md`, `decisions/`, `incidents/`, `playbooks/`, `concepts/`, `comparisons/`, `experiments/`, `patterns/`, or `reuse-assessment.md`.
7. Canonical shared nodes linked from those pages, especially `shared/assets/` for reuse questions.
8. Relevant `outputs/`, especially `engineering-brief.md`, `implementation-guide.md`, `reuse-candidates.md`, and `asset-match-brief.md` for software development questions.
9. Evidence artifacts or raw source paths only when the wiki claim needs verification.

## Grounding Rules

- Answer from explicit wiki content first.
- Treat outputs as action views, not fact sources.
- Use shared nodes as graph navigation; do not trust empty template nodes as high-confidence evidence.
- Mark confirmed knowledge, inference, and missing evidence separately.
- If a recurring concept lacks a canonical node, report a graph gap.
- If an engineering answer lacks outputs, report an output gap.
- If a reuse answer lacks stable asset nodes or candidate outputs, report a graph/output gap instead of inventing assets.
- Set `answer_status`:
  - `confirmed` when the answer is directly supported by current wiki/source links.
  - `inferred` when the answer follows from theme structure, related pages, or weak evidence and must be labelled.
  - `insufficient` when the wiki does not support a reliable answer.
- Set `writeback_candidate` to `yes` when the answer should compound the wiki.

## Engineering Queries

When a question concerns software development, architecture, implementation, testing, evaluation, tooling, or project planning, include:

- Confirmed constraints and decisions.
- Engineering implications.
- Recommended next actions.
- Risks and acceptance signals.
- Source wiki pages and outputs used.

Prefer `outputs/engineering-brief.md`, `outputs/implementation-guide.md`, `outputs/decision-brief.md`, and `outputs/backlog.md` after reading the underlying wiki pages.

For reuse queries, prefer `index/technical-assets.md`, `shared/assets/`, source project `outputs/reuse-candidates.md`, target project `outputs/asset-match-brief.md`, and source `wiki/reuse-assessment.md`.

Include:

- Candidate asset.
- Matched requirement or scenario.
- Reuse level: `direct | adapt | reference | reject`.
- Reuse cost: `low | medium | high`.
- License, coupling, freshness, and evidence risks.
- Next validation task and acceptance signal.

If those outputs are missing or too thin:

- Report `output_gap`.
- Use the answer to propose a write-back target.
- When the user's request asks for implementation or maintenance, create or update the relevant output page with clear source links.

## Fixed Response Template

Use this shape for non-trivial answers:

```text
answer_status: confirmed | inferred | insufficient
writeback_candidate: yes | no
writeback_target: <path or none>

Short answer: ...

Confirmed knowledge:
- ...

Engineering implications:
- ...

Recommended next actions:
- ...

Risks / unknowns / gaps:
- graph_gap: ...
- output_gap: ...
- evidence_gap: ...

Sources:
- ...
```

Omit empty sections for small answers, but do not hide gaps.

## Logging

Record completed queries:

```bash
<PYTHON_CMD> .agents/skills/query/scripts/kb_query_helper.py --root . record-query --question "..." --summary "..." --theme themes/general/02-agent-evaluation --answer-status inferred --writeback-candidate yes --writeback-target themes/general/02-agent-evaluation/outputs/engineering-brief.md --gap output_gap
```
