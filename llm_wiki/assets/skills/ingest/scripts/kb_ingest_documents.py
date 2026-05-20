#!/usr/bin/env python3
"""Deterministic source extraction helpers for ingest workflows."""

from __future__ import annotations

from kb_ingest_core import *

import shutil
import subprocess
import tempfile
import warnings as runtime_warnings
from urllib.parse import parse_qs, unquote, urlencode, urlparse


AUDIO_EXTENSIONS = {"aac", "flac", "m4a", "mp3", "ogg", "wav", "wma"}
VIDEO_EXTENSIONS = {"avi", "m4v", "mkv", "mov", "mp4", "mpeg", "mpg", "webm"}
URL_SCHEMES = {"http", "https", "file", "data"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}

runtime_warnings.filterwarnings(
    "ignore",
    message="Couldn't find ffmpeg or avconv - defaulting to ffmpeg, but may not work",
    category=RuntimeWarning,
)


def safe_import(module_name: str) -> Any | None:
    try:
        return import_module(module_name)
    except Exception:
        return None


@dataclass
class IngestSource:
    locator: str
    display_name: str
    file_type: str
    source_kind: str
    is_url: bool
    local_path: Path | None
    size_bytes: int | None


def is_url_source(source: str) -> bool:
    parsed = urlparse(source)
    return parsed.scheme.lower() in URL_SCHEMES


def is_youtube_url(source: str) -> bool:
    if not is_url_source(source):
        return False
    host = urlparse(source).netloc.lower().split(":", 1)[0]
    return host in YOUTUBE_HOSTS


def detect_file_type(source: Path | str) -> str:
    if isinstance(source, Path):
        return source.suffix.lower().lstrip(".")

    raw_source = str(source)
    if is_youtube_url(raw_source):
        return "youtube"
    if is_url_source(raw_source):
        path_part = unquote(urlparse(raw_source).path)
        suffix = Path(path_part).suffix.lower().lstrip(".")
        return suffix or "url"
    return Path(raw_source).suffix.lower().lstrip(".")


def source_display_name(source: str) -> str:
    if not is_url_source(source):
        return Path(source).name or str(source)

    parsed = urlparse(source)
    if is_youtube_url(source):
        query = parse_qs(parsed.query)
        video_id = query.get("v", [None])[0]
        if not video_id and parsed.netloc.lower().split(":", 1)[0] == "youtu.be":
            video_id = parsed.path.strip("/") or None
        return f"youtube-{video_id}" if video_id else source

    path_name = Path(unquote(parsed.path)).name
    return path_name or source


def normalize_source_locator(source: str) -> str:
    if not is_youtube_url(source):
        return source

    parsed = urlparse(source)
    host = parsed.netloc.lower().split(":", 1)[0]
    query = parse_qs(parsed.query)
    video_id = query.get("v", [None])[0]
    if not video_id and host == "youtu.be":
        video_id = parsed.path.strip("/") or None
    if not video_id:
        return source

    normalized_query: dict[str, str] = {"v": video_id}
    for key in ("t", "start", "list"):
        value = query.get(key, [None])[0]
        if value:
            normalized_query[key] = value
    return f"https://www.youtube.com/watch?{urlencode(normalized_query)}"


def resolve_ingest_source(source: Path | str) -> IngestSource:
    raw_source = str(source)
    if is_url_source(raw_source):
        normalized_locator = normalize_source_locator(raw_source)
        file_type = detect_file_type(normalized_locator)
        if is_youtube_url(normalized_locator):
            source_kind = "youtube"
        elif file_type in AUDIO_EXTENSIONS:
            source_kind = "audio"
        elif file_type in VIDEO_EXTENSIONS:
            source_kind = "video"
        else:
            source_kind = "url"
        return IngestSource(
            locator=normalized_locator,
            display_name=source_display_name(normalized_locator),
            file_type=file_type,
            source_kind=source_kind,
            is_url=True,
            local_path=None,
            size_bytes=None,
        )

    local_path = Path(raw_source).expanduser().resolve()
    file_type = detect_file_type(local_path)
    if file_type in VIDEO_EXTENSIONS:
        source_kind = "video"
    elif file_type in AUDIO_EXTENSIONS:
        source_kind = "audio"
    else:
        source_kind = "document"
    return IngestSource(
        locator=str(local_path),
        display_name=local_path.name,
        file_type=file_type,
        source_kind=source_kind,
        is_url=False,
        local_path=local_path,
        size_bytes=local_path.stat().st_size,
    )


def normalize_markdown_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()


def looks_like_youtube_shell(markdown: str) -> bool:
    lowered = markdown.lower()
    shell_signals = [
        "youtube.com/about",
        "youtube.com/ads",
        "developers.google.com/youtube",
        "/t/privacy",
        "/t/terms",
        "howyoutubeworks",
    ]
    return sum(signal in lowered for signal in shell_signals) >= 2


def extract_youtube_video_id(source: str) -> str | None:
    if not is_youtube_url(source):
        return None

    parsed = urlparse(source)
    host = parsed.netloc.lower().split(":", 1)[0]
    query = parse_qs(parsed.query)
    if host == "youtu.be":
        return parsed.path.strip("/") or None
    return query.get("v", [None])[0]


def format_timestamp(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def render_youtube_transcript_markdown(
    *,
    title: str | None,
    video_url: str,
    transcript: Any,
) -> str:
    lines = ["# YouTube Transcript", ""]
    if title:
        lines.extend([f"## {title}", ""])
    lines.extend([f"- source: {video_url}", f"- language: {getattr(transcript, 'language', 'unknown')}"])

    language_code = getattr(transcript, "language_code", None)
    if language_code:
        lines.append(f"- language_code: {language_code}")
    is_generated = getattr(transcript, "is_generated", None)
    if is_generated is not None:
        lines.append(f"- is_generated: {is_generated}")

    lines.extend(["", "## Transcript", ""])
    for snippet in transcript:
        text = normalize_text(getattr(snippet, "text", "") or "")
        if not text:
            continue
        start = float(getattr(snippet, "start", 0.0) or 0.0)
        lines.append(f"- [{format_timestamp(start)}] {text}")
    return "\n".join(lines).strip()


def fetch_youtube_transcript_fallback(source: IngestSource, metadata: dict[str, Any]) -> dict[str, Any] | None:
    video_id = extract_youtube_video_id(source.locator)
    if not video_id:
        return None

    module = safe_import("youtube_transcript_api")
    if module is None:
        return {
            "parser": "youtube_transcript_api_unavailable",
            "confidence": "low",
            "markdown": "",
            "metadata": {},
            "warnings": [
                "youtube-transcript-api is not installed, so YouTube transcript fallback is unavailable.",
            ],
            "sections": [],
        }

    api_factory = getattr(module, "YouTubeTranscriptApi", None)
    if api_factory is None:
        return None

    try:
        transcript = api_factory().fetch(
            video_id,
            languages=["zh-Hans", "zh-CN", "zh-TW", "en", "en-US", "en-GB"],
        )
    except Exception as exc:
        return {
            "parser": "youtube_transcript_api",
            "confidence": "low",
            "markdown": "",
            "metadata": {"video_id": video_id},
            "warnings": [f"YouTube transcript fallback failed: {exc}"],
            "sections": [],
        }

    rendered_markdown = render_youtube_transcript_markdown(
        title=metadata.get("title"),
        video_url=source.locator,
        transcript=transcript,
    )
    return {
        "parser": "youtube_transcript_api",
        "confidence": "high" if rendered_markdown else "low",
        "markdown": rendered_markdown,
        "metadata": {
            "video_id": video_id,
            "transcript_language": getattr(transcript, "language", None),
            "transcript_language_code": getattr(transcript, "language_code", None),
            "transcript_is_generated": getattr(transcript, "is_generated", None),
            "transcript_snippet_count": len(transcript),
        },
        "warnings": [],
        "sections": [],
    }


def summarize_metadata_value(value: Any) -> Any:
    if value in (None, "", [], {}, ()):
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            summarized = summarize_metadata_value(item)
            if summarized is not None:
                normalized[str(key)] = summarized
        return normalized or None

    if isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value if item not in (None, "")]
        return items if items else None

    return str(value)


def collect_markitdown_metadata(result: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}

    for attr in ("title", "author", "creator", "subject", "description", "language", "source_uri"):
        summarized = summarize_metadata_value(getattr(result, attr, None))
        if summarized is not None:
            metadata[attr] = summarized

    for attr in ("metadata", "document_metadata", "extra_metadata"):
        raw_metadata = getattr(result, attr, None)
        summarized = summarize_metadata_value(raw_metadata)
        if isinstance(summarized, dict):
            metadata.update(summarized)

    return metadata


def load_markitdown_converter() -> Any:
    module = safe_import("markitdown")
    if module is None:
        raise RuntimeError(
            "MarkItDown is required for source ingestion. Install it with `pip install 'markitdown[all]'`."
        )

    factory = getattr(module, "MarkItDown", None)
    if factory is None:
        raise RuntimeError("The installed `markitdown` package does not expose the `MarkItDown` class.")

    try:
        return factory(enable_plugins=False)
    except TypeError:
        return factory()


def convert_local_with_markitdown(converter: Any, path: Path) -> Any:
    convert_local = getattr(converter, "convert_local", None)
    if callable(convert_local):
        return convert_local(str(path))
    return converter.convert(str(path))


def convert_source_with_markitdown(converter: Any, source: IngestSource) -> Any:
    if source.is_url:
        return converter.convert(source.locator)
    if source.local_path is None:
        raise RuntimeError(f"Local source could not be resolved: {source.locator}")
    return convert_local_with_markitdown(converter, source.local_path)


def extract_video_audio_track(path: Path, temp_dir: str) -> Path:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError(
            "Video ingest requires `ffmpeg` on PATH so the audio track can be extracted before MarkItDown transcription."
        )

    audio_path = Path(temp_dir) / f"{path.stem}.wav"
    completed = subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        error_text = normalize_text(completed.stderr or completed.stdout or "")
        raise RuntimeError(f"ffmpeg failed to extract audio from `{path.name}`: {error_text or 'unknown error'}")
    return audio_path


def extract_with_markitdown(source: IngestSource) -> dict[str, Any]:
    converter = load_markitdown_converter()
    warnings: list[str] = []
    metadata: dict[str, Any] = {}

    try:
        if source.source_kind == "video" and not source.is_url:
            if source.local_path is None:
                raise RuntimeError(f"Local video source could not be resolved: {source.locator}")
            with tempfile.TemporaryDirectory(prefix="kb-ingest-video-") as temp_dir:
                audio_path = extract_video_audio_track(source.local_path, temp_dir)
                result = convert_local_with_markitdown(converter, audio_path)
                warnings.append("Video was converted by extracting its audio track and transcribing it with MarkItDown.")
                metadata["video_ingest_mode"] = "ffmpeg_audio_track_to_markdown"
        else:
            result = convert_source_with_markitdown(converter, source)
    except Exception as exc:
        raise RuntimeError(f"MarkItDown failed to convert `{source.display_name}`: {exc}") from exc

    markdown = normalize_markdown_text(getattr(result, "text_content", "") or "")
    metadata.update(collect_markitdown_metadata(result))
    metadata["source_kind"] = source.source_kind
    metadata["source_locator_kind"] = "url" if source.is_url else "local_path"
    metadata["markdown_char_count"] = len(markdown)

    if not markdown:
        warnings.append("MarkItDown returned no Markdown content.")
    elif source.source_kind == "youtube" and looks_like_youtube_shell(markdown):
        warnings.append(
            "MarkItDown returned a YouTube page shell instead of a transcript. Treat this extraction as low-confidence and verify transcript availability."
        )

    if source.source_kind == "youtube" and (not markdown or looks_like_youtube_shell(markdown)):
        fallback_result = fetch_youtube_transcript_fallback(source, metadata)
        if fallback_result is not None and fallback_result.get("markdown"):
            merged_metadata = {**metadata, **fallback_result.get("metadata", {})}
            merged_metadata["youtube_transcript_fallback_used"] = True
            return {
                "parser": fallback_result.get("parser", "youtube_transcript_api"),
                "confidence": fallback_result.get("confidence", "high"),
                "markdown": normalize_markdown_text(fallback_result.get("markdown", "")),
                "metadata": merged_metadata,
                "warnings": warnings + list(fallback_result.get("warnings", [])),
                "sections": fallback_result.get("sections", []),
            }
        if fallback_result is not None:
            metadata.update(fallback_result.get("metadata", {}))
            warnings.extend(fallback_result.get("warnings", []))
            metadata["youtube_transcript_fallback_used"] = True

    confidence = "high"
    if not markdown:
        confidence = "low"
    elif source.source_kind == "youtube" and looks_like_youtube_shell(markdown):
        confidence = "low"
    elif warnings or (source.source_kind == "video" and not source.is_url):
        confidence = "medium"

    return {
        "parser": "markitdown",
        "confidence": confidence,
        "markdown": markdown,
        "metadata": metadata,
        "warnings": warnings,
        "sections": [],
    }


def extract_document(source: Path | str, max_chars: int, max_rows: int, max_cols: int) -> dict[str, Any]:
    resolved_source = resolve_ingest_source(source)
    result = extract_with_markitdown(resolved_source)
    markdown = normalize_markdown_text(result.get("markdown", ""))
    markdown_truncated = len(markdown) > max_chars
    rendered_markdown = truncate_text(markdown, max_chars) if markdown else ""
    warnings = list(result.get("warnings", []))
    if markdown_truncated:
        warnings.append(f"Converted Markdown was truncated to {max_chars} characters for artifact output.")

    metadata = dict(result.get("metadata", {}))
    metadata["markdown_truncated"] = markdown_truncated
    metadata["preview_limits"] = {"max_chars": max_chars, "max_preview_rows": max_rows, "max_preview_cols": max_cols}

    excerpt_source = normalize_text(rendered_markdown) if rendered_markdown else PLACEHOLDER_TEXT
    return {
        "source_path": resolved_source.locator,
        "file_name": resolved_source.display_name,
        "file_type": resolved_source.file_type,
        "size_bytes": resolved_source.size_bytes,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "parser": result.get("parser", "unknown"),
        "confidence": result.get("confidence", "low"),
        "metadata": metadata,
        "warnings": warnings,
        "text": rendered_markdown,
        "markdown": rendered_markdown,
        "text_excerpt": truncate_text(excerpt_source, min(max_chars, 2500)),
        "sections": result.get("sections", []),
    }


def render_payload_content(payload: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return render_markdown(payload)


def render_markdown(payload: dict[str, Any]) -> str:
    converted_markdown = payload.get("markdown") or payload.get("text") or ""
    lines = [
        "# Document Extraction",
        "",
        "## Source",
        f"- file: `{payload['file_name']}`",
        f"- path: `{payload['source_path']}`",
        f"- type: `{payload['file_type']}`",
        f"- size_bytes: `{payload['size_bytes'] if payload['size_bytes'] is not None else 'unknown'}`",
        "",
        "## Extraction",
        f"- parser: `{payload['parser']}`",
        f"- confidence: `{payload['confidence']}`",
        f"- extracted_at: `{payload['extracted_at']}`",
        "",
        "## Metadata",
    ]

    metadata = payload.get("metadata", {})
    if metadata:
        for key, value in metadata.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")

    lines.extend(["", "## Warnings"])
    warnings = payload.get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")

    lines.extend(["", "## Converted Markdown", ""])
    if converted_markdown:
        lines.append(converted_markdown)
    else:
        lines.append(PLACEHOLDER_TEXT)

    sections = payload.get("sections", [])
    if sections:
        lines.extend(["", "## Structured Preview"])
        for section in sections:
            lines.append(f"- {section.get('sheet', 'section')}")
            for row in section.get("preview_rows", []):
                lines.append(f"  - {' | '.join(row)}")

    lines.extend(
        [
            "",
            "## Suggested Deep Ingest Use",
            "- Use this extracted text as evidence for updating `README.md`, `wiki/overview.md`, and topic pages.",
            "- Keep the original file under `sources/` unchanged.",
            "- If confidence is low, mark the wiki update as tentative and keep open questions.",
        ]
    )

    return "\n".join(lines) + "\n"
