---
name: project-reverse
description: Analyze GitHub, GitLab, self-hosted, or local Git repositories into structured reverse-engineering evidence for architecture, modules, APIs, configuration, deployment, data/storage, risks, reuse, and freshness. Use when the agent needs source-level project analysis, API/source-location extraction, repo update checks, or incremental Git diff evidence before LLM Wiki ingest compiles durable pages.
---

# Project Reverse

Produce structured reverse-engineering evidence for software repositories. This skill is an analyzer: it reads a Git repository and emits evidence artifacts, but it does not write durable wiki pages, canonical graph nodes, or engineering outputs directly.

`ingest` is the compiler. When a repository should enter the LLM Wiki, run Graphify first when available for structural graph evidence, then run `project-reverse` for the source-level evidence Graphify does not reliably cover. `ingest` compiles both evidence layers into the target `project` theme.

## Role With Graphify

Graphify is the preferred structural graph extractor for project relationships, communities, and concept paths. This skill remains responsible for:

- API registry extraction with route/export/command names, parameters, return shapes, source lines, owner modules, and `field_confidence`.
- Configuration, environment variable, feature flag, secret-signal, build/deploy, CI, data/storage, test, security, and risk evidence.
- Conservative reuse scoring and extraction recommendations.
- Freshness checks, changed-area classification, affected durable pages, and incremental diff evidence.

If Graphify artifacts exist at `<theme>/outputs/document-intake/graphify/`, read them as structural context before running or interpreting this analyzer. Do not duplicate Graphify's graph output as a durable wiki conclusion.

## Workflow

1. Identify the repository source, requested ref, target theme, and whether this is initial analysis, freshness check, or incremental update.
2. If Graphify has not already been run and the caller is doing full ingest, run `python tools/kb_graphify_bridge.py extract --repo <git-url-or-local-path> --theme <theme> --root .` first when available.
3. Run the helper to create structured evidence:

```bash
python .agents/skills/project-reverse/scripts/project_reverse_helper.py analyze --repo <git-url-or-local-path> --output <theme>/outputs/document-intake/project-reverse-analysis.json --source-anchor <theme>/sources/project-reverse-source-anchor.md --write-focused-artifacts
```

4. Read only the references needed for the repo shape:
   - `references/workflow.md` for analysis sequence and boundaries.
   - `references/output-schema.md` for required artifact fields.
   - `references/api-and-config-analysis.md` when APIs, parameters, routes, commands, or env/config matter.
   - `references/dependency-analysis.md` when module coupling or reuse scoring matters.
   - `references/code-patterns.md` for language/framework search patterns.
5. Use the evidence to answer analysis questions or hand off to `ingest`.
6. For existing project themes, check freshness before trusting stale code-derived knowledge:

```bash
python .agents/skills/project-reverse/scripts/project_reverse_helper.py check-freshness --repo <git-url-or-local-path> --analyzed-commit <sha> --git-timeout 30
```

7. For moved repos, emit diff evidence:

```bash
python .agents/skills/project-reverse/scripts/project_reverse_helper.py diff --repo <git-url-or-local-path> --old-commit <sha> --new-commit <sha> --output <theme>/outputs/document-intake/project-reverse-diff.json
```

Diff evidence must include changed files, changed area counts, affected durable pages, and next update scope. Use `--sync-diff-output <theme>/outputs/document-intake/sync-diff.json` when the caller wants a stable sync-focused copy.

For batch checks across existing project themes, run:

```bash
python tools/kb_freshness_check.py check --root . --timeout 60 --git-timeout 30 --write-report outputs/freshness/latest.json
```

The batch runner reports `current`, `stale`, `unknown`, or `not_configured` status and can optionally write diff evidence with `--write-diffs`. It does not update durable wiki pages or trigger ingest by itself.

## Evidence Contract

The analyzer artifact must include:

- repo URL/path, provider hint, requested ref, default/current branch, analyzed commit, capture time, freshness status, and latest checked commit when available
- language, framework, package, manifest, and version signals
- module candidates with paths, responsibilities, entrypoints, dependencies, and test coverage hints
- API registry entries with kind, name or route, parameters, behavior, return shape, source path, line number, owning module, and confidence
- API registry entries also include `field_confidence` so missing parameters, request/response shapes, return shapes, or naming-only behavior can be marked without losing the source location
- configuration, environment variables, build/deploy/CI, tests, data/storage, security, risk, and reuse signals
- optional focused artifacts: `api-registry.json`, `module-map.json`, and diff/sync artifacts when requested
- warnings for truncation, remote failures, uncertain inference, and unsupported languages

Static analysis is best-effort. Mark missing or inferred API parameters, return shapes, behavior, and module responsibilities as `tentative` or `inferred`; never invent them as confirmed facts.

## Boundaries

- Do not save full repository checkouts or archives under `sources/`.
- Do not edit raw files under any `sources/` directory.
- If a source anchor path already exists, use timestamp mode or skip mode; do not overwrite an existing anchor.
- Do not decide canonical wiki relationships in helper scripts.
- Do not replace `ingest`; this skill only produces evidence that `ingest` compiles into durable LLM Wiki pages.
