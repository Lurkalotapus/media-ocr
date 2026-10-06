#!/usr/bin/env python3
"""Batch local image OCR for a media-item directory.

Requires: rapidocr-onnxruntime and Pillow.
This script deliberately takes local image files only; acquisition and
provenance staging remain separate, operator-authorised steps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote

IMAGE_SUFFIXES = {".avif", ".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def public_path(path: Path) -> str:
    """Return a non-sensitive local reference suitable for generated output."""
    return path.name


def escape_markdown(value: object) -> str:
    """Render untrusted values as literal Markdown text rather than syntax."""
    return re.sub(r"([\\`*_{}\[\]()<>#+!|])", r"\\\1", str(value))


def safe_wikilink_path(value: object) -> str:
    """Percent-encode untrusted path text before placing it in an Obsidian link."""
    return quote(str(value), safe="/._-")


def image_paths(input_dir: Path) -> list[Path]:
    return sorted(
        (path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda path: path.name.lower(),
    )


def parse_result(raw: Any) -> list[dict[str, Any]]:
    """Normalise legacy rapidocr-onnxruntime [box, text, confidence] rows."""
    rows: list[dict[str, Any]] = []
    if not raw:
        return rows
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        box, text, confidence = item[0], str(item[1]).strip(), item[2]
        if not text:
            continue
        try:
            confidence = round(float(confidence), 4)
        except (TypeError, ValueError):
            confidence = None
        rows.append({"box": box, "text": text, "confidence": confidence})
    return rows


def current_rapidocr_result(result: Any) -> list[dict[str, Any]]:
    """Normalise current RapidOCR's boxes/txts/scores output object."""
    rows: list[dict[str, Any]] = []
    boxes = result.boxes if result.boxes is not None else ()
    texts = result.txts if result.txts is not None else ()
    scores = result.scores if result.scores is not None else ()
    for box, text, confidence in zip(boxes, texts, scores):
        text = str(text).strip()
        if not text:
            continue
        if hasattr(box, "tolist"):
            box = box.tolist()
        try:
            confidence = round(float(confidence), 4)
        except (TypeError, ValueError):
            confidence = None
        rows.append({"box": box, "text": text, "confidence": confidence})
    return rows


def load_engine() -> tuple[str, Any]:
    """Support the current RapidOCR package and its older ONNX wrapper."""
    try:
        from rapidocr import RapidOCR
        # RapidOCR's default INFO logger exposes its model-root path on stdout.
        # Silence routine engine diagnostics so normal completion output remains
        # portable and does not reveal local directory layout.
        return "rapidocr+onnxruntime", RapidOCR(params={"Global.log_level": "ERROR"})
    except ImportError:
        try:
            from rapidocr_onnxruntime import RapidOCR
            return "rapidocr-onnxruntime", RapidOCR()
        except ImportError as error:
            raise RuntimeError(
                "Missing OCR engine. Install with: uv pip install --python <venv>/bin/python rapidocr onnxruntime pillow"
            ) from error


def parse_source(source_path: Path) -> dict[str, str]:
    """Read simple Markdown source bullets without inventing missing metadata."""
    if not source_path.is_file():
        return {}
    details: dict[str, str] = {}
    for line in source_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^- \*\*(.+?):\*\*\s*(.*)$", line)
        if match:
            details[match.group(1)] = match.group(2)
    return details


def normalise_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def display_creator_handle(value: str | None) -> str | None:
    """Keep source markup out of the human-facing title."""
    return value.strip().strip("`") if value else None


def is_creator_watermark(line: dict[str, Any], creator_handle: str | None) -> bool:
    return bool(creator_handle) and normalise_identity(str(line["text"])) == normalise_identity(creator_handle)


def box_bounds(box: Any) -> tuple[float, float, float, float]:
    try:
        points = [(float(point[0]), float(point[1])) for point in box]
    except (TypeError, ValueError, IndexError):
        return (0.0, 0.0, 0.0, 0.0)
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


def slide_paragraphs(lines: list[dict[str, Any]], creator_handle: str | None) -> list[list[dict[str, Any]]]:
    """Order visual lines and use unusually large vertical gaps as paragraphs."""
    content = [line for line in lines if not is_creator_watermark(line, creator_handle)]
    content.sort(key=lambda line: (box_bounds(line["box"])[1], box_bounds(line["box"])[0]))
    if not content:
        return []
    heights = [max(1.0, box_bounds(line["box"])[3] - box_bounds(line["box"])[1]) for line in content]
    gap_threshold = max(16.0, statistics.median(heights) * 1.75)
    paragraphs: list[list[dict[str, Any]]] = [[content[0]]]
    previous_bottom = box_bounds(content[0]["box"])[3]
    for line in content[1:]:
        _, top, _, bottom = box_bounds(line["box"])
        if top - previous_bottom > gap_threshold:
            paragraphs.append([])
        paragraphs[-1].append(line)
        previous_bottom = max(previous_bottom, bottom)
    return paragraphs


def sentence_lines(paragraph: list[dict[str, Any]]) -> list[str]:
    """Join visual line wraps, then render each punctuation-delimited sentence once."""
    text = " ".join(str(line["text"]).strip() for line in paragraph).strip()
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]


def confidence_summary(records: list[dict[str, Any]], creator_handle: str | None, threshold: float) -> tuple[float | None, list[tuple[str, float | None, str]]]:
    scores: list[float] = []
    review: list[tuple[str, float | None, str]] = []
    for record in records:
        for line in record["lines"]:
            if is_creator_watermark(line, creator_handle):
                continue
            score = line["confidence"]
            if score is not None:
                scores.append(score)
            if score is None or score < threshold:
                review.append((record["file"], score, str(line["text"])))
    return (sum(scores) / len(scores) if scores else None), review


def filter_persistent_overlays(records: list[dict[str, Any]], frequency: float, similarity: float = 0.78) -> tuple[list[dict[str, Any]], int]:
    """Remove text that recurs across much of a moving video (logos/watermarks)."""
    if frequency <= 0 or not records:
        return records, 0
    clusters: list[dict[str, Any]] = []
    membership: dict[tuple[int, int], int] = {}
    for record_index, record in enumerate(records):
        for line_index, line in enumerate(record["lines"]):
            normalised = normalise_identity(str(line["text"]))
            if len(normalised) < 5:
                continue
            cluster_index = next(
                (index for index, cluster in enumerate(clusters) if SequenceMatcher(None, normalised, cluster["normalised"]).ratio() >= similarity),
                None,
            )
            if cluster_index is None:
                clusters.append({"normalised": normalised, "frames": set()})
                cluster_index = len(clusters) - 1
            clusters[cluster_index]["frames"].add(record_index)
            membership[(record_index, line_index)] = cluster_index
    minimum_frames = max(3, math.ceil(len(records) * frequency))
    overlay_clusters = {index for index, cluster in enumerate(clusters) if len(cluster["frames"]) >= minimum_frames}
    filtered: list[dict[str, Any]] = []
    removed = 0
    for record_index, record in enumerate(records):
        lines = []
        for line_index, line in enumerate(record["lines"]):
            if membership.get((record_index, line_index)) in overlay_clusters:
                removed += 1
                continue
            lines.append(line)
        filtered.append({**record, "lines": lines})
    return filtered, removed


def evidence_records(records: list[dict[str, Any]], creator_handle: str | None, similarity: float = 0.92) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Add cautious, non-destructive roles to OCR observations.

    Repetition is evidence, not proof of a watermark: animated captions and title
    cards repeat too. Only an exact creator-handle match receives a definitive
    role. Other text that appears in at least three frames is surfaced as a
    recurring-text candidate for review and remains in every output layer.
    """
    clusters: list[dict[str, Any]] = []
    membership: dict[tuple[int, int], int] = {}
    for record_index, record in enumerate(records):
        for line_index, line in enumerate(record["lines"]):
            normalised = normalise_identity(str(line["text"]))
            if len(normalised) < 5 or is_creator_watermark(line, creator_handle):
                continue
            cluster_index = next(
                (index for index, cluster in enumerate(clusters) if SequenceMatcher(None, normalised, cluster["normalised"]).ratio() >= similarity),
                None,
            )
            if cluster_index is None:
                clusters.append({"normalised": normalised, "text": str(line["text"]), "frames": set(), "frame_files": []})
                cluster_index = len(clusters) - 1
            cluster = clusters[cluster_index]
            if record_index not in cluster["frames"]:
                cluster["frames"].add(record_index)
                cluster["frame_files"].append(record["file"])
            membership[(record_index, line_index)] = cluster_index

    recurring_clusters = {index for index, cluster in enumerate(clusters) if len(cluster["frames"]) >= 3}
    evidence: list[dict[str, Any]] = []
    for record_index, record in enumerate(records):
        evidence_lines: list[dict[str, Any]] = []
        for line_index, line in enumerate(record["lines"]):
            enriched = dict(line)
            cluster_index = membership.get((record_index, line_index))
            if is_creator_watermark(line, creator_handle):
                enriched["role"] = "creator_handle"
            elif cluster_index in recurring_clusters:
                enriched["role"] = "recurring_text_candidate"
            else:
                enriched["role"] = "content_candidate"
            if cluster_index is not None:
                cluster = clusters[cluster_index]
                enriched["recurrence"] = {"frame_count": len(cluster["frames"]), "frame_files": cluster["frame_files"]}
            evidence_lines.append(enriched)
        evidence.append({**record, "lines": evidence_lines})
    repeated = [
        {"text": cluster["text"], "frame_count": len(cluster["frames"]), "frame_files": cluster["frame_files"]}
        for index, cluster in enumerate(clusters) if index in recurring_clusters
    ]
    repeated.sort(key=lambda candidate: (-candidate["frame_count"], candidate["text"].lower()))
    return evidence, repeated


def final_note_template(title: str, source: dict[str, str]) -> str:
    """Create a deliberately empty, provenance-preserving final-reference note."""
    lines = [
        "---", "type: instagram-reference", "status: needs_review", "---", "",
        f"# {escape_markdown(title)}", "",
        "> [!warning] Review required", "> This note is intentionally empty until the OCR review draft has been checked against the original media. It must not be treated as a verified quote, claim, or source of authorship.",
        "", "## Text", "", "[Text awaiting human review.]", "",
        "## Review trail", "", "- [[../ocr-output/ocr-draft.md|OCR review draft]]", "- [[../ocr-output/ocr-evidence.json|OCR evidence]]", "- [[../ocr-output/ocr-raw.json|Raw OCR observations]]", "",
        "## Source", "",
    ]
    for key, value in source.items():
        if key != "Notes":
            lines.append(f"- **{escape_markdown(key)}:** {escape_markdown(value)}")
    if source.get("Notes"):
        lines.append(f"- **Notes:** {escape_markdown(source['Notes'])}")
    lines.append("")
    content = "\n".join(lines)
    fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content.replace("---\n\n", f"---\n<!-- ocr-template-sha256: {fingerprint} -->\n\n", 1)


def write_final_template(final_dir: Path, title: str, source: dict[str, str]) -> bool:
    """Write a review template, never replacing a human-reviewed final note."""
    final_dir.mkdir(parents=True, exist_ok=True)
    final_path = final_dir / "ocr-final.md"
    if final_path.exists():
        existing = final_path.read_text(encoding="utf-8")
        marker = re.search(r"<!-- ocr-template-sha256: ([0-9a-f]{64}) -->\n", existing)
        unsigned = re.sub(r"<!-- ocr-template-sha256: [0-9a-f]{64} -->\n", "", existing, count=1)
        untouched_template = marker and hashlib.sha256(unsigned.encode("utf-8")).hexdigest() == marker.group(1)
        if not untouched_template:
            return False
    final_path.write_text(final_note_template(title, source), encoding="utf-8")
    return True


def markdown_report(records: list[dict[str, Any]], threshold: float, title: str, creator_handle: str | None, source: dict[str, str], image_link_prefix: str = "../", repeated_candidates: list[dict[str, Any]] | None = None) -> str:
    """Build a clean, human-facing Markdown note; raw OCR remains in ocr.json."""
    lines = [f"# {escape_markdown(title)}", ""]
    if repeated_candidates:
        lines.extend(("## Repeated text candidates (not automatically excluded)", "", "> These observations may be animated captions, title cards, or persistent overlays. They remain in the draft and require human judgment.", ""))
        for candidate in repeated_candidates:
            lines.append(f"- {escape_markdown(candidate['text'])} — visible in {candidate['frame_count']} frames")
        lines.append("")
    for index, record in enumerate(records, 1):
        paragraphs = slide_paragraphs(record["lines"], creator_handle)
        lines.append(f"<!-- Slide {index:02d}: {escape_markdown(record['file'])} -->")
        if not paragraphs:
            lines.extend(("[No text detected — inspect the original slide.]", ""))
            continue
        for paragraph in paragraphs:
            lines.extend(escape_markdown(sentence) for sentence in sentence_lines(paragraph))
            lines.append("")
    average, review = confidence_summary(records, creator_handle, threshold)
    lines.extend(("## Source", ""))
    for key, value in source.items():
        if key != "Notes":
            lines.append(f"- **{escape_markdown(key)}:** {escape_markdown(value)}")
    if source.get("Notes"):
        lines.append(f"- **Notes:** {escape_markdown(source['Notes'])}")
    lines.extend((f"- **Captured images:** [[{safe_wikilink_path(image_link_prefix)}01.jpg|carousel slide files]]", "- **Source record:** [[../source.md|source.md]]", "", "## OCR Confidence Scores", ""))
    lines.append(f"- **Average:** {'n/a' if average is None else f'{average:.2f}'}")
    if review:
        for file_name, score, text in review:
            rendered_score = "unknown" if score is None else f"{score:.2f}"
            target = safe_wikilink_path(f"{image_link_prefix}{file_name}")
            lines.append(f"- **Requires review:** {rendered_score} from [[{target}|{escape_markdown(file_name)}]] — {escape_markdown(text)}")
    else:
        lines.append(f"- **Requires review:** none below {threshold:.2f}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR a local image-sequence directory into reviewable JSON and Markdown; it never fetches URLs.")
    parser.add_argument("--input", required=True, type=Path, help="Directory containing local image files.")
    parser.add_argument("--output", type=Path, help="Output directory (default: INPUT/ocr-output).")
    parser.add_argument("--source-file", type=Path, help="Optional source.md path; defaults to INPUT/source.md.")
    parser.add_argument("--image-link-prefix", default="../", help="Relative Obsidian path prefix for verification images.")
    parser.add_argument("--title", help="Optional title override. Default is a rename-friendly Untitled_001 placeholder.")
    parser.add_argument("--threshold", type=float, default=0.90, help="Confidence below which an OCR line requires review (default: 0.90).")
    parser.add_argument("--persistent-overlay-frequency", type=float, default=0.0, help="Remove OCR lines repeating in this fraction of frames; use for video watermarks only (default: off).")
    parser.add_argument("--check", action="store_true", help="Validate input and OCR-engine availability without processing images.")
    args = parser.parse_args()

    if not args.input.is_dir():
        print(f"Input directory does not exist: {public_path(args.input)}", file=sys.stderr)
        return 2
    paths = image_paths(args.input)
    if not paths:
        print(f"No supported images found in: {public_path(args.input)}", file=sys.stderr)
        return 2
    if not 0 <= args.persistent_overlay_frequency <= 1:
        print("persistent-overlay-frequency must be between 0 and 1", file=sys.stderr)
        return 2
    try:
        engine_name, engine = load_engine()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 3

    if args.check:
        print(f"Preflight passed: {len(paths)} image(s) ready; {engine_name} import succeeded.")
        return 0

    records: list[dict[str, Any]] = []
    for path in paths:
        result = engine(str(path))
        if engine_name == "rapidocr+onnxruntime":
            lines = current_rapidocr_result(result)
            elapsed = result.elapse
        else:
            raw, elapsed = result
            lines = parse_result(raw)
        records.append({"file": path.name, "elapsed_seconds": round(float(elapsed), 4), "lines": lines})

    output_dir = args.output or args.input / "ocr-output"
    output_dir.mkdir(parents=True, exist_ok=True)
    source = parse_source(args.source_file or args.input / "source.md")
    creator_handle = source.get("Creator handle observed on slides")
    display_handle = display_creator_handle(creator_handle)
    title = args.title or f"Untitled_001{f' by {display_handle}' if display_handle else ''}"
    raw_records = records
    evidence, repeated_candidates = evidence_records(raw_records, creator_handle)
    records, removed_overlay_lines = filter_persistent_overlays(records, args.persistent_overlay_frequency)
    final_dir = output_dir.parent / "ocr-output-final"
    final_template_written = write_final_template(final_dir, title, source)
    average, review = confidence_summary(records, creator_handle, args.threshold)
    manifest = {
        "source_directory": public_path(args.input),
        "files": [path.name for path in paths],
        "engine": engine_name,
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "review_threshold": args.threshold,
        "average_confidence": average,
        "review_line_count": len(review),
        "persistent_overlay_frequency": args.persistent_overlay_frequency,
        "removed_overlay_line_count": removed_overlay_lines,
        "evidence_file": "ocr-evidence.json",
        "review_draft_file": "ocr-draft.md",
        "final_reference_note": "../ocr-output-final/ocr-final.md",
        "final_template_written": final_template_written,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output_dir / "ocr-raw.json").write_text(json.dumps(raw_records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "ocr-evidence.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "ocr.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "ocr-draft.md").write_text(markdown_report(records, args.threshold, title, creator_handle, source, args.image_link_prefix, repeated_candidates), encoding="utf-8")
    print(f"OCR complete: {len(records)} image(s) → {public_path(output_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
