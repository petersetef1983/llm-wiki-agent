#!/usr/bin/env python3
"""License and reuse assessment for deterministic synthesis."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from kb_synthesize_common import clean_theme_path, slugify
from kb_synthesize_search import match_assets

RISKY_LICENSE_TERMS = (
    "agpl",
    "gpl",
    "lgpl",
    "sspl",
    "elastic license",
    "elv2",
    "commons clause",
    "bsl",
    "bsl-1.1",
    "business source",
)
PERMISSIVE_LICENSE_TERMS = ("mit", "apache", "bsd", "isc", "mpl-2.0")
REVIEW_LICENSE_TERMS = ("conda", "anaconda", "unknown")


def license_term_matches(text: str, term: str) -> bool:
    escaped = re.escape(term.lower()).replace(r"\ ", r"[\s_-]+")
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


def license_status_for(value: str | None, signals: dict[str, Any] | None = None) -> str:
    # Conservative precedence: risk terms win over permissive terms when mixed
    # license text is ambiguous. Labels are engineering risk signals, not legal advice.
    signals = signals or {}
    values = [value or "", signals.get("license_risk") or "", *(signals.get("normalized_licenses") or [])]
    lowered = " ".join(str(item).lower() for item in values if item)
    if not lowered.strip() or license_term_matches(lowered, "unknown"):
        return "unknown"
    if any(license_term_matches(lowered, term) for term in RISKY_LICENSE_TERMS):
        return "incompatible_risk"
    if any(license_term_matches(lowered, term) for term in PERMISSIVE_LICENSE_TERMS):
        return "compatible"
    if "review_required" in lowered or signals.get("license_review_required") or any(license_term_matches(lowered, term) for term in REVIEW_LICENSE_TERMS):
        return "review_required"
    return "review_required"


def check_license(
    root: Path,
    target_theme: str,
    *,
    top: int = 20,
    search_mode: str = "auto",
    match_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    match_payload = match_payload or match_assets(root, target_theme, top=top, search_mode=search_mode)
    checks = []
    for match in match_payload.get("matches", []):
        status = license_status_for(match.get("license_type"), match.get("license_signals"))
        checks.append(
            {
                "requirement_id": match.get("requirement_id"),
                "candidate_ref": match.get("candidate_ref"),
                "candidate_title": match.get("candidate_title"),
                "license_type": match.get("license_type") or "unknown",
                "license_status": status,
                "engineering_note": "Engineering risk label only; not legal advice.",
                "review_required": status in {"unknown", "review_required", "incompatible_risk"},
            }
        )
    return {
        "schema_version": "llm-wiki-synthesize-license.v1",
        "root": str(root.resolve()),
        "target_theme": clean_theme_path(target_theme),
        "checks": checks,
    }


def assess_reuse(
    root: Path,
    target_theme: str,
    *,
    top: int = 20,
    search_mode: str = "auto",
    match_payload: dict[str, Any] | None = None,
    license_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    match_payload = match_payload or match_assets(root, target_theme, top=top, search_mode=search_mode)
    license_payload = license_payload or check_license(root, target_theme, top=top, search_mode=search_mode, match_payload=match_payload)
    license_by_key = {
        (item.get("requirement_id"), item.get("candidate_ref")): item
        for item in license_payload.get("checks", [])
    }
    assessments = []
    for match in match_payload.get("matches", []):
        license_check = license_by_key.get((match.get("requirement_id"), match.get("candidate_ref")), {})
        reuse_level = normalize_reuse_level(match.get("reuse_level_hint"), match.get("candidate_kind"))
        reuse_cost = normalize_reuse_cost(match.get("reuse_cost_hint"), license_check.get("license_status"), match.get("match_score"))
        risk_notes = reuse_risks(match, license_check, reuse_cost)
        assessments.append(
            {
                **match,
                "reuse_level": reuse_level,
                "reuse_cost": reuse_cost,
                "license_status": license_check.get("license_status", "unknown"),
                "main_risk": "; ".join(risk_notes) if risk_notes else "No major deterministic risk detected; validate with source evidence.",
                "validation_task": validation_task(match, reuse_level),
                "promotion_candidate": is_promotion_candidate(match, reuse_level, license_check),
            }
        )
    return {
        "schema_version": "llm-wiki-synthesize-reuse.v1",
        "root": str(root.resolve()),
        "target_theme": clean_theme_path(target_theme),
        "assessments": assessments,
    }


def normalize_reuse_level(value: Any, kind: Any) -> str:
    text = str(value or "").lower()
    if text in {"direct", "adapt", "reference", "reject"}:
        return text
    if kind == "shared_asset":
        return "adapt"
    if kind == "reuse_candidate":
        return "adapt"
    if kind == "open_source_module":
        return "reference"
    return "reference"


def normalize_reuse_cost(value: Any, license_status: Any, score: Any) -> str:
    text = str(value or "").lower()
    if text in {"low", "medium", "high"}:
        return text
    if license_status in {"unknown", "review_required", "incompatible_risk"}:
        return "high"
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        numeric_score = 0.0
    if numeric_score >= 0.65:
        return "low"
    if numeric_score >= 0.3:
        return "medium"
    return "high"


def reuse_risks(match: dict[str, Any], license_check: dict[str, Any], reuse_cost: str) -> list[str]:
    risks = []
    if license_check.get("license_status") in {"unknown", "review_required", "incompatible_risk"}:
        risks.append(f"license={license_check.get('license_status')}")
    if has_known_vulnerabilities(match.get("known_vulnerabilities")):
        risks.append("known_vulnerabilities_present")
    vulnerability_status = (match.get("vulnerability_signals") or {}).get("status")
    if vulnerability_status == "unavailable" or match.get("known_vulnerabilities") == "unavailable":
        risks.append("vulnerability_lookup_unavailable")
    if reuse_cost == "high":
        risks.append("high_reuse_cost")
    if match.get("match_score", 0) < 0.3:
        risks.append("weak_keyword_match")
    return risks


def has_known_vulnerabilities(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        vulnerabilities = value.get("vulnerabilities")
        return bool(vulnerabilities) if isinstance(vulnerabilities, list) else bool(value)
    return False


def validation_task(match: dict[str, Any], reuse_level: str) -> str:
    requirement_id = match.get("requirement_id") or "requirement"
    title = match.get("candidate_title") or match.get("candidate_ref") or "candidate"
    if reuse_level == "direct":
        return f"Verify {title} against {requirement_id} acceptance criteria."
    if reuse_level == "adapt":
        return f"Build a small adaptation spike for {title} and map gaps to {requirement_id}."
    return f"Use {title} as reference evidence and confirm implementation boundaries for {requirement_id}."


def is_promotion_candidate(match: dict[str, Any], reuse_level: str, license_check: dict[str, Any]) -> bool:
    if match.get("candidate_kind") not in {"reuse_candidate", "historical_project_page", "open_source_module"}:
        return False
    if reuse_level not in {"direct", "adapt"}:
        return False
    if license_check.get("license_status") == "incompatible_risk":
        return False
    return float(match.get("match_score") or 0) >= 0.3


def detect_promotion_candidates(root: Path, target_theme: str, assessments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    theme_refs: dict[str, set[str]] = defaultdict(set)
    for item in assessments:
        if not item.get("promotion_candidate"):
            continue
        title = str(item.get("candidate_title") or item.get("candidate_ref") or "").strip()
        if not title:
            continue
        key = slugify(title)
        grouped.setdefault(
            key,
            {
                "slug": key,
                "title": title,
                "source_refs": [],
                "requirement_ids": [],
                "target_ref": f"shared/assets/{key}.md",
            },
        )
        grouped[key]["source_refs"].extend(item.get("evidence_paths") or [])
        grouped[key]["requirement_ids"].append(item.get("requirement_id"))
        source_theme = str(item.get("source_theme") or "").strip()
        target = clean_theme_path(target_theme)
        if source_theme:
            theme_refs[key].add(source_theme)
        if target:
            theme_refs[key].add(target)

    candidates = []
    for key, item in grouped.items():
        refs = sorted(set(ref for ref in item["source_refs"] if ref))
        themes = sorted(theme for theme in theme_refs[key] if theme)
        if len(themes) < 2:
            continue
        candidates.append(
            {
                **item,
                "source_refs": refs,
                "themes": themes,
                "requirement_ids": sorted(set(req for req in item["requirement_ids"] if req)),
                "reason": "referenced by target synthesis and at least one source theme",
            }
        )
    return candidates
