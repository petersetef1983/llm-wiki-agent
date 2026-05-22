from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from src.core.inbox import INBOX_STAGING_DIRS


def load_reset_helper():
    module_path = Path(__file__).resolve().parents[1] / "src" / "assets" / "skills" / "reset" / "scripts" / "kb_reset.py"
    spec = importlib.util.spec_from_file_location("test_kb_reset", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load reset helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ResetInboxDirTests(unittest.TestCase):
    def test_reset_inbox_recreates_flat_staging_dirs(self) -> None:
        helper = load_reset_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            legacy = root / "inbox" / "media" / "images" / "old.png"
            legacy.parent.mkdir(parents=True)
            legacy.write_bytes(b"\x89PNG\r\n")

            actions: list[str] = []
            helper.reset_inbox(root, dry_run=False, actions=actions)

            for rel in INBOX_STAGING_DIRS:
                self.assertTrue((root / rel).is_dir(), rel.as_posix())
            self.assertFalse((root / "inbox" / "media").exists())


if __name__ == "__main__":
    unittest.main()
