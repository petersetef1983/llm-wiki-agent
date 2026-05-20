# Ingest Workflow

## Reading Order

Read only enough context to make a correct update:

1. Raw source location or evidence artifact.
2. `schema/entity-relationship-model.md`.
3. `index/themes.md`.
4. `index/cross-theme-map.md` when cross-theme impact is plausible.
5. Target theme `README.md`, `meta.md`, and `wiki/overview.md`.
6. Relevant `glossary.md`, `open-questions.md`, topic pages, `wiki/reuse-assessment.md`, shared nodes, technical assets, and outputs.

## Classification

Choose the narrowest durable home:

- Existing theme when the material clearly belongs there.
- `shared/` only for stable cross-theme entities, concepts, patterns, methods, tools, glossary terms, or technical assets.
- `inbox/to-be-filed/` when destination or evidence quality is too uncertain.
- New theme only when a long-lived topic has emerged and no existing theme fits.

## Evidence Handling

- Keep raw sources unchanged.
- Use `extract-document` for PDFs, office files, URLs, transcripts, audio/video outputs, or any source that benefits from conversion.
- Use `project-reverse` for GitHub, GitLab, internal Git services, or local Git repositories when source-level project analysis is needed; keep `extract-git-repo` only as a legacy/lightweight fallback.
- Treat extraction as evidence, not final wiki content.
- Mark confidence as high, medium, or low in the wiki update or report.
- Low-confidence evidence should usually update `open-questions.md`, not stable shared nodes.

## Git Repo Ingest

Use this flow when the source is a software repository and the goal is to understand functionality, architecture, APIs, modules, implementation choices, freshness, or reusable engineering ideas.

### Classification

- If the repository is an independent software system, library, framework, service, or internal project, create or update a `project` theme.
- If the repository only supports an existing project theme, ingest it into that existing project theme.
- If the user only wants reusable patterns from the repository, update `shared/` or a relevant `general` theme without creating a repo-specific theme.
- Do not create a new top-level theme category for GitHub, GitLab, or internal Git repositories.

### Source Policy

- `project-reverse` may temporarily clone the full repository so the LLM can inspect source deeply during the current run.
- Do not save full source code, zip archives, or checkouts under `sources/`.
- Save only a source anchor under `sources/` that records URL, requested ref, resolved commit, capture time, and evidence artifact path.
- Save repo evidence under `outputs/document-intake/`; structured analyzer artifacts are evidence, not durable source replacement.
- Authentication for private repositories belongs to local `git` configuration, SSH keys, or credential manager. Do not write tokens into wiki pages, logs, anchors, or artifacts.

### Analyzer First

Before writing durable wiki pages, run the `project-reverse` analyzer:

```bash
<PYTHON_CMD> .agents/skills/project-reverse/scripts/project_reverse_helper.py analyze \
  --repo <git-url-or-local-path> \
  --output themes/project/NN-repo/outputs/document-intake/project-reverse-analysis.json \
  --source-anchor themes/project/NN-repo/sources/project-reverse-source-anchor.md \
  --source-anchor-mode timestamp \
  --write-focused-artifacts
```

For existing project themes, check freshness against the last analyzed commit. If the repo moved, generate `project-reverse-diff.json` or `sync-diff.json` and update only `affected_pages` unless the user asks for a full rebuild or semantic review finds cross-cutting drift.

### Project Wiki Targets

After reading the temporary clone and evidence artifact, update:

- `README.md`: project positioning, analysis status, and reading entry points.
- `wiki/overview.md`: functional scope, core capabilities, boundaries, evidence status.
- `wiki/architecture.md`: runtime structure, major dependencies, module relationships, data flow.
- `wiki/modules/*.md`: core module responsibilities, entry files, important implementation details, interfaces, and risks.
- `wiki/api.md`: API registry with kind, name/route/command, parameters, behavior, return shape, source file, source line, owner module, and confidence.
- `wiki/data-storage.md`: data models, persistence, state, queues, caches, migrations, schema files, and uncertainty.
- `wiki/configuration.md`: config files, env vars, feature flags, precedence, secrets-handling notes.
- `wiki/build-deployment.md`: build scripts, CI, Docker, infra, deployment and runtime requirements.
- `wiki/technical-notes.md`: design patterns, algorithms, performance concerns, security or operational details.
- `wiki/reuse-assessment.md`: reusable modules, extraction score, blockers, and suggested boundaries.
- `wiki/glossary.md`: project terms, component names, protocols, and key abstractions.
- `wiki/open-questions.md`: unverified behavior, missing runtime validation, complex source areas.
- `outputs/engineering-brief.md`: engineering lessons, constraints, and risks for future projects.
- `outputs/implementation-guide.md`: implementation approaches worth reusing, module boundaries, and testing strategy.
- `outputs/decision-brief.md`: architecture choices, trade-offs, and counterexamples.
- `outputs/backlog.md`: experiments, reproduction tasks, and deeper reading tasks.
- `outputs/reuse-candidates.md`: reusable technical assets, reuse level, adaptation cost, risks, and validation tasks.
- `outputs/sync-status.md`: analyzed commit, latest checked commit, freshness status, changed areas, stale pages, and next update scope.

### Technical Asset Rules

- Use `outputs/reuse-candidates.md` as the first landing zone for project-specific reuse findings.
- Promote to `shared/assets/` only when a capability is stable, source-backed, and plausibly useful to future projects.
- Technical asset pages must include source project, suitable and unsuitable scenarios, tech stack, dependencies, license boundary, maturity, reuse level, reuse cost, confidence, source pages, and evidence artifacts.
- Use reuse levels `direct`, `adapt`, `reference`, and `reject`; use reuse costs `low`, `medium`, and `high`.
- When matching a target project against assets, write the demand-side synthesis to `outputs/asset-match-brief.md` and keep target requirements separate from proven source assets.

### Cross-Project Reuse Scan

When ingesting a new project theme:

1. Run `scan-reuse` to get a read-only inventory of shared assets, reuse candidates, target match briefs, missing briefs, unpromoted candidates, unmatched assets, and broken asset references.
2. Read `index/technical-assets.md` to discover all available shared assets.
3. Read each relevant `shared/assets/*.md` page whose `suitable_for`, `tech_stack`, source project, or related concepts overlap with the new project.
4. Read other projects' `outputs/reuse-candidates.md` for candidate assets not yet promoted to `shared/assets/`.
5. For each matching asset, evaluate functional overlap, tech stack compatibility, license compatibility, integration cost, main risk, and validation task.
6. Write demand-side synthesis to the new project's `outputs/asset-match-brief.md`; do not treat target requirements as proven assets.
7. Update `index/technical-assets.md` target project matching table and `index/cross-theme-map.md` when a real cross-theme relation is established.
8. If the new project reveals a stable cross-project concept or pattern, suggest or create the appropriate `shared/concepts/` or `shared/patterns/` page with evidence.

### Entity And API Rules

- Treat API source location as a first-class navigation target. Every API entry should include source path and line number when the analyzer can discover it.
- Treat API confidence as field-specific: a source location can be confirmed while parameters, request shape, return shape, or behavior remain tentative.
- Create theme-local canonical concept/entity pages for recurring project concepts before promoting anything to `shared/`.
- Link module pages to relevant API entries and source-location evidence.
- Mark a wiki page or section stale when its source-derived conclusion is older than the recorded repo freshness status.

### Confidence

- Mark conclusions as `confirmed` only when supported by source files, API declarations, manifests, tests, docs, or a coherent implementation path.
- Mark conclusions as `inferred` when based on source structure but not runtime verification.
- Mark conclusions as `tentative` when the artifact is truncated, key files are excluded, checkout fails partially, or private dependencies are unavailable.

## Durable Wiki Maintenance

Prefer existing pages:

- General themes: `overview.md`, `glossary.md`, `faq.md`, `patterns/`, `checklists/`.
- Project themes: `overview.md`, `architecture.md`, `modules/`, `decisions/`, `incidents/`, `playbooks/`.
- Research themes: `overview.md`, `concepts/`, `comparisons/`, `experiments/`, `decisions/`.

When writing:

- Merge new evidence into current synthesis.
- Revise old conclusions when new evidence changes them.
- Record contradictions explicitly.
- Add wikilinks to recurring entities and concepts.
- Promote to `shared/` only when the node is stable and useful across themes.

## Engineering Outputs

After durable wiki updates, decide whether the material changes future software work.

Update or recommend:

- `outputs/engineering-brief.md` for goals, constraints, risks, and engineering implications.
- `outputs/implementation-guide.md` for module boundaries, interfaces, data flow, and tests.
- `outputs/decision-brief.md` for options, trade-offs, recommendations, and counterexamples.
- `outputs/backlog.md` for project seeds, experiments, implementation tasks, and acceptance signals.
- `outputs/reuse-candidates.md` for reusable capability candidates from source projects or candidate assets for target projects.
- `outputs/asset-match-brief.md` for demand-to-asset matching in new projects.

Outputs must link back to wiki pages or shared nodes and should label claims as confirmed, inferred, or tentative.

## Post-Ingest Checklist

Before reporting completion, confirm:

- Wiki pages updated: existing durable pages were revised before creating new ones.
- Graph links updated: stable entities/concepts have canonical links, or promotion was explicitly deferred.
- Outputs updated: engineering outputs were updated when the material affects software development, architecture, evaluation, tooling, or project planning.
- Technical assets updated: reuse candidates were captured or intentionally deferred; stable assets were linked from `shared/assets/` and `index/technical-assets.md`.
- Outputs deferred: if output updates were skipped, the reason and target page are recorded.
- Query gaps resolved: any graph gap, output gap, evidence gap, contradiction, or stale conclusion discovered during ingest is fixed or listed as follow-up.
- Evidence confidence recorded: low-confidence extraction does not become high-confidence wiki knowledge.
- Git repo policy respected: no full source checkout or archive was saved under `sources/`.

## Report Back

Include:

- Raw sources processed.
- Evidence artifacts created.
- Durable wiki pages updated.
- Canonical graph nodes touched.
- Engineering outputs updated or intentionally deferred.
- High-confidence conclusions and unresolved gaps.
