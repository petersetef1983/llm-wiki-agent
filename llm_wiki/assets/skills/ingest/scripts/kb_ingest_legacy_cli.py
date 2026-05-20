#!/usr/bin/env python3
"""Legacy compatibility CLI for ingest canonical helpers."""

from __future__ import annotations

from kb_ingest_core import *
from kb_ingest_documents import *
from kb_ingest_legacy_canonical import *


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Legacy compatibility helpers for ingest workflows. "
            "These commands are for migration, debugging, or one-off deterministic backfills."
        )
    )
    parser.add_argument("--root", default=".", help="Knowledge base root directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    promote_entity = subparsers.add_parser("promote-entity", help="Create or update a canonical shared entity page")
    promote_entity.add_argument("--title", required=True, help="Canonical entity title")
    promote_entity.add_argument("--slug", help="Optional canonical slug")
    promote_entity.add_argument("--alias", action="append", default=[], help="Alias for the entity. Repeatable.")
    promote_entity.add_argument("--tag", action="append", default=[], help="Extra tag for the entity. Repeatable.")
    promote_entity.add_argument("--theme", action="append", default=[], help="Theme readme ref, e.g. themes/general/02-x/README")
    promote_entity.add_argument("--source-page", action="append", default=[], help="Source wiki page ref. Repeatable.")
    promote_entity.add_argument("--evidence-from", action="append", default=[], help="Raw source path supporting this node. Repeatable.")
    promote_entity.add_argument("--related-entity", action="append", default=[], help="Related canonical entity ref. Repeatable.")
    promote_entity.add_argument("--related-concept", action="append", default=[], help="Related canonical concept ref. Repeatable.")
    promote_entity.add_argument("--related-pattern", action="append", default=[], help="Related canonical pattern ref. Repeatable.")
    promote_entity.add_argument("--related-method", action="append", default=[], help="Related canonical method ref. Repeatable.")
    promote_entity.add_argument("--status", default="active", help="Node status, for example active/tentative/deprecated/archived")
    promote_entity.add_argument("--link-page", action="append", default=[], help="Theme page to patch with a wikilink to the canonical page")
    promote_entity.add_argument("--format", choices=["text", "json"], default="text")

    promote_concept = subparsers.add_parser("promote-concept", help="Create or update a canonical shared concept page")
    promote_concept.add_argument("--title", required=True, help="Canonical concept title")
    promote_concept.add_argument("--slug", help="Optional canonical slug")
    promote_concept.add_argument("--alias", action="append", default=[], help="Alias for the concept. Repeatable.")
    promote_concept.add_argument("--tag", action="append", default=[], help="Extra tag for the concept. Repeatable.")
    promote_concept.add_argument("--theme", action="append", default=[], help="Theme readme ref, e.g. themes/general/02-x/README")
    promote_concept.add_argument("--source-page", action="append", default=[], help="Source wiki page ref. Repeatable.")
    promote_concept.add_argument("--evidence-from", action="append", default=[], help="Raw source path supporting this node. Repeatable.")
    promote_concept.add_argument("--related-entity", action="append", default=[], help="Related canonical entity ref. Repeatable.")
    promote_concept.add_argument("--related-concept", action="append", default=[], help="Related canonical concept ref. Repeatable.")
    promote_concept.add_argument("--related-pattern", action="append", default=[], help="Related canonical pattern ref. Repeatable.")
    promote_concept.add_argument("--related-method", action="append", default=[], help="Related canonical method ref. Repeatable.")
    promote_concept.add_argument("--status", default="active", help="Node status, for example active/tentative/deprecated/archived")
    promote_concept.add_argument("--link-page", action="append", default=[], help="Theme page to patch with a wikilink to the canonical page")
    promote_concept.add_argument("--format", choices=["text", "json"], default="text")

    link_canonical = subparsers.add_parser("link-canonical", help="Link a theme page to a canonical shared node and refresh reverse relations")
    link_canonical.add_argument("--page", required=True, help="Markdown page path or ref to patch")
    link_canonical.add_argument("--canonical", required=True, help="Canonical shared node ref, e.g. shared/entities/llm-judge")
    link_canonical.add_argument("--label", help="Optional display text for the wikilink")
    link_canonical.add_argument("--format", choices=["text", "json"], default="text")

    suggest_nodes = subparsers.add_parser("suggest-canonical-nodes", help="Suggest canonical entities/concepts from a theme or a set of pages")
    suggest_nodes.add_argument("--theme", help="Theme readme ref, e.g. themes/general/02-x/README")
    suggest_nodes.add_argument("--page", action="append", default=[], help="Page ref to scan. Repeatable.")
    suggest_nodes.add_argument("--limit", type=int, default=8, help="Maximum number of suggestions to return")
    suggest_nodes.add_argument("--include-existing", action="store_true", help="Include terms that already have canonical pages")
    suggest_nodes.add_argument("--format", choices=["text", "json"], default="text")

    batch_link = subparsers.add_parser("batch-link-canonical", help="Link one or more pages to one or more canonical nodes")
    batch_link.add_argument("--page", action="append", required=True, help="Page ref to patch. Repeatable.")
    batch_link.add_argument("--canonical", action="append", required=True, help="Canonical ref to link. Repeatable.")
    batch_link.add_argument("--format", choices=["text", "json"], default="text")

    sync_graph = subparsers.add_parser("sync-theme-graph", help="Sync theme page graph from existing canonical links")
    sync_graph.add_argument("--theme", required=True, help="Theme readme ref, e.g. themes/general/02-x/README")
    sync_graph.add_argument("--page", action="append", default=[], help="Optional explicit page refs to scan instead of auto-discovering wiki pages")
    sync_graph.add_argument("--format", choices=["text", "json"], default="text")

    suggest_document_nodes = subparsers.add_parser(
        "suggest-document-canonical-nodes",
        help="Extract a source and propose canonical entities/concepts with follow-up commands",
    )
    suggest_document_nodes.add_argument("--input", required=True, help="Source path or URL")
    suggest_document_nodes.add_argument("--theme", help="Theme readme ref, e.g. themes/general/02-x/README")
    suggest_document_nodes.add_argument("--page", action="append", default=[], help="Theme page ref to use for follow-up commands. Repeatable.")
    suggest_document_nodes.add_argument("--artifact-output", help="Optional extraction artifact output path")
    suggest_document_nodes.add_argument("--artifact-format", choices=["json", "markdown"], default="json")
    suggest_document_nodes.add_argument("--max-chars", type=int, default=12000, help="Maximum characters to analyze from the extracted payload")
    suggest_document_nodes.add_argument("--max-preview-rows", type=int, default=12, help="Maximum preview rows per worksheet for XLSX fallback output")
    suggest_document_nodes.add_argument("--max-preview-cols", type=int, default=8, help="Maximum preview columns per worksheet for XLSX fallback output")
    suggest_document_nodes.add_argument("--limit", type=int, default=8, help="Maximum number of suggestions to return")
    suggest_document_nodes.add_argument("--include-existing", action="store_true", help="Include terms that already have canonical pages")
    suggest_document_nodes.add_argument("--format", choices=["text", "json"], default="text")

    apply_document_nodes = subparsers.add_parser(
        "apply-document-canonical-nodes",
        help="Apply selected source-based canonical proposals as promote/link operations",
    )
    apply_document_nodes.add_argument("--input", required=True, help="Source path or URL")
    apply_document_nodes.add_argument("--theme", help="Theme readme ref, e.g. themes/general/02-x/README")
    apply_document_nodes.add_argument("--page", action="append", default=[], help="Theme page ref to use for follow-up commands. Repeatable.")
    apply_document_nodes.add_argument("--artifact-output", help="Optional extraction artifact output path")
    apply_document_nodes.add_argument("--artifact-format", choices=["json", "markdown"], default="json")
    apply_document_nodes.add_argument("--max-chars", type=int, default=12000, help="Maximum characters to analyze from the extracted payload")
    apply_document_nodes.add_argument("--max-preview-rows", type=int, default=12, help="Maximum preview rows per worksheet for XLSX fallback output")
    apply_document_nodes.add_argument("--max-preview-cols", type=int, default=8, help="Maximum preview columns per worksheet for XLSX fallback output")
    apply_document_nodes.add_argument("--limit", type=int, default=8, help="Maximum number of suggestions to consider before applying filters")
    apply_document_nodes.add_argument("--include-existing", action="store_true", help="Include terms that already have canonical pages")
    apply_document_nodes.add_argument("--title", action="append", default=[], help="Exact suggestion title to apply. Repeatable.")
    apply_document_nodes.add_argument("--all", action="store_true", help="Apply all returned suggestions after filtering")
    apply_document_nodes.add_argument("--dry-run", action="store_true", help="Preview planned promote/link operations without modifying files")
    apply_document_nodes.add_argument("--format", choices=["text", "json"], default="text")

    write_document_proposal = subparsers.add_parser(
        "write-document-proposal-file",
        help="Write a persistent document proposal file for later review and execution",
    )
    write_document_proposal.add_argument("--input", required=True, help="Source path or URL")
    write_document_proposal.add_argument("--output", required=True, help="Proposal JSON output path")
    write_document_proposal.add_argument("--theme", help="Theme readme ref, e.g. themes/general/02-x/README")
    write_document_proposal.add_argument("--page", action="append", default=[], help="Theme page ref to use for follow-up commands. Repeatable.")
    write_document_proposal.add_argument("--artifact-output", help="Optional extraction artifact output path")
    write_document_proposal.add_argument("--artifact-format", choices=["json", "markdown"], default="json")
    write_document_proposal.add_argument("--max-chars", type=int, default=12000, help="Maximum characters to analyze from the extracted payload")
    write_document_proposal.add_argument("--max-preview-rows", type=int, default=12, help="Maximum preview rows per worksheet for XLSX fallback output")
    write_document_proposal.add_argument("--max-preview-cols", type=int, default=8, help="Maximum preview columns per worksheet for XLSX fallback output")
    write_document_proposal.add_argument("--limit", type=int, default=8, help="Maximum number of suggestions to persist")
    write_document_proposal.add_argument("--include-existing", action="store_true", help="Include terms that already have canonical pages")
    write_document_proposal.add_argument("--format", choices=["text", "json"], default="text")

    approve_document_proposal = subparsers.add_parser(
        "approve-document-proposal-file",
        help="Mark proposal suggestions as approved, rejected, or pending",
    )
    approve_document_proposal.add_argument("--proposal", required=True, help="Proposal JSON file path")
    approve_document_proposal.add_argument("--title", action="append", required=True, help="Exact suggestion title to update. Repeatable.")
    approve_document_proposal.add_argument("--status", required=True, choices=["approved", "rejected", "pending"], help="Review status to apply")
    approve_document_proposal.add_argument("--note", default="", help="Optional review note written to the selected suggestions")
    approve_document_proposal.add_argument("--format", choices=["text", "json"], default="text")

    apply_document_proposal = subparsers.add_parser(
        "apply-document-proposal-file",
        help="Apply approved entries from a persistent document proposal file",
    )
    apply_document_proposal.add_argument("--proposal", required=True, help="Proposal JSON file path")
    apply_document_proposal.add_argument("--title", action="append", default=[], help="Optional exact approved title to apply. Repeatable.")
    apply_document_proposal.add_argument("--all-approved", action="store_true", help="Apply all approved suggestions in the proposal file")
    apply_document_proposal.add_argument("--dry-run", action="store_true", help="Preview planned promote/link operations without modifying files")
    apply_document_proposal.add_argument("--format", choices=["text", "json"], default="text")

    return parser.parse_args()


def maybe_write_artifact(
    *,
    source_input: str,
    output_arg: str | None,
    artifact_format: str,
    max_chars: int,
    max_rows: int,
    max_cols: int,
) -> Path | None:
    artifact_output_path = Path(output_arg) if output_arg else None
    if artifact_output_path is None:
        return None
    if not artifact_output_path.is_absolute():
        artifact_output_path = Path.cwd() / artifact_output_path
    artifact_output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_output_path.write_text(
        render_payload_content(
            extract_document(source_input, max_chars, max_rows, max_cols),
            artifact_format,
        ),
        encoding="utf-8",
    )
    return artifact_output_path


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    try:
        if args.command in {"promote-entity", "promote-concept"}:
            node_type = "entity" if args.command == "promote-entity" else "concept"
            payload = upsert_canonical_page(
                root,
                node_type=node_type,
                title=args.title,
                slug=args.slug,
                aliases=args.alias,
                tags=args.tag,
                status=args.status,
                theme_refs=args.theme,
                page_refs=args.source_page + args.link_page,
                evidence_from=args.evidence_from,
                related_entities=args.related_entity,
                related_concepts=args.related_concept,
                related_patterns=args.related_pattern,
                related_methods=args.related_method,
            )
            linked_pages: list[dict[str, Any]] = []
            for page_ref in unique_preserve_order(args.link_page):
                linked_pages.append(link_canonical_page(root, page_ref=page_ref, canonical_ref=payload["canonical_ref"], label=args.title))
            payload["linked_pages"] = linked_pages
            append_recent_update(root, f"提升 `{args.title}` 为 `{payload['canonical_ref']}`，并同步更新实体关系。")
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                action = "Created" if payload["created"] else "Updated"
                print(f"{action} canonical {node_type} at {payload['canonical_path']}")
                print("Themes:")
                for item in payload["themes"]:
                    print(f"- {item}")
                print("Source pages:")
                for item in payload["source_pages"]:
                    print(f"- {item}")
                if linked_pages:
                    print("Linked pages:")
                    for item in linked_pages:
                        print(f"- {item['page']}")
            log_ingest_operation(
                root,
                args.command,
                f"提升 `{args.title}` 为 canonical {node_type} 节点。",
                details=[
                    f"canonical_ref={payload['canonical_ref']}",
                    f"themes={', '.join(payload['themes']) or 'none'}",
                    f"source_pages={', '.join(payload['source_pages']) or 'none'}",
                    f"linked_pages={len(linked_pages)}",
                ],
            )
            return 0

        if args.command == "link-canonical":
            payload = link_canonical_page(root, page_ref=args.page, canonical_ref=args.canonical, label=args.label)
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Linked {payload['page']} -> {payload['canonical_ref']}")
            log_ingest_operation(
                root,
                "link-canonical",
                f"把 `{payload['page']}` 链接到 `{payload['canonical_ref']}`。",
                details=[f"theme_readme={payload['theme_readme'] or 'none'}"],
            )
            return 0

        if args.command == "suggest-canonical-nodes":
            payload = suggest_canonical_nodes(
                root,
                theme_ref=args.theme,
                page_refs=args.page,
                limit=args.limit,
                include_existing=args.include_existing,
            )
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print("Suggested canonical nodes:")
                for item in payload["suggestions"]:
                    print(f"- {item['title']} [{item['suggested_node_type']}] action={item['recommended_action']}")
                    print(f"  - pages={', '.join(item['pages'])}")
                    if item["existing_canonical_ref"]:
                        print(f"  - existing={item['existing_canonical_ref']}")
                    print(f"  - command={item['command']}")
            log_ingest_operation(
                root,
                "suggest-canonical-nodes",
                f"为 {len(payload['pages_scanned'])} 个页面生成 canonical node 候选建议。",
                details=[f"suggestions={len(payload['suggestions'])}", f"theme={payload['theme'] or 'none'}"],
            )
            return 0

        if args.command == "batch-link-canonical":
            payload = batch_link_canonical_pages(root, page_refs=args.page, canonical_refs=args.canonical)
            append_recent_update(root, f"批量补充 {payload['link_count']} 条 canonical page 关联链接。")
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Linked {payload['link_count']} page/canonical pairs")
            log_ingest_operation(
                root,
                "batch-link-canonical",
                f"批量链接 {payload['link_count']} 对 page/canonical 关系。",
                details=[f"pages={len(payload['pages'])}", f"canonicals={len(payload['canonicals'])}"],
            )
            return 0

        if args.command == "sync-theme-graph":
            payload = sync_theme_graph(root, theme_readme_ref=args.theme, page_refs=args.page)
            append_recent_update(root, f"同步 `{payload['theme_readme']}` 的 theme graph，并刷新 canonical 反向关系。")
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Synced theme graph for {payload['theme_readme']}")
                for canonical_ref in payload["canonical_refs"]:
                    print(f"- {canonical_ref}")
            log_ingest_operation(
                root,
                "sync-theme-graph",
                f"同步主题图谱 `{payload['theme_readme']}`。",
                details=[f"pages={len(payload['pages_scanned'])}", f"canonicals={len(payload['canonical_refs'])}", f"links={payload['link_count']}"],
            )
            return 0

        if args.command == "suggest-document-canonical-nodes":
            source_input = args.input
            source_label = resolve_ingest_source(source_input).display_name
            payload = suggest_document_canonical_nodes(
                root,
                source_path=source_input,
                theme_ref=args.theme,
                page_refs=args.page,
                limit=args.limit,
                include_existing=args.include_existing,
                max_chars=args.max_chars,
                max_rows=args.max_preview_rows,
                max_cols=args.max_preview_cols,
            )
            artifact_output_path = maybe_write_artifact(
                source_input=source_input,
                output_arg=args.artifact_output,
                artifact_format=args.artifact_format,
                max_chars=args.max_chars,
                max_rows=args.max_preview_rows,
                max_cols=args.max_preview_cols,
            )
            if artifact_output_path is not None:
                payload["artifact_output"] = str(artifact_output_path)
                payload["artifact_format"] = args.artifact_format
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print_document_suggestions_text(payload)
                if artifact_output_path is not None:
                    print(f"Artifact written to {artifact_output_path}")
            log_ingest_operation(
                root,
                "suggest-document-canonical-nodes",
                f"基于文档 `{source_label}` 生成 canonical node 候选建议。",
                details=[
                    f"theme={payload['theme'] or 'none'}",
                    f"primary_page={payload['primary_page'] or 'none'}",
                    f"suggestions={len(payload['suggestions'])}",
                    f"artifact={artifact_output_path if artifact_output_path is not None else 'none'}",
                ],
            )
            return 0

        if args.command == "apply-document-canonical-nodes":
            source_input = args.input
            source_label = resolve_ingest_source(source_input).display_name
            payload = apply_document_canonical_nodes(
                root,
                source_path=source_input,
                theme_ref=args.theme,
                page_refs=args.page,
                selected_titles=args.title,
                apply_all=args.all,
                dry_run=args.dry_run,
                limit=args.limit,
                include_existing=args.include_existing,
                max_chars=args.max_chars,
                max_rows=args.max_preview_rows,
                max_cols=args.max_preview_cols,
            )
            artifact_output_path = maybe_write_artifact(
                source_input=source_input,
                output_arg=args.artifact_output,
                artifact_format=args.artifact_format,
                max_chars=args.max_chars,
                max_rows=args.max_preview_rows,
                max_cols=args.max_preview_cols,
            )
            if artifact_output_path is not None:
                payload["artifact_output"] = str(artifact_output_path)
                payload["artifact_format"] = args.artifact_format
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print_document_apply_text(payload)
                if artifact_output_path is not None:
                    print(f"Artifact written to {artifact_output_path}")
            log_ingest_operation(
                root,
                "apply-document-canonical-nodes",
                f"基于文档 `{source_label}` 应用 document canonical proposal。",
                details=[
                    f"dry_run={payload['dry_run']}",
                    f"selected={len(payload['selected_titles'])}",
                    f"applied={payload['applied_count']}",
                    f"missing={len(payload['missing_titles'])}",
                    f"theme={payload['theme'] or 'none'}",
                ],
            )
            return 0

        if args.command == "write-document-proposal-file":
            source_input = args.input
            source_label = resolve_ingest_source(source_input).display_name
            output_path = Path(args.output)
            if not output_path.is_absolute():
                output_path = Path.cwd() / output_path
            payload = build_document_proposal_file_payload(
                root,
                source_path=source_input,
                theme_ref=args.theme,
                page_refs=args.page,
                limit=args.limit,
                include_existing=args.include_existing,
                max_chars=args.max_chars,
                max_rows=args.max_preview_rows,
                max_cols=args.max_preview_cols,
            )
            write_json_payload(output_path, payload)
            artifact_output_path = maybe_write_artifact(
                source_input=source_input,
                output_arg=args.artifact_output,
                artifact_format=args.artifact_format,
                max_chars=args.max_chars,
                max_rows=args.max_preview_rows,
                max_cols=args.max_preview_cols,
            )
            if artifact_output_path is not None:
                payload["artifact_output"] = str(artifact_output_path)
                payload["artifact_format"] = args.artifact_format
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print_document_proposal_file_text(payload)
                print(f"Proposal written to {output_path}")
                if artifact_output_path is not None:
                    print(f"Artifact written to {artifact_output_path}")
            log_ingest_operation(
                root,
                "write-document-proposal-file",
                f"为文档 `{source_label}` 写出持久化 proposal 文件。",
                details=[
                    f"proposal={output_path}",
                    f"suggestions={len(payload['suggestions'])}",
                    f"theme={payload['theme'] or 'none'}",
                ],
            )
            return 0

        if args.command == "approve-document-proposal-file":
            proposal_path = Path(args.proposal)
            if not proposal_path.is_absolute():
                proposal_path = Path.cwd() / proposal_path
            proposal_payload = load_json_payload(proposal_path)
            review_payload = update_document_proposal_reviews(
                proposal_payload,
                titles=args.title,
                status=args.status,
                note=args.note,
            )
            write_json_payload(proposal_path, proposal_payload)
            result_payload = {"proposal_path": str(proposal_path), **review_payload}
            if args.format == "json":
                print(json.dumps(result_payload, ensure_ascii=False, indent=2))
            else:
                print_document_proposal_review_text(result_payload)
            log_ingest_operation(
                root,
                "approve-document-proposal-file",
                f"更新 proposal 文件 `{proposal_path.name}` 的审批状态。",
                details=[
                    f"status={args.status}",
                    f"updated={len(review_payload['updated_titles'])}",
                    f"missing={len(review_payload['missing_titles'])}",
                ],
            )
            return 0

        if args.command == "apply-document-proposal-file":
            proposal_path = Path(args.proposal)
            if not proposal_path.is_absolute():
                proposal_path = Path.cwd() / proposal_path
            payload = apply_document_proposal_file(
                root,
                proposal_path=proposal_path,
                selected_titles=args.title,
                apply_all_approved=args.all_approved,
                dry_run=args.dry_run,
            )
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print_document_apply_text(payload)
                print(f"Proposal file: {proposal_path}")
            log_ingest_operation(
                root,
                "apply-document-proposal-file",
                f"根据 proposal 文件 `{proposal_path.name}` 执行 canonical proposal。",
                details=[
                    f"dry_run={payload['dry_run']}",
                    f"selected={len(payload['selected_titles'])}",
                    f"applied={payload['applied_count']}",
                    f"missing={len(payload['missing_titles'])}",
                ],
            )
            return 0
    except Exception as exc:
        log_ingest_operation(root, args.command, f"命令执行失败：{exc}", status="failed")
        raise

    return 1
