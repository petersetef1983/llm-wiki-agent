from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


def load_ingest_core():
    module_path = Path(__file__).resolve().parents[1] / "src" / "assets" / "skills" / "ingest" / "scripts" / "kb_ingest_core.py"
    spec = importlib.util.spec_from_file_location("test_kb_ingest_core", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load ingest core")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class InboxClassificationTests(unittest.TestCase):
    def test_mixed_inbox_routes_requirements_and_review(self) -> None:
        core = load_ingest_core()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            requirement = root / "inbox" / "requirements" / "crm-prd.md"
            requirement.parent.mkdir(parents=True)
            requirement.write_text(
                "# CRM PRD\n\n## 功能需求\n\n- 用户可以导入客户线索。\n\n## 验收标准\n\n- 导入成功率可验证。\n",
                encoding="utf-8",
            )
            paper = root / "inbox" / "papers" / "retrieval-paper.md"
            paper.parent.mkdir(parents=True)
            paper.write_text("# Retrieval Paper\n\nAbstract\n\nMethods\n\nReferences\n", encoding="utf-8")
            article = root / "inbox" / "articles" / "blog-note.md"
            article.parent.mkdir(parents=True)
            article.write_text("# Blog\n\nThis article explains an implementation pattern.\n", encoding="utf-8")
            image = root / "inbox" / "images" / "diagram.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"\x89PNG\r\n")
            video = root / "inbox" / "videos" / "demo.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            audio = root / "inbox" / "audio" / "interview.mp3"
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b"ID3")
            legacy_image = root / "inbox" / "media" / "images" / "legacy-diagram.png"
            legacy_image.parent.mkdir(parents=True)
            legacy_image.write_bytes(b"\x89PNG\r\n")
            source = root / "inbox" / "source-code" / "app.py"
            source.parent.mkdir(parents=True)
            source.write_text("def main():\n    pass\n", encoding="utf-8")
            unknown = root / "inbox" / "to-be-filed" / "misc.bin"
            unknown.parent.mkdir(parents=True)
            unknown.write_bytes(b"\x00\x01")

            payload = core.classify_inbox(root)
            by_path = {item["path"]: item for item in payload["items"]}

            self.assertEqual(by_path["inbox/requirements/crm-prd.md"]["content_kind"], "requirement")
            self.assertEqual(by_path["inbox/requirements/crm-prd.md"]["suggested_action"], "ingest_requirement")
            self.assertEqual(by_path["inbox/papers/retrieval-paper.md"]["content_kind"], "paper")
            self.assertEqual(by_path["inbox/articles/blog-note.md"]["content_kind"], "article")
            self.assertEqual(by_path["inbox/images/diagram.png"]["content_kind"], "image")
            self.assertEqual(by_path["inbox/videos/demo.mp4"]["content_kind"], "video")
            self.assertEqual(by_path["inbox/audio/interview.mp3"]["source_type"], "audio")
            self.assertEqual(by_path["inbox/audio/interview.mp3"]["suggested_action"], "extract_media_then_ingest")
            self.assertEqual(by_path["inbox/media/images/legacy-diagram.png"]["content_kind"], "image")
            self.assertEqual(by_path["inbox/source-code/app.py"]["content_kind"], "source-code")
            self.assertEqual(by_path["inbox/to-be-filed/misc.bin"]["suggested_action"], "review")
            self.assertIn("inbox/requirements/crm-prd.md", payload["high_confidence_requirements"])


if __name__ == "__main__":
    unittest.main()
