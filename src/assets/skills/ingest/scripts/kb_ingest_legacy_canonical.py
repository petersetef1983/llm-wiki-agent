#!/usr/bin/env python3
"""Legacy canonical proposal helpers for ingest workflows."""

from __future__ import annotations

from kb_ingest_core import *
from kb_ingest_documents import (
    extract_document,
    render_payload_content,
    resolve_ingest_source,
)

DOCUMENT_NOISE_TERMS = {
    "first edition",
    "revision history",
    "table of contents",
    "first release",
    "release details",
    "copyright",
    "printed in the united states of america",
    "united states of america",
}
DOCUMENT_NOISE_PATTERNS = (
    re.compile(r"\bisbn\b", re.IGNORECASE),
    re.compile(r"\btable of contents\b", re.IGNORECASE),
    re.compile(r"\brevision history\b", re.IGNORECASE),
    re.compile(r"\bfirst edition\b", re.IGNORECASE),
    re.compile(r"\bfirst release\b", re.IGNORECASE),
    re.compile(r"^part [ivx]+$", re.IGNORECASE),
    re.compile(r"^\d+\.$"),
    re.compile(r"^[A-Z]{2}\s+\d{5}(?:-\d{4})?$"),
)
GENERIC_TRAILING_WORDS = {
    "applications",
    "application",
    "language",
    "science",
    "art",
    "edition",
    "history",
    "contents",
    "release",
    "introduction",
}
ROLE_TRAILING_WORDS = {
    "editor",
    "designer",
    "illustrator",
    "proofreader",
    "copyeditor",
    "indexer",
}
CONCEPT_TRAILING_WORDS = {
    "models",
    "modeling",
    "applications",
    "application",
    "behavior",
    "behaviors",
    "pass",
    "design",
    "taxonomy",
    "tax",
}
PERSON_CONNECTOR_WORDS = {"de", "del", "der", "di", "la", "van", "von"}
NON_NAME_WORDS = {
    "are",
    "is",
    "was",
    "were",
    "basic",
    "avoiding",
    "prompt",
    "engineering",
    "language",
    "languages",
    "application",
    "applications",
    "building",
    "science",
    "art",
    "edition",
    "history",
    "contents",
    "editor",
    "acquisitions",
    "production",
    "development",
    "copyeditor",
    "proofreader",
    "introduction",
    "foundations",
    "data",
    "tax",
}
ORGANIZATION_SUFFIXES = {
    "media",
    "labs",
    "lab",
    "inc",
    "corp",
    "corporation",
    "company",
    "foundation",
    "institute",
    "university",
    "technologies",
    "technology",
    "systems",
    "studio",
    "studios",
}

def title_from_file_stem(stem: str) -> str:
    parts = [part for part in re.split(r"[-_.\s]+", stem.strip()) if part]
    if not parts:
        return ""
    return " ".join(part.upper() if part.isupper() else part.capitalize() for part in parts)


def derive_title_candidate_terms(title: str) -> list[str]:
    normalized_title = normalize_candidate_term(title)
    if not is_valid_candidate_term(normalized_title):
        return []
    return [normalized_title]


def is_probable_person_name(term: str) -> bool:
    words = [part for part in re.split(r"[\s-]+", term.strip()) if part]
    if not 2 <= len(words) <= 4:
        return False
    lowered = term.lower()
    if any(hint in lowered for hint in CONCEPT_HINTS) or any(hint in lowered for hint in ENTITY_HINTS):
        return False
    for word in words:
        if word.lower() in PERSON_CONNECTOR_WORDS:
            continue
        if word.lower() in NON_NAME_WORDS:
            return False
        if not re.fullmatch(r"[A-Z][a-z]+(?:'[A-Z][a-z]+)?", word):
            return False
    return True


def is_probable_organization_name(term: str) -> bool:
    words = [part for part in re.split(r"[\s-]+", term.strip()) if part]
    if len(words) < 1:
        return False
    if words[-1].lower().rstrip(".") in ORGANIZATION_SUFFIXES:
        return True
    return any(word.isupper() and len(word) >= 2 for word in words)


def is_document_noise_term(term: str) -> bool:
    cleaned = normalize_candidate_term(term)
    lowered = cleaned.lower()
    if lowered in DOCUMENT_NOISE_TERMS:
        return True
    if any(pattern.search(cleaned) for pattern in DOCUMENT_NOISE_PATTERNS):
        return True

    words = [part for part in re.split(r"[\s-]+", cleaned) if part]
    has_concept_signal = any(hint in lowered for hint in CONCEPT_HINTS)
    has_entity_signal = any(hint in lowered for hint in ENTITY_HINTS)
    if len(words) >= 2 and words[0].lower() == "the" and not has_concept_signal and not has_entity_signal:
        return True
    if len(words) >= 2 and not has_concept_signal and not has_entity_signal:
        if is_probable_person_name(cleaned) or is_probable_organization_name(cleaned):
            return False
        if words[-1].lower() in ROLE_TRAILING_WORDS:
            return True
        if any(word.lower() in NON_NAME_WORDS for word in words):
            return True
        if words[-1].lower() in GENERIC_TRAILING_WORDS:
            return True
    return False


def infer_document_node_type(term: str) -> str:
    lowered = term.lower()
    if any(hint in lowered for hint in CONCEPT_HINTS):
        return "concept"
    words = [part for part in re.split(r"[\s-]+", lowered) if part]
    if words and words[-1] in CONCEPT_TRAILING_WORDS:
        return "concept"
    if is_probable_person_name(term) or is_probable_organization_name(term):
        return "entity"
    return infer_node_type_for_term(term)


def has_strong_document_signal(term: str) -> bool:
    lowered = term.lower()
    return (
        is_probable_organization_name(term)
        or any(hint in lowered for hint in CONCEPT_HINTS)
        or any(hint in lowered for hint in ENTITY_HINTS)
    )


def build_document_candidate_terms(payload: dict[str, Any]) -> list[str]:
    weighted_terms: list[str] = []
    metadata = payload.get("metadata", {})

    for key in ("title", "Title", "subject", "Subject"):
        value = metadata.get(key)
        if isinstance(value, str):
            for candidate in derive_title_candidate_terms(value):
                weighted_terms.extend([candidate, candidate, candidate])

    file_title = normalize_candidate_term(title_from_file_stem(Path(payload.get("file_name", "")).stem))
    for candidate in derive_title_candidate_terms(file_title):
        weighted_terms.extend([candidate, candidate])

    parser = str(payload.get("parser", "")).lower()
    confidence = str(payload.get("confidence", "")).lower()
    warning_blob = " ".join(str(item) for item in payload.get("warnings", [])).lower()
    if confidence == "low" or parser in {"binary_strings_fallback", "unparsed_pdf"} or "printable-string fallback" in warning_blob:
        return weighted_terms

    text = payload.get("text", "") or ""
    weighted_terms.extend(extract_candidate_terms_from_markdown(text))
    return weighted_terms


def maybe_normalize_evidence_ref(root: Path, source_path: Path | str) -> str | None:
    resolved_source = resolve_ingest_source(source_path)
    if resolved_source.is_url:
        return resolved_source.locator
    if resolved_source.local_path is None:
        return None
    try:
        return normalize_reference(resolved_source.local_path.relative_to(root.resolve()).as_posix(), root)
    except ValueError:
        return str(resolved_source.local_path)


def derive_document_context(root: Path, theme_ref: str | None, page_refs: list[str]) -> tuple[str | None, list[str], str | None]:
    normalized_pages = unique_preserve_order([normalize_reference(item, root) for item in page_refs if normalize_reference(item, root)])
    normalized_theme_readme = normalize_reference(theme_ref, root) if theme_ref else None
    if not normalized_theme_readme and normalized_pages:
        normalized_theme_readme = infer_theme_readme_ref_from_page(root, normalized_pages[0])
    primary_page = normalized_pages[0] if normalized_pages else normalized_theme_readme
    context_pages = unique_preserve_order(([normalized_theme_readme] if normalized_theme_readme else []) + normalized_pages)
    return normalized_theme_readme, context_pages, primary_page


def build_document_follow_up_command(
    *,
    theme_readme_ref: str | None,
    primary_page: str | None,
    evidence_ref: str | None,
    title: str,
    node_type: str,
    existing_canonical_ref: str | None = None,
    existing_title: str | None = None,
) -> str | None:
    if existing_canonical_ref:
        if not primary_page:
            return None
        command = f"link-canonical --page {primary_page} --canonical {existing_canonical_ref}"
        if existing_title:
            command += f' --label "{existing_title}"'
        return command

    if not theme_readme_ref and not primary_page:
        return None

    page_ref = primary_page or theme_readme_ref
    command = f'promote-{node_type} --title "{title}"'
    if theme_readme_ref:
        command += f" --theme {theme_readme_ref}"
    if page_ref:
        command += f" --source-page {page_ref} --link-page {page_ref}"
    if evidence_ref:
        command += f' --evidence-from "{evidence_ref}"'
    for tag in suggest_tags_for_term(node_type, title)[1:-1]:
        command += f" --tag {tag}"
    return command


def suggest_document_canonical_nodes(
    root: Path,
    *,
    source_path: Path | str,
    theme_ref: str | None,
    page_refs: list[str],
    limit: int,
    include_existing: bool,
    max_chars: int,
    max_rows: int,
    max_cols: int,
) -> dict[str, Any]:
    extraction = extract_document(source_path, max_chars, max_rows, max_cols)
    theme_readme_ref, context_pages, primary_page = derive_document_context(root, theme_ref, page_refs)
    registry = build_canonical_registry(root)
    evidence_ref = maybe_normalize_evidence_ref(root, source_path)

    candidates: dict[str, dict[str, Any]] = {}
    for term in build_document_candidate_terms(extraction):
        key = term.lower()
        info = candidates.setdefault(
            key,
            {
                "title": term,
                "hits": 0,
                "sources": [],
            },
        )
        info["hits"] += 1
        if context_pages:
            for page_ref in context_pages:
                if page_ref not in info["sources"]:
                    info["sources"].append(page_ref)
        elif evidence_ref and evidence_ref not in info["sources"]:
            info["sources"].append(evidence_ref)

    suggestions: list[dict[str, Any]] = []
    for key, info in candidates.items():
        if is_document_noise_term(info["title"]):
            continue
        existing = registry.get(key)
        if existing and not include_existing:
            continue
        if info["hits"] < 2 and existing is None and not has_strong_document_signal(info["title"]):
            continue
        node_type = existing["node_type"] if existing else infer_document_node_type(info["title"])
        command = build_document_follow_up_command(
            theme_readme_ref=theme_readme_ref,
            primary_page=primary_page,
            evidence_ref=evidence_ref,
            title=info["title"],
            node_type=node_type,
            existing_canonical_ref=existing["canonical_ref"] if existing else None,
            existing_title=existing["title"] if existing else None,
        )
        suggestion = {
            "title": info["title"],
            "suggested_node_type": node_type,
            "preferred_canonical_ref": existing["canonical_ref"] if existing else preferred_canonical_ref_for_term(node_type, info["title"]),
            "hits": info["hits"],
            "sources": info["sources"],
            "existing_canonical_ref": existing["canonical_ref"] if existing else None,
            "recommended_action": "link-existing" if existing else f"promote-{node_type}",
            "suggested_tags": suggest_tags_for_term(node_type, info["title"]),
            "command": command,
            "blocking_reason": None if command else "Provide --theme or --page so follow-up promote/link commands can be generated.",
        }
        suggestions.append(suggestion)

    suggestions.sort(key=lambda item: (-item["hits"], item["title"].lower()))
    return {
        "source_document": evidence_ref or str(source_path),
        "theme": theme_ref_from_readme_ref(theme_readme_ref) if theme_readme_ref else None,
        "theme_readme": theme_readme_ref,
        "context_pages": context_pages,
        "primary_page": primary_page,
        "extraction": {
            "file_name": extraction["file_name"],
            "file_type": extraction["file_type"],
            "parser": extraction["parser"],
            "confidence": extraction["confidence"],
            "warnings": extraction["warnings"],
            "text_excerpt": extraction["text_excerpt"],
        },
        "suggestions": suggestions[:limit],
    }


def print_document_suggestions_text(payload: dict[str, Any]) -> None:
    extraction = payload["extraction"]
    print("Document canonical proposals:")
    print(f"- source={payload['source_document']}")
    if payload["theme_readme"]:
        print(f"- theme={payload['theme_readme']}")
    if payload["primary_page"]:
        print(f"- primary_page={payload['primary_page']}")
    print(f"- parser={extraction['parser']} confidence={extraction['confidence']} type={extraction['file_type']}")
    if extraction["warnings"]:
        print("- warnings:")
        for warning in extraction["warnings"]:
            print(f"  - {warning}")
    print("- suggestions:")
    for item in payload["suggestions"]:
        print(f"  - {item['title']} [{item['suggested_node_type']}] action={item['recommended_action']} hits={item['hits']}")
        if item["existing_canonical_ref"]:
            print(f"    - existing={item['existing_canonical_ref']}")
        if item["command"]:
            print(f"    - command={item['command']}")
        elif item["blocking_reason"]:
            print(f"    - blocked={item['blocking_reason']}")


def select_document_suggestions(
    suggestions: list[dict[str, Any]],
    *,
    selected_titles: list[str],
    apply_all: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    if apply_all:
        return suggestions, []

    requested = unique_preserve_order(selected_titles)
    if not requested:
        raise ValueError("Provide --title at least once, or use --all to apply every returned suggestion.")

    by_lower = {item["title"].lower(): item for item in suggestions}
    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    for title in requested:
        match = by_lower.get(title.lower())
        if match is None:
            missing.append(title)
            continue
        selected.append(match)
    return selected, missing


def normalize_optional_reference(root: Path, reference: str | None) -> str | None:
    if not reference:
        return None
    if is_url_source(reference):
        return reference
    try:
        return normalize_reference(reference, root)
    except Exception:
        return None


def execute_document_suggestions(
    root: Path,
    *,
    suggestions: list[dict[str, Any]],
    source_document_ref: str | None,
    theme_readme_ref: str | None,
    primary_page: str | None,
    extraction_confidence: str,
    dry_run: bool,
) -> dict[str, Any]:
    evidence_ref = normalize_optional_reference(root, source_document_ref)
    applied: list[dict[str, Any]] = []
    planned: list[dict[str, Any]] = []
    auto_linked_pages: list[dict[str, Any]] = []

    for item in suggestions:
        if item.get("blocking_reason"):
            planned.append(
                {
                    "title": item["title"],
                    "mode": "blocked",
                    "command": item.get("command"),
                    "blocking_reason": item["blocking_reason"],
                }
            )
            continue

        if item["recommended_action"] == "link-existing":
            if not primary_page or not item.get("existing_canonical_ref"):
                planned.append(
                    {
                        "title": item["title"],
                        "mode": "blocked",
                        "command": item.get("command"),
                        "blocking_reason": "Existing canonical link requires a primary theme page and canonical ref.",
                    }
                )
                continue
            operation = {
                "title": item["title"],
                "mode": "link-existing",
                "canonical_ref": item["existing_canonical_ref"],
                "page": primary_page,
                "command": item.get("command"),
            }
            if dry_run:
                planned.append(operation)
            else:
                operation["result"] = link_canonical_page(
                    root,
                    page_ref=primary_page,
                    canonical_ref=item["existing_canonical_ref"],
                    label=item["title"],
                )
                if theme_readme_ref:
                    operation["auto_linked_pages"] = auto_link_theme_mentions(
                        root,
                        theme_readme_ref=theme_readme_ref,
                        canonical_ref=item["existing_canonical_ref"],
                        label=item["title"],
                        exclude_pages=[primary_page] if primary_page else [],
                    )
                    auto_linked_pages.extend(operation["auto_linked_pages"])
                applied.append(operation)
            continue

        operation = {
            "title": item["title"],
            "mode": item["recommended_action"],
            "node_type": item["suggested_node_type"],
            "command": item.get("command"),
        }
        if dry_run:
            planned.append(operation)
            continue

        promote_payload = upsert_canonical_page(
            root,
            node_type=item["suggested_node_type"],
            title=item["title"],
            slug=None,
            aliases=[],
            tags=item.get("suggested_tags", []),
            status="tentative" if extraction_confidence == "low" else "active",
            theme_refs=[theme_readme_ref] if theme_readme_ref else [],
            page_refs=[primary_page] if primary_page else [],
            evidence_from=[evidence_ref] if evidence_ref else [],
            related_entities=[],
            related_concepts=[],
            related_patterns=[],
            related_methods=[],
        )
        linked_pages: list[dict[str, Any]] = []
        if primary_page:
            linked_pages.append(
                link_canonical_page(
                    root,
                    page_ref=primary_page,
                    canonical_ref=promote_payload["canonical_ref"],
                    label=item["title"],
                )
            )
        operation["canonical_ref"] = promote_payload["canonical_ref"]
        operation["result"] = promote_payload
        operation["linked_pages"] = linked_pages
        if theme_readme_ref:
            operation["auto_linked_pages"] = auto_link_theme_mentions(
                root,
                theme_readme_ref=theme_readme_ref,
                canonical_ref=promote_payload["canonical_ref"],
                label=item["title"],
                aliases=promote_payload.get("aliases", []),
                exclude_pages=[primary_page] if primary_page else [],
            )
            auto_linked_pages.extend(operation["auto_linked_pages"])
        applied.append(operation)

    sync_payload: dict[str, Any] | None = None
    if theme_readme_ref and not dry_run and applied:
        sync_payload = sync_theme_graph(root, theme_readme_ref=theme_readme_ref, page_refs=[primary_page] if primary_page else [])

    return {
        "planned_operations": planned,
        "applied_operations": applied,
        "applied_count": len(applied),
        "auto_linked_pages": auto_linked_pages,
        "sync_theme_graph": sync_payload,
    }


def apply_document_canonical_nodes(
    root: Path,
    *,
    source_path: Path | str,
    theme_ref: str | None,
    page_refs: list[str],
    selected_titles: list[str],
    apply_all: bool,
    dry_run: bool,
    limit: int,
    include_existing: bool,
    max_chars: int,
    max_rows: int,
    max_cols: int,
) -> dict[str, Any]:
    source_label = resolve_ingest_source(source_path).display_name
    proposal = suggest_document_canonical_nodes(
        root,
        source_path=source_path,
        theme_ref=theme_ref,
        page_refs=page_refs,
        limit=limit,
        include_existing=include_existing,
        max_chars=max_chars,
        max_rows=max_rows,
        max_cols=max_cols,
    )
    selected, missing_titles = select_document_suggestions(
        proposal["suggestions"],
        selected_titles=selected_titles,
        apply_all=apply_all,
    )

    execution = execute_document_suggestions(
        root,
        suggestions=selected,
        source_document_ref=maybe_normalize_evidence_ref(root, source_path),
        theme_readme_ref=proposal["theme_readme"],
        primary_page=proposal["primary_page"],
        extraction_confidence=proposal["extraction"]["confidence"],
        dry_run=dry_run,
    )

    if not dry_run and execution["applied_operations"]:
        append_recent_update(
            root,
            f"基于文档 `{source_label}` 应用 {execution['applied_count']} 条 canonical proposal，并同步主题图谱。",
        )

    return {
        "source_document": proposal["source_document"],
        "theme": proposal["theme"],
        "theme_readme": proposal["theme_readme"],
        "primary_page": proposal["primary_page"],
        "extraction": proposal["extraction"],
        "selected_titles": [item["title"] for item in selected],
        "missing_titles": missing_titles,
        "dry_run": dry_run,
        **execution,
    }


def print_document_apply_text(payload: dict[str, Any]) -> None:
    print("Document canonical apply:")
    print(f"- source={payload['source_document']}")
    if payload["theme_readme"]:
        print(f"- theme={payload['theme_readme']}")
    if payload["primary_page"]:
        print(f"- primary_page={payload['primary_page']}")
    print(f"- dry_run={payload['dry_run']}")
    print(f"- selected={', '.join(payload['selected_titles']) or 'none'}")
    if payload["missing_titles"]:
        print(f"- missing_titles={', '.join(payload['missing_titles'])}")
    if payload["planned_operations"]:
        print("- planned_operations:")
        for item in payload["planned_operations"]:
            print(f"  - {item['title']} [{item['mode']}]")
            if item.get("command"):
                print(f"    - command={item['command']}")
            if item.get("blocking_reason"):
                print(f"    - blocked={item['blocking_reason']}")
    if payload["applied_operations"]:
        print("- applied_operations:")
        for item in payload["applied_operations"]:
            suffix = f" canonical={item['canonical_ref']}" if item.get("canonical_ref") else ""
            print(f"  - {item['title']} [{item['mode']}] {suffix}".rstrip())
    if payload["sync_theme_graph"]:
        print(f"- sync_theme_graph links={payload['sync_theme_graph']['link_count']}")


def write_json_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json_payload(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def build_document_proposal_file_payload(
    root: Path,
    *,
    source_path: Path | str,
    theme_ref: str | None,
    page_refs: list[str],
    limit: int,
    include_existing: bool,
    max_chars: int,
    max_rows: int,
    max_cols: int,
) -> dict[str, Any]:
    proposal = suggest_document_canonical_nodes(
        root,
        source_path=source_path,
        theme_ref=theme_ref,
        page_refs=page_refs,
        limit=limit,
        include_existing=include_existing,
        max_chars=max_chars,
        max_rows=max_rows,
        max_cols=max_cols,
    )
    return {
        "schema_version": "document-canonical-proposal/v1",
        "proposal_type": "document_canonical_nodes",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_document": proposal["source_document"],
        "theme": proposal["theme"],
        "theme_readme": proposal["theme_readme"],
        "context_pages": proposal["context_pages"],
        "primary_page": proposal["primary_page"],
        "extraction": proposal["extraction"],
        "suggestions": [
            {
                **item,
                "review_status": "pending",
                "review_notes": "",
                "reviewed_at": None,
                "apply_status": "not_applied",
                "applied_at": None,
            }
            for item in proposal["suggestions"]
        ],
    }


def validate_document_proposal_payload(payload: dict[str, Any]) -> None:
    if payload.get("proposal_type") != "document_canonical_nodes":
        raise ValueError("Unsupported proposal file type.")
    if not isinstance(payload.get("suggestions"), list):
        raise ValueError("Proposal file does not contain a `suggestions` list.")


def update_document_proposal_reviews(
    payload: dict[str, Any],
    *,
    titles: list[str],
    status: str,
    note: str,
) -> dict[str, Any]:
    validate_document_proposal_payload(payload)
    requested = unique_preserve_order(titles)
    lookup = {item["title"].lower(): item for item in payload["suggestions"]}
    updated: list[str] = []
    missing: list[str] = []
    reviewed_at = datetime.now().isoformat(timespec="seconds")
    for title in requested:
        match = lookup.get(title.lower())
        if match is None:
            missing.append(title)
            continue
        match["review_status"] = status
        match["review_notes"] = note
        match["reviewed_at"] = reviewed_at
        updated.append(match["title"])
    payload["review_updated_at"] = reviewed_at
    return {"updated_titles": updated, "missing_titles": missing, "status": status, "note": note}


def select_approved_proposal_suggestions(
    payload: dict[str, Any],
    *,
    selected_titles: list[str],
    apply_all_approved: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    validate_document_proposal_payload(payload)
    approved = [item for item in payload["suggestions"] if item.get("review_status") == "approved"]
    if apply_all_approved:
        return approved, []
    requested = unique_preserve_order(selected_titles)
    if not requested:
        raise ValueError("Provide --title at least once, or use --all-approved to execute all approved suggestions.")
    lookup = {item["title"].lower(): item for item in approved}
    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    for title in requested:
        match = lookup.get(title.lower())
        if match is None:
            missing.append(title)
            continue
        selected.append(match)
    return selected, missing


def apply_document_proposal_file(
    root: Path,
    *,
    proposal_path: Path,
    selected_titles: list[str],
    apply_all_approved: bool,
    dry_run: bool,
) -> dict[str, Any]:
    payload = load_json_payload(proposal_path)
    validate_document_proposal_payload(payload)
    selected, missing_titles = select_approved_proposal_suggestions(
        payload,
        selected_titles=selected_titles,
        apply_all_approved=apply_all_approved,
    )
    execution = execute_document_suggestions(
        root,
        suggestions=selected,
        source_document_ref=payload.get("source_document"),
        theme_readme_ref=payload.get("theme_readme"),
        primary_page=payload.get("primary_page"),
        extraction_confidence=payload.get("extraction", {}).get("confidence", "low"),
        dry_run=dry_run,
    )

    if not dry_run:
        applied_titles = {item["title"] for item in execution["applied_operations"]}
        applied_at = datetime.now().isoformat(timespec="seconds")
        for item in payload["suggestions"]:
            if item["title"] in applied_titles:
                item["apply_status"] = "applied"
                item["applied_at"] = applied_at
        payload["last_applied_at"] = applied_at
        payload["last_apply_summary"] = {
            "applied_count": execution["applied_count"],
            "applied_titles": sorted(applied_titles),
            "dry_run": False,
        }
        write_json_payload(proposal_path, payload)
        if execution["applied_operations"]:
            append_recent_update(
                root,
                f"根据 proposal 文件 `{proposal_path.name}` 应用 {execution['applied_count']} 条 canonical proposal。",
            )

    return {
        "proposal_path": str(proposal_path),
        "source_document": payload.get("source_document"),
        "theme": payload.get("theme"),
        "theme_readme": payload.get("theme_readme"),
        "primary_page": payload.get("primary_page"),
        "selected_titles": [item["title"] for item in selected],
        "missing_titles": missing_titles,
        "dry_run": dry_run,
        **execution,
    }


def print_document_proposal_file_text(payload: dict[str, Any]) -> None:
    print("Document proposal file:")
    print(f"- source={payload['source_document']}")
    if payload.get("theme_readme"):
        print(f"- theme={payload['theme_readme']}")
    print(f"- suggestions={len(payload['suggestions'])}")
    for item in payload["suggestions"]:
        print(f"  - {item['title']} [{item['suggested_node_type']}] review={item['review_status']}")


def print_document_proposal_review_text(payload: dict[str, Any]) -> None:
    print("Document proposal review:")
    print(f"- proposal={payload['proposal_path']}")
    print(f"- updated_titles={', '.join(payload['updated_titles']) or 'none'}")
    if payload["missing_titles"]:
        print(f"- missing_titles={', '.join(payload['missing_titles'])}")
    if payload["status"]:
        print(f"- status={payload['status']}")

