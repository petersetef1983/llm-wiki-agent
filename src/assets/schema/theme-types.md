# Theme Types

This file holds theme-type details that are intentionally kept out of the always-loaded `AGENTS.md`.

## Naming

Themes live under exactly one category directory:

- `themes/general/`
- `themes/project/`
- `themes/research/`

Each theme directory is named `NN-theme-name`, where `NN` is a zero-padded integer inside that category and `theme-name` is a short ASCII slug.

## Project

Use `project` only for software projects, business systems, repositories, services, and internal platforms.

Expected wiki contents:

- `overview.md`
- `architecture.md`
- `modules/`
- `decisions/`
- `incidents/`
- `playbooks/`
- `glossary.md`
- `open-questions.md`

Maintain project themes for engineering execution: system overview, architecture, module boundaries, decisions, incidents, playbooks, runbooks, and domain glossary.

## Research

Use `research` only for technical investigations, AI or LLM research tracks, architecture explorations, and long-running learning topics.

Expected wiki contents:

- `overview.md`
- `concepts/`
- `comparisons/`
- `experiments/`
- `decisions/`
- `glossary.md`
- `open-questions.md`

Maintain research themes around concept clarification, evidence comparison, hypotheses, experiment logs, conclusions with caveats, and next-step planning.

## General

Use `general` only for reusable knowledge domains that apply across multiple themes.

Expected wiki contents:

- `overview.md`
- `concepts/`
- `patterns/`
- `checklists/`
- `faq.md`
- `glossary.md`
- `open-questions.md`

Maintain general themes around transferable concepts, reusable patterns, anti-patterns, checklists, FAQs, and tool or workflow guidance.
