# Project Reverse Workflow

Use this workflow to turn a repository into structured evidence for later LLM Wiki compilation.

## Phase 1: Discovery

1. Identify project purpose from README, docs, package metadata, and website files.
2. Map top-level directories into likely subsystems: runtime, SDK, CLI, API, data, console/UI, docs, infra, tests, examples.
3. Extract stack signals from manifests and lockfiles.
4. Record license, version, branch, commit, release hints, and maturity signals.
5. When the caller requests OSS due diligence, also query hosted metadata for public/private state, archive/fork status, stars/forks/watchers, topics, and recent activity.

## Phase 2: Architecture And Modules

For each major module candidate, capture:

- responsibility and boundary
- entry files and public exports
- imports/dependencies on sibling modules
- key runtime path or request/data flow
- test coverage hints
- reuse/extraction score from 1 to 5
- confidence and source paths

Prefer evidence over polish. The artifact may include rough module candidates; `ingest` will synthesize durable module pages.

## Phase 3: API, Data, And Configuration

API extraction is required when statically discoverable. Capture external and important internal callable surfaces:

- HTTP routes and route handlers
- SDK exports and public library functions
- CLI commands and subcommands
- RPC, gRPC, GraphQL, WebSocket, worker, trigger, function, or event handlers
- internal service methods only when they define important module contracts

Each API entry must include parameters, behavior, return shape, source path, line number, owner module, and confidence where available. Missing values should be explicit, not silently omitted.

Record field-level confidence. A route declaration can have confirmed source location while its request body, response body, or behavior is still tentative. Do not upgrade naming-only behavior to confirmed.

Also capture:

- data models, schemas, migrations, persistence adapters
- config files, env vars, feature flags, secrets-management patterns
- build scripts, deployment manifests, CI jobs, runtime requirements
- security-sensitive auth/RBAC/data-protection paths
- technical debt, performance, and scalability signals when source-located

## Phase 4: Risks And Reuse

Record:

- technical debt and limitations
- high-coupling or cyclic dependency signals
- missing tests around important modules
- security-sensitive config, secret, auth, or network handling
- performance and operational bottleneck hints
- reusable modules with extraction recommendations

## Phase 4.5: OSS Governance And Vulnerabilities

When the caller enables the corresponding checks:

- `--open-source`: collect hosted repository metadata and normalize whether the project appears public and open-source.
- `--community-health`: record CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue template, PR template, CI, release, and recent-push signals; score them conservatively.
- `--vulnerabilities`: derive dependency name/version tuples from manifests and query OSV; record findings and severity summary without pretending to be a full SCA platform.

These checks are best-effort. Network failures, rate limits, private repositories, and non-versioned local dependencies should become warnings, not silent omissions.

## Phase 5: Freshness And Incremental Updates

For existing project themes:

1. Check whether the remote/default branch commit differs from the last analyzed commit.
2. If equal, mark freshness `current`.
3. If changed, produce diff evidence and classify changed areas.
4. If remote is unavailable, mark freshness `unknown` and preserve the last analyzed commit.

Incremental diff evidence should tell `ingest` which durable wiki pages are likely affected, but should not edit those pages itself.

Diff evidence must include `affected_pages` and `next_update_scope` so `ingest` can update only pages mapped from changed areas.

## Handoff To Ingest

`project-reverse` stops after evidence generation. `ingest` must compile the artifact into:

- durable project wiki pages
- API registry and source-location index
- theme-local canonical concepts/entities when useful
- engineering outputs and sync status

Do not save full source code under `sources/`; source anchors and evidence artifacts are enough.
