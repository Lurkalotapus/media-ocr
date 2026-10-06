#!/usr/bin/env python3
"""Extract text-bearing frames from a local video and run the Media OCR flow.

Requires the same virtual environment as ocr_batch.py plus imageio-ffmpeg.
No audio transcription or URL fetching is performed.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageStat


def public_path(path: Path) -> str:
    """Return a non-sensitive local reference suitable for generated output."""
    return path.name


def escape_markdown(value: object) -> str:
    """Render untrusted values as literal Markdown text rather than syntax."""
    return re.sub(r"([\\`*_{}\[\]()<>#+!|])", r"\\\1", str(value))


def ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise RuntimeError(
            "Missing video extractor. Install with: uv pip install --python <venv>/bin/python imageio-ffmpeg"
        ) from error
    return imageio_ffmpeg.get_ffmpeg_exe()


def parse_roi(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        left, top, right, bottom = (float(part) for part in value.split(","))
    except ValueError as error:
        raise ValueError("roi must be four comma-separated fractions: left,top,right,bottom") from error
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError("roi fractions must be within 0..1 and left/top less than right/bottom")
    return left, top, right, bottom


def extract_frames(video_path: Path, frames_dir: Path, fps: float, roi: tuple[float, float, float, float] | None = None) -> list[Path]:
    """Sample a local clip at a fixed rate; timestamps are derived from sample index."""
    if fps <= 0:
        raise ValueError("fps must be greater than zero")
    frames_dir.mkdir(parents=True, exist_ok=True)
    for stale_frame in frames_dir.glob("frame_*.jpg"):
        stale_frame.unlink()
    output_pattern = frames_dir / "frame_%06d.jpg"
    filters = [f"fps={fps}"]
    if roi:
        left, top, right, bottom = roi
        filters.append(f"crop=iw*{right-left}:ih*{bottom-top}:iw*{left}:ih*{top}")
    command = [
        ffmpeg_executable(), "-y", "-i", str(video_path), "-vf", ",".join(filters),
        "-q:v", "2", str(output_pattern),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as error:
        detail = error.stderr[-1500:] if error.stderr else "no ffmpeg diagnostic"
        raise RuntimeError(f"Frame extraction failed:\n{detail}") from error
    return sorted(frames_dir.glob("frame_*.jpg"))


def frame_difference(left: Path, right: Path) -> float:
    """Return mean grayscale pixel difference for simple duplicate-frame removal."""
    with Image.open(left) as left_image, Image.open(right) as right_image:
        left_gray = left_image.convert("L").resize((32, 32))
        right_gray = right_image.convert("L").resize((32, 32))
        difference = ImageStat.Stat(__import__("PIL.ImageChops", fromlist=["difference"]).difference(left_gray, right_gray))
        return float(difference.mean[0])


def deduplicate_frames(frames: Iterable[Path], threshold: float) -> list[Path]:
    """Keep the first of visually near-identical sampled frames."""
    kept: list[Path] = []
    for frame in frames:
        if not kept or frame_difference(kept[-1], frame) >= threshold:
            kept.append(frame)
        else:
            frame.unlink()
    return kept


def sample_index(frame: Path) -> int:
    match = re.search(r"(\d+)$", frame.stem)
    if not match:
        raise ValueError(f"Frame name does not carry a sample index: {frame.name}")
    return int(match.group(1))


def write_source_record(output_dir: Path, video_path: Path, fps: float, retained: int, source_url: str | None, creator: str | None) -> None:
    source_path = output_dir / "source.md"
    if source_path.exists():
        return
    lines = [
        "# Source", "", "- **Platform:** Video", f"- **Video local file:** `{public_path(video_path)}`",
        f"- **Frame sampling:** {fps:g} frame(s) per second", f"- **Frames retained:** {retained}",
    ]
    if source_url:
        lines.append(f"- **Post URL:** {escape_markdown(source_url)}")
    if creator:
        lines.append(f"- **Creator handle observed on slides:** {escape_markdown(creator)}")
    lines.append("")
    source_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract local text-on-video frames, deduplicate them, and run Media OCR without fetching URLs.")
    parser.add_argument("--input", required=True, type=Path, help="Local video file to process.")
    parser.add_argument("--output", type=Path, help="Output directory (default: beside the video, named after it).")
    parser.add_argument("--fps", type=float, default=1.0, help="Sample rate in frames per second (default: 1).")
    parser.add_argument("--dedupe-threshold", type=float, default=3.0, help="Mean grayscale difference below which sampled frames are dropped (default: 3).")
    parser.add_argument("--roi", help="Optional foreground crop: left,top,right,bottom as fractions of the frame.")
    parser.add_argument("--source-url", help="Optional original public post URL for provenance.")
    parser.add_argument("--creator", help="Optional creator handle for title and watermark suppression.")
    parser.add_argument("--title", help="Optional final note title override.")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Video file does not exist: {public_path(args.input)}", file=sys.stderr)
        return 2
    if args.dedupe_threshold < 0:
        print("dedupe-threshold cannot be negative", file=sys.stderr)
        return 2

    output_dir = args.output or args.input.with_suffix("")
    frames_dir = output_dir / "frames"
    try:
        sampled = extract_frames(args.input, frames_dir, args.fps, parse_roi(args.roi))
        retained = deduplicate_frames(sampled, args.dedupe_threshold)
    except (RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 3
    if not retained:
        print("No frames were extracted from the video.", file=sys.stderr)
        return 3

    write_source_record(output_dir, args.input, args.fps, len(retained), args.source_url, args.creator)
    frame_manifest = [
        {"file": frame.name, "timestamp_seconds": round((sample_index(frame) - 1) / args.fps, 3)}
        for frame in retained
    ]
    (output_dir / "frame-manifest.json").write_text(
        json.dumps({"video": public_path(args.input), "fps": args.fps, "frames": frame_manifest, "ran_at_utc": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n",
        encoding="utf-8",
    )

    ocr_script = Path(__file__).with_name("ocr_batch.py")
    command = [
        sys.executable, str(ocr_script), "--input", str(frames_dir), "--output", str(output_dir / "ocr-output"),
        "--source-file", str(output_dir / "source.md"), "--image-link-prefix", "../frames/",
    ]
    if args.title:
        command.extend(("--title", args.title))
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
        return error.returncode
    print(f"Video OCR complete: {len(retained)} retained frame(s) → {public_path(output_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
