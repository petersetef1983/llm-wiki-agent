# Source Adapter Contract

## Purpose

This contract prepares the LLM Wiki for future enterprise sources without connecting to real enterprise systems yet. Adapters fetch source material, normalize it into evidence artifacts, and hand the artifacts to `ingest`; they do not write durable wiki conclusions directly.

## Source Registry

Local source metadata belongs in `.data-sources/registry.json`. The registry is local operational state and must not contain credentials.

Required source fields:

- `id`: stable ASCII identifier.
- `type`: `git | document | im | meeting | cicd | internal-system | other`.
- `provider`: concrete provider such as `github`, `graphify`, `slack`, `generic-meeting`, or `github-actions`.
- `theme`: optional target theme path.
- `enabled`: whether an automation may read this source.
- `url` or `connection`: non-secret endpoint or connector name.
- `freshness`: `current | stale | unknown | not_configured`.
- `metadata`: provider-specific non-secret settings.

Credentials, tokens, cookies, private keys, and raw enterprise exports do not belong in the registry.

## Evidence Artifact

Every adapter emits artifacts shaped like this:

```json
{
  "schema_version": "evidence.v1",
  "source_id": "github-iii",
  "source_type": "git",
  "content_type": "project-reverse|graphify-graph|graphify-report|graphify-query|graphify-global-report|document|im-message|meeting-transcript|ci-event",
  "captured_at": "2026-05-18T00:00:00Z",
  "source_uri": "https://example.invalid/source",
  "provenance": {
    "provider": "github",
    "author": "optional",
    "timestamp": "optional",
    "thread_or_run_id": "optional"
  },
  "sensitivity": "public|internal|confidential|restricted|unknown",
  "retention": "keep|review|expire",
  "confidence": "confirmed|inferred|tentative",
  "redaction_notes": [],
  "content": {}
}
```

Artifacts are evidence only. The LLM still decides whether to update a theme page, create or update a shared node, record an open question, or leave the material as low-confidence evidence.

## Adapter Interface

Each future adapter must implement these conceptual operations:

- `fetch(source_config, cursor) -> list[raw_item]`
- `normalize(raw_item, source_config) -> evidence_artifact`
- `check_freshness(source_config, cursor) -> freshness_status`
- `redact(evidence_artifact, policy) -> evidence_artifact`

Adapters must be idempotent: fetching the same source range twice should not require duplicate durable wiki updates.

## Source Types

- `git`: use Graphify first for structural graph evidence when available, then `project-reverse` for API registry, configuration, build/deploy, data/storage, reuse, freshness, and diff evidence. Store only source anchors and structured artifacts.
- `document`: convert files or URLs into markdown/json evidence artifacts before wiki updates.
- `im`: normalize channel messages, threads, author, timestamp, and source URI; avoid storing private chat without explicit review.
- `meeting`: normalize transcript, attendees, agenda, decisions, and open questions; mark transcription uncertainty.
- `cicd`: normalize build, test, deploy, failure, duration, commit, and environment signals.
- `internal-system`: define a narrow read contract before capture; require sensitivity and retention metadata.

## Graphify Adapter

Graphify is a `provider=graphify` adapter for structural graph evidence. Its default durable artifacts live under:

- `themes/<category>/<theme>/outputs/document-intake/graphify/graphify-evidence.json`
- `themes/<category>/<theme>/outputs/document-intake/graphify/graph.json`
- `themes/<category>/<theme>/outputs/document-intake/graphify/GRAPH_REPORT.md`
- `themes/<category>/<theme>/outputs/document-intake/graphify/graphify-source-anchor.md`
- `outputs/document-intake/graphify/global-cross-project-report.json`
- `outputs/document-intake/graphify/global-cross-project-report.md`

`graphify-evidence.json` must use the `evidence.v1` envelope and include Graphify version, executed command, input URL/path, backend, captured commit when available, node/edge statistics, community and god-node summaries, artifact paths, warnings, redaction notes, sensitivity, retention, and confidence.

Runtime files such as `graphify-cache/`, `graph.html`, MCP server state, full repository checkouts, and temporary clones are not durable wiki artifacts. Keep them outside the knowledge base or under ignored `outputs/document-intake/graphify/runtime/` paths only when explicitly needed for local review.

## Ingest Boundary

Adapters do not decide canonical graph semantics. After artifacts are produced, `ingest` must compile stable conclusions into `themes/`, `shared/`, and `outputs/` while preserving traceability and uncertainty.
