# Wiki Writing Standards

This file holds detailed writing rules that are loaded only when editing wiki content.

## Writing Rules

Write concise, high-signal Markdown. Prioritize:

- responsibilities
- boundaries
- architecture
- trade-offs
- decisions
- failure modes
- debugging clues
- operational knowledge
- reusable patterns

Avoid vague summaries. Update existing pages before creating new ones. Link related pages when the relationship matters. Mark stale or tentative conclusions explicitly.

## Theme README

Treat each theme `README.md` as the theme entry point. Keep it navigable and current.

It should answer:

- What is this theme?
- Why does it matter?
- What is the current focus?
- What should be read first?
- What are the key wiki pages?
- What remains unclear?

## Theme Meta

Each `meta.md` tracks:

- theme name
- theme type
- status
- owners
- tags
- stack summary
- boundaries
- update date

Update `meta.md` when any of those fields become outdated.

## Stack Documentation

Use each theme's `stack/` directory for theme-specific languages, frameworks, data systems, infrastructure, tooling, evaluation tools, and workflows.

Do not move theme-specific stack details into `shared/` unless they are broadly reusable.

## Update Checklists

For `project` themes, ask whether architecture changed, a module boundary became clearer, a decision was made, an incident produced a reusable lesson, or a playbook should be updated.

For `project` themes that ingest a Git repository or requirements document, also ask whether the material creates a reusable technical asset. If yes, update `outputs/reuse-candidates.md`; promote to `shared/assets/` only when the capability is stable, source-backed, and useful beyond the source theme.

For `research` themes, ask what concept became clearer, what belief changed, what evidence affects a hypothesis, what experiment should run next, and what comparison should be updated.

For `general` themes, ask whether the material is reusable, refines a pattern, belongs in a checklist, or answers a recurring question.

## Uncertainty

When something is uncertain, record:

- what is uncertain
- why it is uncertain
- what evidence is missing
- what should be checked next

If sources conflict, record the conflict explicitly instead of smoothing it away.

## Anti-Duplication

Before creating a page:

1. Check whether an equivalent page already exists.
2. Update the existing page if possible.
3. Create a new page only when the topic is clearly distinct.

Avoid duplicate summaries, near-duplicate concept pages, and parallel pages that will drift out of sync.
