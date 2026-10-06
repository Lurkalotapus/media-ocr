#!/usr/bin/env python3
"""Regression tests for safe, repeatable OCR output generation."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).parent


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ocr_batch = load_module("ocr_batch")
ocr_video = load_module("ocr_video")
transcribe_audio = load_module("transcribe_audio")


class EnginePrivacyTests(unittest.TestCase):
    def test_current_rapidocr_uses_error_only_routine_logging(self) -> None:
        captured: dict[str, object] = {}

        class FakeRapidOCR:
            def __init__(self, **kwargs) -> None:
                captured.update(kwargs)

        module = types.ModuleType("rapidocr")
        module.RapidOCR = FakeRapidOCR
        with patch.dict(sys.modules, {"rapidocr": module}):
            engine_name, engine = ocr_batch.load_engine()

        self.assertEqual(engine_name, "rapidocr+onnxruntime")
        self.assertIsInstance(engine, FakeRapidOCR)
        self.assertEqual(captured, {"params": {"Global.log_level": "ERROR"}})


class RepeatabilityTests(unittest.TestCase):
    def test_frame_extraction_discards_stale_frames_before_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            frames_dir = Path(tmp) / "frames"
            frames_dir.mkdir()
            stale = frames_dir / "frame_999999.jpg"
            stale.write_bytes(b"stale")

            def fake_run(command, **kwargs):
                (frames_dir / "frame_000001.jpg").write_bytes(b"fresh")

            with patch.object(ocr_video, "ffmpeg_executable", return_value="ffmpeg"), patch.object(
                ocr_video.subprocess, "run", side_effect=fake_run
            ):
                frames = ocr_video.extract_frames(Path(tmp) / "clip.mp4", frames_dir, 1.0)

            self.assertEqual([frame.name for frame in frames], ["frame_000001.jpg"])
            self.assertFalse(stale.exists())

    def test_rerun_preserves_an_edited_generated_final_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            final_dir = Path(tmp)
            final_path = final_dir / "ocr-final.md"
            original = ocr_batch.final_note_template("Original title", {}) + "\nReviewer added context.\n"
            final_path.write_text(original, encoding="utf-8")

            written = ocr_batch.write_final_template(final_dir, "Replacement title", {})

            self.assertFalse(written)
            self.assertEqual(final_path.read_text(encoding="utf-8"), original)


class SafeRenderingTests(unittest.TestCase):
    def test_batch_run_keeps_absolute_paths_out_of_artifacts_and_console_output(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "private-input"
            input_dir.mkdir()
            Image.new("RGB", (1, 1)).save(input_dir / "01.jpg")
            output_dir = root / "private-output"
            stdout = StringIO()

            class EmptyEngine:
                def __call__(self, path):
                    return [], 0.0

            with patch.object(ocr_batch, "load_engine", return_value=("fake", EmptyEngine())), patch(
                "sys.argv", ["ocr_batch.py", "--input", str(input_dir), "--output", str(output_dir)]
            ), patch("sys.stdout", stdout):
                self.assertEqual(ocr_batch.main(), 0)

            rendered = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.glob("*") if path.is_file())
            self.assertNotIn(str(root), rendered)
            self.assertNotIn(str(root), stdout.getvalue())

    def test_markdown_report_escapes_untrusted_title_source_and_ocr_text(self) -> None:
        records = [{"file": "01.jpg", "lines": [{
            "box": [[0, 0], [100, 0], [100, 10], [0, 10]],
            "text": "[spoof](https://evil.test) <script>alert(1)</script>",
            "confidence": 0.2,
        }]}]
        report = ocr_batch.markdown_report(
            records,
            0.9,
            "# injected heading",
            None,
            {"[key](https://evil.test)": "[value](https://evil.test) <script>bad</script>"},
        )

        self.assertIn("# \\# injected heading", report)
        self.assertNotIn("[spoof](https://evil.test)", report)
        self.assertNotIn("<script>", report)
        self.assertIn("\\[spoof\\]\\(https://evil.test\\)", report)
        self.assertIn("\\<script\\>", report)

    def test_markdown_report_neutralises_untrusted_link_paths(self) -> None:
        records = [{"file": "01.jpg|spoof]]", "lines": []}]
        report = ocr_batch.markdown_report(records, 0.9, "Untitled", None, {}, "../images/]]spoof")

        self.assertNotIn("../images/]]spoof", report)
        self.assertNotIn("[[../images/]]spoof01.jpg|spoof]]", report)
        self.assertIn("%5D%5D", report)

    def test_output_metadata_uses_non_absolute_local_references_by_default(self) -> None:
        private_path = Path("/home/alice/private/project/clip.mp4")
        self.assertEqual(ocr_batch.public_path(private_path), "clip.mp4")
        self.assertEqual(ocr_video.public_path(private_path), "clip.mp4")

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            ocr_video.write_source_record(
                output_dir, private_path, 1.0, 1, "[spoof](https://evil.test)", "<script>bad</script>"
            )
            source = (output_dir / "source.md").read_text(encoding="utf-8")
            self.assertNotIn(str(private_path.parent), source)
            self.assertNotIn("[spoof](https://evil.test)", source)
            self.assertNotIn("<script>", source)
            self.assertEqual(transcribe_audio.escape_markdown("<script>bad</script>"), "\\<script\\>bad\\</script\\>")


if __name__ == "__main__":
    unittest.main()
