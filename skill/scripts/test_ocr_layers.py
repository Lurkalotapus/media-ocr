#!/usr/bin/env python3
"""Regression tests for the OCR evidence, review, and final-note layers."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("ocr_batch.py")
spec = importlib.util.spec_from_file_location("ocr_batch", SCRIPT)
assert spec and spec.loader
ocr_batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ocr_batch)


class OcrLayerTests(unittest.TestCase):
    def test_evidence_classifies_creator_and_recurrence_without_deleting_text(self) -> None:
        records = [
            {"file": "frame_000001.jpg", "lines": [
                {"box": [[0, 0], [20, 0], [20, 10], [0, 10]], "text": "@maker", "confidence": 0.99},
                {"box": [[0, 20], [100, 20], [100, 30], [0, 30]], "text": "A recurring title", "confidence": 0.99},
            ]},
            {"file": "frame_000002.jpg", "lines": [
                {"box": [[0, 0], [20, 0], [20, 10], [0, 10]], "text": "@maker", "confidence": 0.99},
                {"box": [[0, 20], [100, 20], [100, 30], [0, 30]], "text": "A recurring title", "confidence": 0.99},
            ]},
            {"file": "frame_000003.jpg", "lines": [
                {"box": [[0, 20], [100, 20], [100, 30], [0, 30]], "text": "A recurring title", "confidence": 0.99},
            ]},
        ]

        evidence, repeated = ocr_batch.evidence_records(records, "@maker")

        self.assertEqual(len(evidence[0]["lines"]), 2)
        self.assertEqual(evidence[0]["lines"][0]["role"], "creator_handle")
        self.assertEqual(evidence[0]["lines"][1]["role"], "recurring_text_candidate")
        self.assertEqual(repeated[0]["text"], "A recurring title")
        self.assertEqual(repeated[0]["frame_count"], 3)

    def test_review_draft_surfaces_recurrence_as_a_non_destructive_candidate(self) -> None:
        records = [{"file": "01.jpg", "lines": [
            {"box": [[0, 0], [100, 0], [100, 10], [0, 10]], "text": "A recurring title", "confidence": 0.99}
        ]}]
        report = ocr_batch.markdown_report(
            records, 0.9, "Untitled_001", None, {}, repeated_candidates=[
                {"text": "A recurring title", "frame_count": 3, "frame_files": ["01.jpg", "02.jpg", "03.jpg"]}
            ],
        )

        self.assertIn("## Repeated text candidates (not automatically excluded)", report)
        self.assertIn("A recurring title — visible in 3 frames", report)

    def test_final_note_is_clean_template_with_provenance_and_review_status(self) -> None:
        final = ocr_batch.final_note_template(
            "Untitled_001 by @maker", {"Post URL": "https://example.test/post", "Creator handle observed on slides": "@maker"}
        )

        self.assertIn("status: needs_review", final)
        self.assertIn("## Text", final)
        self.assertIn("## Review trail", final)
        self.assertIn("[[../ocr-output/ocr-evidence.json|OCR evidence]]", final)
        self.assertIn("## Source", final)
        self.assertIn("https://example.test/post", final)
        self.assertNotIn("OCR Confidence Scores", final)

    def test_final_template_never_replaces_hand_curated_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            final_dir = Path(tmp)
            final_path = final_dir / "ocr-final.md"
            final_path.write_text("# Hand-curated reference\n\nA careful final text.\n", encoding="utf-8")

            written = ocr_batch.write_final_template(final_dir, "New generated title", {})

            self.assertFalse(written)
            self.assertEqual(final_path.read_text(encoding="utf-8"), "# Hand-curated reference\n\nA careful final text.\n")


if __name__ == "__main__":
    unittest.main()
