#!/usr/bin/env python3
"""Tests for batch text-on-video OCR.

Run: .venv/bin/python -m unittest discover -s skill/scripts -p 'test_*.py' -v
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ocr_video_batch as batch  # noqa: E402


def make_tree(root: Path, item: str, *, videos: tuple[str, ...] = ("01.mp4",), source: str | None = None) -> Path:
    directory = root / item
    directory.mkdir(parents=True, exist_ok=True)
    for name in videos:
        (directory / name).write_bytes(b"not-really-a-video")
    if source is not None:
        (directory / "source.md").write_text(source, encoding="utf-8")
    return directory


SAMPLE_SOURCE = """# Source

- **Local item ID:** 2026-11-10_testcreator_reel-test_ABC123
- **Source URL:** https://www.instagram.com/reel/ABC123/
- **Creator/publisher:** @testcreator (Test Creator)
- **Creator handle observed on slides:** @testcreator
"""


class DiscoveryTests(unittest.TestCase):
    def test_finds_videos_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_tree(root, "item-a", videos=("01.mp4", "02.mov"))
            make_tree(root, "item-b", videos=("01.webm",))
            (root / "item-a" / "notes.txt").write_text("x", encoding="utf-8")
            found = batch.find_videos(root)
        self.assertEqual(len(found), 3)
        self.assertTrue(all(path.suffix in batch.VIDEO_SUFFIXES for path in found))

    def test_single_file_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            path.write_bytes(b"x")
            self.assertEqual(batch.find_videos(path), [path])
            other = Path(tmp) / "notes.md"
            other.write_text("x", encoding="utf-8")
            self.assertEqual(batch.find_videos(other), [])

    def test_output_dir_sits_beside_the_clip(self):
        self.assertEqual(batch.output_for(Path("/a/b/01.mp4")), Path("/a/b/01"))


class ProvenanceTests(unittest.TestCase):
    def test_reads_post_url_and_creator_from_item_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = make_tree(Path(tmp), "item", source=SAMPLE_SOURCE)
            url, creator = batch.provenance_for(directory / "01.mp4")
        self.assertEqual(url, "https://www.instagram.com/reel/ABC123/")
        self.assertEqual(creator, "@testcreator")

    def test_absent_source_is_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = make_tree(Path(tmp), "item")
            url, creator = batch.provenance_for(directory / "01.mp4")
        self.assertIsNone(url)
        self.assertIsNone(creator)

    def test_media_ocr_video_record_shape_is_understood(self):
        """ocr_video.py writes 'Post URL'; media-intake writes 'Source URL'."""
        record = "# Source\n\n- **Platform:** Video\n- **Post URL:** https://example.invalid/p/1/\n"
        with tempfile.TemporaryDirectory() as tmp:
            directory = make_tree(Path(tmp), "item", source=record)
            url, _ = batch.provenance_for(directory / "01.mp4")
        self.assertEqual(url, "https://example.invalid/p/1/")


class SamplingTests(unittest.TestCase):
    def test_ladder_by_duration(self):
        self.assertEqual(batch.fps_for(5.0, None), 4.0)
        self.assertEqual(batch.fps_for(40.0, None), 2.0)
        self.assertEqual(batch.fps_for(120.0, None), 1.0)
        self.assertEqual(batch.fps_for(900.0, None), batch.FPS_FLOOR)

    def test_explicit_override_wins(self):
        self.assertEqual(batch.fps_for(5.0, 8.0), 8.0)

    def test_floor_applies(self):
        self.assertEqual(batch.fps_for(900.0, None, minimum=2.0), 2.0)

    def test_unknown_duration_is_conservative(self):
        self.assertEqual(batch.fps_for(None, None), 2.0)


class ResumeTests(unittest.TestCase):
    def test_draft_marks_a_clip_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "01"
            self.assertFalse(batch.already_done(output))
            (output / "ocr-output").mkdir(parents=True)
            (output / "ocr-output" / "ocr-draft.md").write_text("draft", encoding="utf-8")
            self.assertTrue(batch.already_done(output))

    def test_dedupe_default_is_measured_for_text(self):
        """3.0 silently keeps one frame per caption-swap clip."""
        self.assertLess(batch.DEFAULT_DEDUPE, 1.0)
        self.assertGreaterEqual(batch.DEFAULT_DEDUPE, 0.2)


class SummaryTests(unittest.TestCase):
    def test_counts_split_ok_from_failed(self):
        summary = batch.summarise(
            [
                {"status": "ok", "frames": 5, "seconds": 2.0},
                {"status": "failed", "frames": 0},
                {"status": "timeout", "frames": 0},
            ],
            skipped=4,
        )
        self.assertEqual(summary["videos_ok"], 1)
        self.assertEqual(summary["videos_failed"], 2)
        self.assertEqual(summary["videos_skipped_existing"], 4)
        self.assertEqual(summary["frames_retained"], 5)


def ffmpeg_available() -> bool:
    try:
        return bool(batch.ffmpeg_executable())
    except Exception:
        return False


def pillow_available() -> bool:
    try:
        import PIL  # noqa: F401

        return True
    except ImportError:
        return False


@unittest.skipUnless(ffmpeg_available() and pillow_available(), "ffmpeg or Pillow unavailable")
class EndToEndTests(unittest.TestCase):
    """A real clip through the real pipeline, so provenance and frames are proven."""

    def build_clip(self, directory: Path, captions: tuple[str, ...]) -> Path:
        from PIL import Image, ImageDraw, ImageFont

        fonts = ImageFont.load_default(size=40)
        frames = directory / "_src"
        frames.mkdir(parents=True, exist_ok=True)
        index = 0
        for caption in captions:
            for _ in range(10):
                image = Image.new("RGB", (720, 1280), "white")
                ImageDraw.Draw(image).text((60, 600), caption, fill="black", font=fonts)
                image.save(frames / f"f{index:04d}.png")
                index += 1
        video = directory / "01.mp4"
        subprocess.run(
            [batch.ffmpeg_executable(), "-y", "-loglevel", "error", "-framerate", "30",
             "-i", str(frames / "f%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
            check=True,
        )
        shutil.rmtree(frames)
        return video

    def test_real_clip_produces_frames_provenance_and_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "_inbox"
            item = make_tree(root, "2026-11-10_testcreator_reel-test_ABC123", videos=(), source=SAMPLE_SOURCE)
            self.build_clip(item, ("Step one: feed the starter", "Step two: bulk ferment four hours", "Step three: bake at 250C"))
            report = Path(tmp) / "report.json"
            code = batch.main(["--input", str(root), "--workers", "1", "--fps", "4", "--report", str(report)])
            self.assertEqual(code, 0)
            payload = json.loads(report.read_text(encoding="utf-8"))
            output = item / "01"
            manifest = json.loads((output / "frame-manifest.json").read_text(encoding="utf-8"))
            draft = (output / "ocr-output" / "ocr-draft.md").read_text(encoding="utf-8")
            source = (output / "source.md").read_text(encoding="utf-8")

        self.assertEqual(payload["videos_ok"], 1)
        self.assertGreaterEqual(len(manifest["frames"]), 2, "caption swaps must survive dedupe")
        self.assertIn("https://www.instagram.com/reel/ABC123/", source)
        self.assertIn("@testcreator", source)
        self.assertIn("https://www.instagram.com/reel/ABC123/", draft)
        self.assertTrue(any(word in draft.lower() for word in ("starter", "ferment", "bake")))

    def test_rerun_skips_completed_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "_inbox"
            item = make_tree(root, "item", videos=(), source=SAMPLE_SOURCE)
            self.build_clip(item, ("Only caption",))
            batch.main(["--input", str(root), "--workers", "1", "--fps", "2", "--report", str(Path(tmp) / "r1.json")])
            second = Path(tmp) / "r2.json"
            batch.main(["--input", str(root), "--workers", "1", "--fps", "2", "--report", str(second)])
            payload = json.loads(second.read_text(encoding="utf-8"))
        self.assertEqual(payload["videos_skipped_existing"], 1)
        self.assertEqual(payload["videos_attempted"], 0)


if __name__ == "__main__":
    unittest.main()
