# Project Reverse Output Schema

Use this schema for `project-reverse` evidence artifacts. JSON is preferred for deterministic handoff to `ingest`; Markdown can be rendered from the same sections for human review.

## Top-Level Fields

- `schema_version`: current value `project-reverse.v1`.
- `source_type`: `git-repository`.
- `repo`: URL/path, provider hint, requested ref, default/current branch, analyzed commit, capture time.
- `freshness`: `current`, `stale`, or `unknown`, plus latest checked commit and check error when available.
- `inventory`: file counts, extension counts, tree preview, manifests, docs, tests, config, CI, build/deploy, data/storage files.
- `stack`: languages, package managers, frameworks, libraries, runtime versions, build tools.
- `open_source_signals`: hosted repository metadata such as public/private signal, stars, forks, topics, archive state, and confidence when `--open-source` is enabled.
- `license_signals`: license files, manifest license fields, normalized license summary, review-required flag, license-related config/check files, and confidence.
- `community_health`: community files, CI/governance/security-policy signals, optional hosted activity metadata, score, and confidence when `--community-health` is enabled.
- `modules`: module candidates with paths, responsibilities, entrypoints, dependencies, test files, reuse score, confidence.
- `api_registry`: API candidates.
- `configuration`: config files, environment variables, feature flags, secrets-management signals.
- `build_deploy`: package scripts, make targets, Docker, compose, CI jobs, infra manifests.
- `data_storage`: models, schema/migration files, DB/cache/queue/storage signals.
- `vulnerability_signals`: dependency inventory, OSV query results, severity summary, findings, and confidence when `--vulnerabilities` is enabled.
- `risks`: technical debt, security, performance, coupling, missing-test, stale-doc, and operational risks.
- `reuse_assessment`: modules/components with extraction score and recommendation.
- `diff`: present only for incremental update artifacts.
- `source_anchor_path`: actual source anchor path when one was written; timestamp mode may create a sibling path if the requested anchor already exists.
- `focused_artifacts`: optional paths for focused handoff files such as `api-registry.json` and `module-map.json`.
- `warnings`: truncation, inaccessible remote, unsupported patterns, and inference limits.

## API Registry Entry

Every API candidate should use these fields:

- `kind`: `http-route`, `sdk-export`, `cli-command`, `rpc-service`, `websocket-message`, `worker-function`, `library-export`, or `internal-service`.
- `name`: stable name, route, command, exported symbol, or service method.
- `method`: HTTP verb or command method when applicable.
- `path`: route path, CLI path, source symbol path, or protocol channel.
- `parameters`: list of `{name, type, required, default, source}` where known.
- `request_shape`: request DTO/body/message shape when known.
- `return_shape`: response/result/message shape when known.
- `behavior`: concise purpose; mark as tentative if inferred from naming only.
- `source_path`: repository-relative source file.
- `source_line`: 1-based line number when statically discoverable.
- `owner_module`: module candidate that owns the API.
- `confidence`: `confirmed`, `inferred`, or `tentative`.
- `field_confidence`: confidence by field, including parameters, request shape, return shape, behavior, and source location.
- `evidence`: exact pattern type, nearby docs/comment, manifest entry, or route declaration used.

## Freshness Fields

- `analyzed_commit`: commit represented by durable wiki content.
- `latest_checked_commit`: latest remote/default branch commit seen by helper.
- `status`: `current` when equal, `stale` when different, `unknown` when remote check failed.
- `changed_areas`: for diffs, classify changes into `api`, `module`, `config`, `data-storage`, `build-deploy`, `docs`, `tests`, `dependencies`, `security`, or `unknown`.
- `affected_pages`: durable wiki/output pages that `ingest` should review for the changed areas.
- `next_update_scope`: concise update instruction for incremental compilation.

## Confidence Rules

- `confirmed`: supported by source declarations, manifests, tests, docs, or route/signature syntax.
- `inferred`: supported by file structure, naming, imports, or partial declarations.
- `tentative`: truncated, framework-specific parser uncertain, unsupported language, or missing return/parameter source.

Top-level API confidence should not stay `confirmed` when required field confidence is tentative. A source location can be confirmed while request/return shape remains tentative.
