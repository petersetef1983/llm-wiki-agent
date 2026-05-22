#!/usr/bin/env python3
"""Output rendering and writeback for deterministic synthesis."""

from __future__ import annotations

import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from kb_synthesize_assessment import assess_reuse, check_license, detect_promotion_candidates
from kb_synthesize_common import CONFIRM_WRITE, DEFAULT_MAX_CHARS, OUTPUT_NAMES, build_wikilink, clean_theme_path, log_synthesize_operation, read_text, safe_write_path, table_escape, validate_wikilinks
from kb_synthesize_context import parse_requirements
from kb_synthesize_search import match_assets


def generate_outputs(
    root: Path,
    target_theme: str,
    *,
    top: int = 20,
    search_mode: str = "auto",
    reuse_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reuse_payload = reuse_payload or assess_reuse(root, target_theme, top=top, search_mode=search_mode)
    assessments = reuse_payload.get("assessments", [])
    promotions = detect_promotion_candidates(root, target_theme, assessments)
    theme = clean_theme_path(target_theme)
    proposed_changes = [
        {
            "action": "write",
            "path": f"{theme}/outputs/asset-match-brief.md",
            "content": render_asset_match_brief(theme, assessments, promotions),
            "rationale": "Deterministic synthesize output from requirement-to-asset matching.",
            "confidence": "inferred",
        },
        {
            "action": "write",
            "path": f"{theme}/outputs/engineering-brief.md",
            "content": render_engineering_brief(theme, assessments),
            "rationale": "Deterministic engineering brief scaffold from assessed reuse candidates.",
            "confidence": "inferred",
        },
        {
            "action": "write",
            "path": f"{theme}/outputs/implementation-guide.md",
            "content": render_implementation_guide(theme, assessments),
            "rationale": "Deterministic implementation guide scaffold from validation tasks.",
            "confidence": "inferred",
        },
        {
            "action": "write",
            "path": f"{theme}/outputs/decision-brief.md",
            "content": render_decision_brief(theme, assessments),
            "rationale": "Deterministic decision brief scaffold from license and reuse risk.",
            "confidence": "inferred",
        },
    ]
    for promotion in promotions:
        if not (root / promotion["target_ref"]).exists():
            proposed_changes.append(
                {
                    "action": "write",
                    "path": promotion["target_ref"],
                    "content": render_shared_asset(promotion),
                    "rationale": "Promote cross-theme reusable asset after confirmed synthesis.",
                    "confidence": "inferred",
                }
            )
        for theme_ref in promotion.get("themes") or []:
            readme_path = f"{theme_ref}/README.md"
            existing_path = root / readme_path
            if existing_path.is_file():
                proposed_changes.append(
                    {
                        "action": "write",
                        "path": readme_path,
                        "content": render_theme_asset_link(read_text(existing_path, max_chars=0), promotion),
                        "rationale": "Link source or target theme back to a promoted shared asset.",
                        "confidence": "inferred",
                    }
                )
    proposed_changes.append(
        {
            "action": "write",
            "path": "index/technical-assets.md",
            "content": render_technical_assets_index(root, promotions),
            "rationale": "Refresh technical asset index with confirmed promotion candidates.",
            "confidence": "inferred",
        }
    )
    return {
        "schema_version": "llm-wiki-synthesize-outputs.v1",
        "root": str(root.resolve()),
        "target_theme": theme,
        "assessments": assessments,
        "promotion_candidates": promotions,
        "proposed_changes": proposed_changes,
        "wikilink_validation": validate_wikilinks(root, proposed_changes, planned_paths=[item["path"] for item in proposed_changes]),
    }


def render_asset_match_brief(theme: str, assessments: list[dict[str, Any]], promotions: list[dict[str, Any]]) -> str:
    lines = [
        "# Asset Match Brief",
        "",
        "## Summary",
        "",
        f"- Target project: {build_wikilink(f'{theme}/README.md', PurePosixPath(theme).name)}",
        "- Requirement analysis: " + build_wikilink(f"{theme}/outputs/requirement-analysis.md", "requirement-analysis"),
        f"- Candidate matches: {len(assessments)}",
        "- Confidence: inferred",
        "",
        "## Candidate Matches",
        "",
        "| Requirement ID | Requirement area | Candidate asset | Source project | Reuse level | Reuse cost | License status | Why it fits | Main risk | Validation task |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in assessments or []:
        candidate_ref = str(item.get("candidate_ref") or "")
        if candidate_ref.endswith(".md"):
            candidate = build_wikilink(candidate_ref, str(item.get("candidate_title")))
        else:
            candidate = f"`{candidate_ref or item.get('candidate_title') or ''}`"
        source = build_wikilink(f"{item.get('source_theme')}/README.md", PurePosixPath(str(item.get("source_theme") or "source")).name) if item.get("source_theme") else ""
        lines.append(
            "| {requirement_id} | {area} | {candidate} | {source} | {reuse_level} | {reuse_cost} | {license_status} | {why} | {risk} | {task} |".format(
                requirement_id=item.get("requirement_id") or "",
                area=table_escape(str(item.get("requirement") or ""))[:80],
                candidate=table_escape(candidate),
                source=table_escape(source),
                reuse_level=item.get("reuse_level") or "reference",
                reuse_cost=item.get("reuse_cost") or "medium",
                license_status=item.get("license_status") or "unknown",
                why=table_escape("; ".join(item.get("match_reason") or [])),
                risk=table_escape(str(item.get("main_risk") or "")),
                task=table_escape(str(item.get("validation_task") or "")),
            )
        )
    if not assessments:
        lines.append("|  |  |  |  | reference | high | unknown | no deterministic match | missing evidence | run manual search |")
    lines.extend(["", "## Recommended Use", ""])
    for item in assessments[:5]:
        lines.append(f"- {item.get('requirement_id')}: {item.get('reuse_level')} `{item.get('candidate_title')}`; validate via `{item.get('validation_task')}`")
    if promotions:
        lines.extend(["", "## Promotion Candidates", ""])
        for item in promotions:
            lines.append(f"- {build_wikilink(item['target_ref'], item['title'])}: {item['reason']}")
    lines.extend(["", "## Sources", "", f"- Requirement analysis: {build_wikilink(f'{theme}/outputs/requirement-analysis.md', 'requirement-analysis')}"])
    return "\n".join(lines).rstrip() + "\n"


def render_engineering_brief(theme: str, assessments: list[dict[str, Any]]) -> str:
    high_risk = [item for item in assessments if item.get("reuse_cost") == "high" or item.get("license_status") in {"unknown", "review_required", "incompatible_risk"}]
    low_risk = [item for item in assessments if item.get("reuse_cost") in {"low", "medium"} and item.get("license_status") == "compatible"]
    lines = [
        "# Engineering Brief",
        "",
        "## Summary",
        "",
        f"- Target project: {build_wikilink(f'{theme}/README.md', PurePosixPath(theme).name)}",
        f"- Candidate assets assessed: {len(assessments)}",
        f"- High-risk candidates: {len(high_risk)}",
        "- Confidence: inferred",
        "",
        "## Engineering Impact",
        "",
        f"- Confirmed: {len(low_risk)} candidate(s) have compatible license and bounded reuse cost.",
        f"- Inferred: {len(assessments)} candidate(s) need implementation validation before commitment.",
        f"- Tentative: {len(high_risk)} candidate(s) require license, coupling, or evidence review.",
        "",
        "## Reuse Strategy",
        "",
    ]
    if assessments:
        for item in assessments[:8]:
            lines.append(f"- {item.get('requirement_id')}: use `{item.get('candidate_title')}` as `{item.get('reuse_level')}` with `{item.get('reuse_cost')}` reuse cost.")
    else:
        lines.append("- No deterministic reuse strategy was found; run manual discovery before implementation.")
    lines.extend(["", "## Risks", ""])
    for item in high_risk[:8]:
        lines.append(f"- {item.get('requirement_id')} / `{item.get('candidate_title')}`: {item.get('main_risk')}")
    if not high_risk:
        lines.append("- No high-risk deterministic candidates; still validate source evidence before delivery.")
    lines.extend(
        [
            "",
            "## Technical Options",
            "",
            "| Option | Best fit | Trade-off | Evidence | Recommendation |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in assessments[:8]:
        evidence = ", ".join(item.get("evidence_paths") or []) or "missing"
        recommendation = "proceed after validation" if item.get("license_status") == "compatible" else "review before reuse"
        lines.append(
            "| {option} | {best_fit} | {tradeoff} | {evidence} | {recommendation} |".format(
                option=table_escape(str(item.get("candidate_title") or item.get("candidate_ref") or "")),
                best_fit=table_escape(str(item.get("requirement_id") or "")),
                tradeoff=table_escape(f"{item.get('reuse_level')} / {item.get('reuse_cost')} / {item.get('license_status')}"),
                evidence=table_escape(evidence),
                recommendation=table_escape(recommendation),
            )
        )
    if not assessments:
        lines.append("| manual discovery | unmapped requirements | no deterministic candidates | missing | run asset search |")
    lines.extend(
        [
            "",
            "## Constraints",
            "",
            f"- Architecture: validate module boundaries for {len(assessments)} reuse candidate(s).",
            f"- Data: confirm input/output contracts for candidates before implementation.",
            "- Operations: treat unavailable vulnerability or activity signals as review items.",
            "- Evaluation: convert validation tasks into acceptance checks.",
            "",
            "## Recommended Next Actions",
            "",
        ]
    )
    for item in assessments[:5]:
        lines.append(f"- {item.get('requirement_id')}: {item.get('validation_task') or 'manual validation required'}")
    if not assessments:
        lines.append("- Run manual asset discovery and update requirement-analysis evidence.")
    lines.extend(["", "## Sources", "", f"- Requirement analysis: {build_wikilink(f'{theme}/outputs/requirement-analysis.md', 'requirement-analysis')}"])
    return "\n".join(lines).rstrip() + "\n"


def render_implementation_guide(theme: str, assessments: list[dict[str, Any]]) -> str:
    boundary_groups: dict[str, list[dict[str, Any]]] = {}
    for item in assessments:
        boundary_groups.setdefault(str(item.get("candidate_kind") or "candidate"), []).append(item)
    lines = [
        "# Implementation Guide",
        "",
        "## Summary",
        "",
        f"- Goal: deliver {build_wikilink(f'{theme}/outputs/requirement-analysis.md', 'requirement-analysis')} with validated reuse choices.",
        f"- Target project or workflow: {build_wikilink(f'{theme}/README.md', PurePosixPath(theme).name)}",
        "- Confidence: inferred",
        "",
        "## Module Boundaries",
        "",
    ]
    for kind, items in sorted(boundary_groups.items()):
        titles = ", ".join(str(item.get("candidate_title") or item.get("candidate_ref") or "candidate") for item in items[:4])
        lines.append(f"- Module: `{kind}`. Responsibility: evaluate {titles or 'candidate assets'}. Out of scope: unverified source rewrites.")
    if not boundary_groups:
        lines.append("- Module: manual discovery. Responsibility: identify candidate assets. Out of scope: implementation lock-in.")
    lines.extend(
        [
        "",
        "## Milestones",
        "",
        "| Milestone | Goal | Reuse checkpoint | Acceptance signal |",
        "| --- | --- | --- | --- |",
        "| M0 | Confirm requirement scope and acceptance criteria | Review requirement-analysis evidence | Approved requirement set |",
        "| M1 | Validate selected reuse candidates with small spikes | Run validation tasks | Spike notes linked to evidence |",
        "| M2 | Implement target modules with source-linked decisions | Apply accepted reuse decisions | Tests pass with traceable sources |",
        "| M3 | Run tests and update target outputs | Refresh briefs/backlog | Delivery artifacts updated |",
        "",
        "## Task Breakdown",
        "",
        "- Task: confirm candidate fit. Depends on: requirement-analysis. Evidence: asset-match-brief. Acceptance signal: selected candidate list.",
        "- Task: implement adaptation. Depends on: validation spike. Evidence: engineering-brief. Acceptance signal: passing tests.",
        "- Task: update delivery docs. Depends on: implementation result. Evidence: decision-brief. Acceptance signal: refreshed outputs.",
        "",
        "## Reuse And Adaptation Plan",
        "",
        ]
    )
    for item in assessments[:12]:
        evidence = ", ".join(item.get("evidence_paths") or []) or "missing"
        rejection = "license/coupling review fails" if item.get("license_status") != "compatible" else "validation task fails"
        lines.append(f"- Candidate asset: `{item.get('candidate_title')}`. Adaptation work: `{item.get('reuse_level')}` with `{item.get('reuse_cost')}` cost. License/coupling check: `{item.get('license_status')}`. Rejection criteria: {rejection}. Evidence: {evidence}.")
    if not assessments:
        lines.append("- Candidate asset: manual discovery required. Adaptation work: unknown. License/coupling check: manual validation required. Rejection criteria: missing evidence.")
    lines.extend(
        [
            "",
            "## Interfaces And Data Flow",
            "",
            "- Input: requirement-analysis items and candidate evidence paths.",
            "- Output: implemented target modules plus refreshed synthesis outputs.",
            "- Dependencies: accepted reuse candidates, license/coupling review, validation tasks.",
            "- Failure modes: missing evidence, incompatible license risk, high coupling, unavailable vulnerability signals.",
            "",
            "## Test Strategy",
            "",
            "- Unit: cover adapted module behavior and boundary contracts.",
            "- Integration: verify target workflow against reused dependencies.",
            "- Evaluation: convert each validation task into an acceptance test or spike report before implementation lock-in.",
            "- Regression: rerun synthesize and lint after implementation.",
            "",
            "## Rollout Notes",
            "",
            "- Migration: keep source assets read-only until validated.",
            "- Observability: log accepted reuse decisions and failed validation tasks.",
            "- Revert path: fall back to reference-only implementation if validation fails.",
            "",
            "## Sources",
            "",
            f"- Requirement analysis: {build_wikilink(f'{theme}/outputs/requirement-analysis.md', 'requirement-analysis')}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_decision_brief(theme: str, assessments: list[dict[str, Any]]) -> str:
    direct = [item for item in assessments if item.get("reuse_level") in {"direct", "adapt"} and item.get("license_status") != "incompatible_risk"]
    rejected = [item for item in assessments if item.get("license_status") == "incompatible_risk"]
    lines = [
        "# Decision Brief",
        "",
        "## Recommendation",
        "",
    ]
    if direct:
        lines.append(f"- Proceed with evidence-backed adaptation for {len(direct)} candidate(s), after validation tasks pass.")
    else:
        lines.append("- Treat candidates as reference material until stronger evidence or license review is available.")
    lines.extend(["", "## Options", ""])
    for item in assessments[:8]:
        lines.append(f"- {item.get('candidate_title')}: `{item.get('reuse_level')}` / `{item.get('reuse_cost')}` / license `{item.get('license_status')}`.")
    lines.extend(["", "## Rejected Or Deferred", ""])
    for item in rejected:
        lines.append(f"- {item.get('candidate_title')}: license status `{item.get('license_status')}` requires review before reuse.")
    if not rejected:
        lines.append("- None from deterministic checks.")
    return "\n".join(lines).rstrip() + "\n"


def render_shared_asset(promotion: dict[str, Any]) -> str:
    title = promotion["title"]
    source_refs = promotion.get("source_refs") or []
    themes = promotion.get("themes") or []
    lines = [
        "---",
        f"title: {title}",
        "node_type: asset",
        "status: proposed",
        "confidence: inferred",
        "themes:",
        *(f"  - {theme}" for theme in themes),
        "source_refs:",
        *(f"  - {ref}" for ref in source_refs),
        "---",
        "",
        f"# {title}",
        "",
        "## Summary",
        "",
        "Promoted by confirmed synthesize because the capability was referenced by multiple themes.",
        "",
        "## Evidence",
        "",
    ]
    lines.extend(f"- {ref}" for ref in source_refs)
    lines.extend(["", "## Validation", "", "- Confirm ownership, API boundary, license status, and reuse cost before marking active."])
    return "\n".join(lines).rstrip() + "\n"


def render_theme_asset_link(existing: str, promotion: dict[str, Any]) -> str:
    link = build_wikilink(promotion["target_ref"], promotion["title"])
    if link in existing:
        return existing.rstrip() + "\n"
    section = "## Shared Asset Links"
    bullet = f"- {link} - promoted by confirmed synthesize."
    content = existing.rstrip()
    if section in content:
        return content + "\n" + bullet + "\n"
    return content + "\n\n" + section + "\n\n" + bullet + "\n"


def render_technical_assets_index(root: Path, promotions: list[dict[str, Any]]) -> str:
    path = root / "index" / "technical-assets.md"
    existing = read_text(path, max_chars=0).rstrip() if path.exists() else "# Technical Assets\n"
    additions = []
    for item in promotions:
        link = build_wikilink(item["target_ref"], item["title"])
        bullet = f"- {link} - promoted by synthesize; status proposed."
        if bullet not in existing:
            additions.append(bullet)
    if not additions:
        return existing.rstrip() + "\n"
    if "## Shared Assets" in existing:
        return existing.rstrip() + "\n" + "\n".join(additions) + "\n"
    return existing.rstrip() + "\n\n## Shared Assets\n\n" + "\n".join(additions) + "\n"


def build_synthesis_pipeline(root: Path, target_theme: str, *, top: int = 20, max_chars: int = DEFAULT_MAX_CHARS, search_mode: str = "auto") -> dict[str, Any]:
    root = root.resolve()
    matches = match_assets(root, target_theme, top=top, max_chars=max_chars, search_mode=search_mode)
    licenses = check_license(root, target_theme, top=top, search_mode=search_mode, match_payload=matches)
    reuse = assess_reuse(root, target_theme, top=top, search_mode=search_mode, match_payload=matches, license_payload=licenses)
    outputs = generate_outputs(root, target_theme, top=top, search_mode=search_mode, reuse_payload=reuse)
    return {
        "schema_version": "llm-wiki-synthesize-pipeline.v1",
        "root": str(root),
        "target_theme": clean_theme_path(target_theme),
        "requirements": parse_requirements(root, target_theme),
        "matches": matches,
        "license_checks": licenses,
        "reuse_assessment": reuse,
        "generated_outputs": outputs,
    }


def apply_generated_outputs(root: Path, payload: dict[str, Any], *, confirm: str) -> dict[str, Any]:
    if confirm != CONFIRM_WRITE:
        return {"status": "needs_confirmation", "error": f'write tools require confirm="{CONFIRM_WRITE}"'}
    applied = []
    denied = []
    for change in payload.get("proposed_changes") or []:
        rel_path = str(change.get("path") or "")
        target = safe_write_path(root, rel_path)
        if target is None:
            denied.append({"path": rel_path, "error": "unsafe path"})
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            denied.append({"path": rel_path, "error": f"mkdir failed: {exc}"})
            continue
        tmp_path = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp_path.write_text(str(change.get("content") or ""), encoding="utf-8")
        except OSError as exc:
            denied.append({"path": rel_path, "error": f"write failed: {exc}"})
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            continue
        try:
            tmp_path.replace(target)
            applied.append({"action": change.get("action", "write"), "path": rel_path})
        except OSError as exc:
            denied.append({"path": rel_path, "error": f"replace failed: {exc}"})
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
    status = "ok" if not denied else "partial"
    log_synthesize_operation(
        root,
        payload.get("target_theme", ""),
        action="synthesize",
        status=status,
        details=[f"applied={', '.join(item['path'] for item in applied) or 'none'}"],
    )
    return {"status": status, "applied": applied, "denied": denied}
