# Project Reverse Output Schema

Use this schema for `project-reverse` evidence artifacts. JSON is preferred for deterministic handoff to `ingest`; Markdown can be rendered from the same sections for human review.

## Top-Level Fields

- `schema_version`: current value `project-reverse.v1`.
- `source_type`: `git-repository`.
- `repo`: URL/path, provider hint, requested ref, default/current branch, analyzed commit, capture time.
- `freshness`: `current`, `stale`, or `unknown`, plus latest checked commit and check error when available.
- `inventory`: file counts, extension counts, tree preview, manifests, docs, tests, config, CI, build/deploy, data/storage files.
- `stack`: languages, package managers, frameworks, libraries, runtime versions, build tools.
- `license_signals`: license files, manifest license fields, normalized license hints, license-related config/check files, engineering `license_risk`, and confidence.
- `license_type`: compatibility alias for the primary license signal; `unknown` when no primary license can be determined.
- `dependency_inventory`: direct dependency signals from package manifests and requirements files.
- `open_source_signals`: optional host, dependency count, license risk, activity, and version signals when `--open-source` is used.
- `community_health`: optional local Git activity, contributor sample count, tags, docs, CI, and test health signals.
- `vulnerability_signals`: optional best-effort OSV lookup status; network or service failures must be recorded as `unavailable` and non-blocking.
- `known_vulnerabilities`: compatibility alias for OSV vulnerability results. This field is intentionally dual-shape for v1 compatibility: it may be a list of vulnerability records, or the string `unavailable` when lookup fails. Prefer `vulnerability_signals.status` for structured availability checks.
- `modules`: module candidates with paths, responsibilities, entrypoints, dependencies, test files, reuse score, confidence.
- `api_registry`: API candidates.
- `configuration`: config files, environment variables, feature flags, secrets-management signals.
- `build_deploy`: package scripts, make targets, Docker, compose, CI jobs, infra manifests.
- `data_storage`: models, schema/migration files, DB/cache/queue/storage signals.
- `risks`: technical debt, security, performance, coupling, missing-test, stale-doc, and operational risks.
- `reuse_assessment`: modules/components with extraction score and recommendation.
- `diff`: present only for incremental update artifacts.
- `source_anchor_path`: actual source anchor path when one was written; timestamp mode may create a sibling path if the requested anchor already exists.
- `focused_artifacts`: optional paths for focused handoff files such as `api-registry.json` and `module-map.json`.
- `warnings`: truncation, inaccessible remote, unsupported patterns, and inference limits.

License fields are engineering risk labels for reuse review. They are not legal advice.

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
