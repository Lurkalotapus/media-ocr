#!/usr/bin/env python3
"""Optional local speech-to-text pass for difficult video review."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def public_path(path: Path) -> str:
    """Return a non-sensitive local reference suitable for generated output."""
    return path.name


def escape_markdown(value: object) -> str:
    """Render untrusted transcript text as literal Markdown text rather than syntax."""
    return re.sub(r"([\\`*_{}\[\]()<>#+!|])", r"\\\1", str(value))


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe speech from a local video/audio file with faster-whisper; no URLs are fetched.")
    parser.add_argument("--input", type=Path, required=True, help="Local video or audio source")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    parser.add_argument("--model", default="small", help="Whisper model name; default: small")
    parser.add_argument("--language", default=None, help="Optional language code, e.g. en")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    parser.add_argument("--compute-type", default="int8", help="faster-whisper compute type")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"input does not exist: {args.input}")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        parser.error("Install the optional dependency first: uv pip install faster-whisper")

    args.output.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    segments, info = model.transcribe(str(args.input), language=args.language, vad_filter=True)
    rows = []
    for segment in segments:
        rows.append({"start": round(segment.start, 3), "end": round(segment.end, 3), "text": segment.text.strip()})

    payload = {
        "source_file": public_path(args.input),
        "model": args.model,
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "segments": rows,
    }
    (args.output / "speech-transcript.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Speech transcript", "", "> This is an auxiliary speech-to-text transcript for human comparison. It is not a substitute for reviewing the source media.", ""]
    for row in rows:
        lines.append(f"**[{row['start']:.1f}–{row['end']:.1f}s]** {escape_markdown(row['text'])}")
        lines.append("")
    (args.output / "speech-transcript.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Transcription complete: {len(rows)} segment(s) → {public_path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
