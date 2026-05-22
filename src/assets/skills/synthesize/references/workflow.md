# Synthesize Workflow

## Inputs

Use the smallest sufficient context:

- target theme `README.md`, `meta.md`, `wiki/overview.md`, `wiki/open-questions.md`
- target `outputs/requirement-analysis.md`
- `index/technical-assets.md`
- `shared/assets/*.md` relevant to the requirements
- source project `outputs/reuse-candidates.md`
- project-reverse or Graphify evidence only when validation, license, freshness, or module/API detail is needed

## Matching Rules

- Start with `scripts/kb_synthesize_helper.py match-assets --target-theme <theme>` and treat the result as the deterministic baseline.
- `match-assets` defaults to `--search-mode auto`, which combines keyword overlap, best-effort BM25 via `kb_search_bridge`, frontmatter filtering via `kb_query_index`, and read-only Graphify graph hints when artifacts exist.
- Inspect `search_diagnostics` and each match's `search_signals`; bridge failures are routing limitations, not synthesize failures.
- Run `check-license` and `assess-reuse` before drafting final outputs.
- Match by requirement ID, functional area, key entity, technical constraint, tech stack, and acceptance criteria.
- Prefer shared assets over unpromoted reuse candidates when both describe the same capability.
- Keep rejected matches in the output when they prevent scope creep.
- If evidence is missing, record a validation task instead of upgrading confidence.

## Output Rules

`asset-match-brief.md` must include:

- matched requirement ID or area
- candidate asset or source project
- reuse level: `direct | adapt | reference | reject`
- reuse cost: `low | medium | high`
- license status or review note
- main risk
- validation task and acceptance signal
- evidence links

`engineering-brief.md` should summarize goals, constraints, reuse strategy, options, risks, and next actions.

`implementation-guide.md` should include milestones, module boundaries, task breakdown, data/interface flow, test strategy, and reuse checkpoints.

`decision-brief.md` should compare options and give a recommendation with counterexamples or rejection reasons.

## Write-Back Rules

- Update target outputs first.
- Use wikilinks in `[[path/to/page|Label]]` form for durable wiki pages and proposed shared assets.
- Propose `shared/assets/` or `shared/patterns/` only when the capability is reused by multiple themes and has source-backed evidence.
- If promotion is proposed, update related theme links and `index/technical-assets.md`.
- Log the synthesis operation after confirmed writes.
