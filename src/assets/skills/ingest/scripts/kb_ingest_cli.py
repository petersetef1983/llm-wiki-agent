#!/usr/bin/env python3
"""Deterministic CLI for ingest workflow helpers."""

from __future__ import annotations

from kb_ingest_core import *
from kb_ingest_documents import *
from kb_ingest_git import *


def parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS, help="Knowledge base root directory")

    parser = argparse.ArgumentParser(
        description=(
            "Deterministic helpers for ingest workflows. "
            "Semantic wiki maintenance belongs to the LLM, not this CLI."
        )
    )
    parser.add_argument("--root", default=".", help="Knowledge base root directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory", parents=[common], help="Summarize themes and inbox files")
    inventory.add_argument("--format", choices=["text", "json"], default="text")

    scan_reuse_cmd = subparsers.add_parser(
        "scan-reuse",
        parents=[common],
        help="Read-only scan of shared assets, reuse candidates, and asset-match briefs",
    )
    scan_reuse_cmd.add_argument("--format", choices=["text", "json"], default="json")

    append_update = subparsers.add_parser("append-update", parents=[common], help="Append a note to recent-updates.md")
    append_update.add_argument("--message", required=True, help="Update message to append")

    suggest_theme = subparsers.add_parser("suggest-theme-dir", parents=[common], help="Suggest the next theme directory name for a category")
    suggest_theme.add_argument("--category", required=True, choices=THEME_CATEGORIES, help="Theme category")
    suggest_theme.add_argument("--title", required=True, help="Human-readable topic title")
    suggest_theme.add_argument("--format", choices=["text", "json"], default="text")

    create_theme = subparsers.add_parser(
        "create-theme",
        parents=[common],
        help="Create a new theme scaffold after the LLM has decided a new container is necessary",
    )
    create_theme.add_argument("--category", required=True, choices=THEME_CATEGORIES, help="Theme category")
    create_theme.add_argument("--title", required=True, help="Human-readable topic title")
    create_theme.add_argument("--owner", action="append", default=[], help="Theme owner. Repeat to add multiple owners.")
    create_theme.add_argument("--tags", nargs="*", default=[], help="Additional tags for the theme frontmatter")
    create_theme.add_argument("--status", default="active", help="Theme status, for example active/planning/paused/archived")
    create_theme.add_argument("--format", choices=["text", "json"], default="text")

    extract_document_cmd = subparsers.add_parser("extract-document", parents=[common], help="Convert a source file or URL into a markdown evidence artifact")
    extract_document_cmd.add_argument("--input", required=True, help="Source path or URL")
    extract_document_cmd.add_argument("--output", help="Optional output file path")
    extract_document_cmd.add_argument("--format", choices=["json", "markdown"], default="json")
    extract_document_cmd.add_argument("--max-chars", type=int, default=12000, help="Maximum characters to emit in the main text payload")
    extract_document_cmd.add_argument("--max-preview-rows", type=int, default=12, help="Maximum preview rows per worksheet for XLSX fallback output")
    extract_document_cmd.add_argument("--max-preview-cols", type=int, default=8, help="Maximum preview columns per worksheet for XLSX fallback output")

    extract_git_cmd = subparsers.add_parser("extract-git-repo", parents=[common], help="Temporarily clone a Git repository and emit a repo evidence artifact")
    extract_git_cmd.add_argument("--url", required=True, help="Git URL or local path accepted by `git clone`")
    extract_git_cmd.add_argument("--output", help="Evidence artifact output path")
    extract_git_cmd.add_argument("--source-anchor", help="Optional source anchor path that records URL/ref/commit without source code")
    extract_git_cmd.add_argument("--ref", help="Optional branch, tag, or commit to checkout")
    extract_git_cmd.add_argument("--format", choices=["json", "markdown"], default="json")
    extract_git_cmd.add_argument("--max-files", type=int, default=2000, help="Maximum repo inventory files to record")
    extract_git_cmd.add_argument("--max-excerpt-files", type=int, default=80, help="Maximum selected files to excerpt for LLM analysis")
    extract_git_cmd.add_argument("--max-file-chars", type=int, default=16000, help="Maximum characters per excerpted file")
    extract_git_cmd.add_argument("--include-globs", action="append", default=[], help="Glob for files eligible for excerpts. Repeatable.")
    extract_git_cmd.add_argument("--exclude-globs", action="append", default=[], help="Additional glob to exclude from inventory/excerpts. Repeatable.")
    extract_git_cmd.add_argument("--keep-temp", action="store_true", help="Keep the temporary clone for manual analysis instead of deleting it")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    try:
        if args.command == "inventory":
            themes = collect_theme_summaries(root)
            inbox_files = collect_inbox_files(root)
            recent_updates = read_recent_updates(root)
            payload = {
                "root": str(root),
                "themes": [asdict(theme) for theme in themes],
                "next_theme_numbers": {category: next_theme_number(root, category) for category in THEME_CATEGORIES},
                "inbox": inbox_files,
                "recent_updates": recent_updates,
            }
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print_inventory_text(root, themes, inbox_files, recent_updates)
            log_ingest_operation(
                root,
                "inventory",
                f"生成知识库结构快照，识别到 {len(themes)} 个主题。",
                details=[f"inbox_buckets={len(inbox_files)}"],
            )
            return 0

        if args.command == "append-update":
            append_recent_update(root, args.message)
            print(f"Appended update to {root / 'index' / 'recent-updates.md'}")
            log_ingest_operation(root, "append-update", "追加一条 recent update 记录。", details=[f"message={args.message}"])
            return 0

        if args.command == "scan-reuse":
            payload = scan_reuse(root)
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Reuse scan: {root}")
                print(f"- shared_assets: {len(payload['shared_assets'])}")
                print(f"- reuse_candidate_files: {len(payload['reuse_candidate_files'])}")
                print(f"- target_match_briefs: {len(payload['target_match_briefs'])}")
                print(f"- missing_match_briefs: {len(payload['missing_match_briefs'])}")
                print(f"- unpromoted_candidates: {len(payload['unpromoted_candidates'])}")
                print(f"- unmatched_assets: {len(payload['unmatched_assets'])}")
                print(f"- broken_asset_refs: {len(payload['broken_asset_refs'])}")
            log_ingest_operation(
                root,
                "scan-reuse",
                "扫描跨项目复用链路，生成只读资产匹配线索。",
                details=[
                    f"shared_assets={len(payload['shared_assets'])}",
                    f"unpromoted_candidates={len(payload['unpromoted_candidates'])}",
                    f"broken_asset_refs={len(payload['broken_asset_refs'])}",
                ],
            )
            return 0

        if args.command == "suggest-theme-dir":
            payload = {
                "category": args.category,
                "title": args.title,
                "next_number": next_theme_number(root, args.category),
                "directory_name": build_theme_dir_name(root, args.category, args.title),
                "relative_path": f"themes/{args.category}/{build_theme_dir_name(root, args.category, args.title)}",
            }
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(payload["relative_path"])
            log_ingest_operation(
                root,
                "suggest-theme-dir",
                f"为 `{args.title}` 生成候选主题目录名。",
                details=[f"category={args.category}", f"path={payload['relative_path']}"],
            )
            return 0

        if args.command == "create-theme":
            payload = create_theme(root, args.category, args.title, args.owner, args.tags, args.status)
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"Created theme scaffold at {payload['relative_path']}")
                print("Created files:")
                for file_path in payload["created_files"]:
                    print(f"- {file_path}")
                print("Updated indexes:")
                for file_path in payload["updated_indexes"]:
                    print(f"- {file_path}")
            log_ingest_operation(
                root,
                "create-theme",
                f"创建主题 `{payload['theme_name']}` 并初始化脚手架。",
                details=[
                    f"category={payload['category']}",
                    f"status={payload['status']}",
                    f"owners={', '.join(payload['owners'])}",
                    f"tags={', '.join(payload['tags'])}",
                    f"path={payload['relative_path']}",
                ],
            )
            return 0

        if args.command == "extract-document":
            source_input = args.input
            payload = extract_document(source_input, args.max_chars, args.max_preview_rows, args.max_preview_cols)
            output_path = Path(args.output) if args.output else None
            if output_path is not None and not output_path.is_absolute():
                output_path = Path.cwd() / output_path
            emit_payload(payload, output_path, args.format)
            log_ingest_operation(
                root,
                "extract-document",
                f"抽取文档 `{payload['file_name']}`。",
                details=[
                    f"type={payload['file_type']}",
                    f"parser={payload['parser']}",
                    f"confidence={payload['confidence']}",
                    f"output={output_path if output_path is not None else 'stdout'}",
                ],
            )
            return 0

        if args.command == "extract-git-repo":
            output_path = Path(args.output) if args.output else None
            if output_path is not None and not output_path.is_absolute():
                output_path = Path.cwd() / output_path
            source_anchor_path = Path(args.source_anchor) if args.source_anchor else None
            if source_anchor_path is not None and not source_anchor_path.is_absolute():
                source_anchor_path = Path.cwd() / source_anchor_path
            payload = extract_git_repo(
                url=args.url,
                ref=args.ref,
                output_path=output_path,
                source_anchor_path=source_anchor_path,
                output_format=args.format,
                max_files=args.max_files,
                max_excerpt_files=args.max_excerpt_files,
                max_file_chars=args.max_file_chars,
                include_globs=args.include_globs,
                exclude_globs=args.exclude_globs,
                keep_temp=args.keep_temp,
            )
            if output_path is None:
                if args.format == "json":
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(render_git_markdown(payload))
            log_ingest_operation(
                root,
                "extract-git-repo",
                f"抽取 Git 仓库 `{payload['repo']['url']}` 的结构证据。",
                details=[
                    f"commit={payload['repo']['resolved_commit']}",
                    f"files={payload['inventory']['file_count']}",
                    f"output={output_path if output_path is not None else 'stdout'}",
                    f"source_anchor={source_anchor_path if source_anchor_path is not None else 'none'}",
                    f"keep_temp={args.keep_temp}",
                ],
            )
            return 0
    except Exception as exc:
        log_ingest_operation(root, args.command, f"命令执行失败：{exc}", status="failed")
        raise

    return 1
