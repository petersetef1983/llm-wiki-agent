# Output Format

Use Markdown only.

## Wiki Page Shape

Prefer descriptive headings, short paragraphs, compact bullet lists, and explicit sections where useful:

- summary
- importance
- core knowledge
- decisions or trade-offs
- related pages
- sources
- unknowns / next steps

Keep file and directory names ASCII and stable.

## Good Output

Good wiki content should help future agents and humans:

- understand a codebase
- recall why a decision was made
- debug recurring failures
- compare technical options
- onboard into a project
- continue a research direction
- reuse proven patterns across themes

## Engineering Outputs

`outputs/` pages are action views compiled from wiki content. They do not replace raw sources, evidence artifacts, or durable wiki pages.

Recommended output pages:

- `engineering-brief.md`
- `implementation-guide.md`
- `decision-brief.md`
- `backlog.md`
- `requirement-analysis.md`
- `next-steps.md`
- `weekly-summary.md`
- `reuse-candidates.md`
- `asset-match-brief.md`

Outputs should link back to supporting wiki pages, shared nodes, or evidence artifacts and label recommendations as `confirmed`, `inferred`, or `tentative` when confidence matters.

## Runtime Artifacts

Local runtime artifacts support search, metadata filtering, source tracking, and freshness checks. They are operational state, not wiki content:

- `.query-index/frontmatter.json` is the generated frontmatter index for structured query filters.
- qmd local indexes are generated search state. On native Windows the supported baseline is BM25 keyword retrieval; vector and hybrid retrieval are optional runtime capabilities via WSL2 qmd HTTP/MCP daemon, WSL2 CLI passthrough, or Linux/WSL native qmd. The bridge auto-detects the best available path.
- `.data-sources/registry.json` records source adapter registrations and cursors.
- `outputs/freshness/latest.json` and `outputs/freshness/latest.md` report project source freshness.

Runtime reports may be cited as evidence for follow-up work, but they should not silently rewrite durable pages. A stale freshness report should produce review tasks, diff evidence, or lint warnings before any wiki update.

## Technical Asset Outputs

Use `outputs/reuse-candidates.md` when a project can export reusable technical capabilities or when a target project is collecting candidate assets. Include the candidate asset, source project, reuse level, reuse cost, best-fit scenario, key risk, and evidence links.

Use `outputs/asset-match-brief.md` when a new project requirement is matched against historical or open-source assets. It should not treat the target requirement as a proven asset; it should record demand-side fit, adaptation work, rejection reasons, and validation tasks.

Use `outputs/requirement-analysis.md` when ingest is explicitly requirement-driven and the source document needs to be normalized into functional requirements, non-functional constraints, technical constraints, acceptance criteria, and key entities before later synthesis work.

Technical asset pages should include `license_compatibility` frontmatter as engineering risk metadata. Treat GPL, ELv2, mixed-license, or unclear source boundaries as `review_required` unless project evidence and legal review confirm a narrower answer.
