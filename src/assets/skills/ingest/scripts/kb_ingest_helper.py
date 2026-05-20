#!/usr/bin/env python3
"""Default entrypoint for deterministic ingest workflow helpers."""

from __future__ import annotations

from kb_ingest_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
