# Lint Workflow

## Severity

- `error`: broken structure or invalid references that can mislead tools.
- `warning`: degraded graph or knowledge quality that should be fixed soon.
- `info`: maintenance backlog, thin content, or optional improvements.

## Fix Policy

Safe to fix when requested:

- Missing standardized directories.
- Missing scaffold pages from templates.
- Obvious `index/themes.md` omissions.
- Simple broken links where the target is unambiguous.

Do not auto-fix:

- Theme merging or renaming.
- Ambiguous links.
- Canonical node creation from weak evidence.
- Contradictions, conclusions, or engineering recommendations.
- Deleting pages.

## Reporting

Report:

- Counts by severity and by scope.
- The highest-impact broken files or themes.
- Which issues are safe structural fixes.
- Which findings need semantic ingest or manual review.
- Whether query may be affected by graph gaps or thin outputs.
- In summary mode, report the top five actionable gaps first.

## Semantic Maintenance

`knowledge` findings include heuristic semantic checks. Interpret them as prompts for wiki maintenance:

- `stale_page`: re-read newer sources/evidence and update the durable wiki if conclusions changed.
- `contradiction_gap`: add a `contradicts` relation or open question only after reading the relevant evidence.
- `duplicate_canonical_node`: merge or cross-link only when the concepts are truly the same.
- `source_drift`: add traceability text or remove stale evidence links.
- `output_stale`: recompile engineering outputs from the newer wiki pages.

Do not let lint create semantic content on its own.
