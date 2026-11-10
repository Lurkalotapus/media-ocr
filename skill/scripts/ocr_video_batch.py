#!/usr/bin/env python3
"""Batch text-on-video OCR over a local directory tree.

`ocr_video.py` handles one clip. This walks a staged tree (for example a
media-intake inbox), samples and OCRs every video, resumes where it left off, and
writes a machine-readable report. Local files only: it never fetches a URL and
never invents provenance.

Per-video output, beside the clip:

    <item>/01.mp4
    <item>/01/frames/            sampled, deduplicated frames
    <item>/01/frame-manifest.json
    <item>/01/source.md
    <item>/01/ocr-output/        ocr-draft.md, ocr-evidence.json, ocr-raw.json
    <item>/01/ocr-output-final/  ocr-final.md (empty template, needs review)

Run:
    python ocr_video_batch.py --input /path/to/inbox --report report.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}

# Sampling guidance from the skill: animated word-by-word text needs a high rate,
# long talking-head clips with static captions need almost none.
FPS_LADDER = ((15.0, 4.0), (60.0, 2.0), (300.0, 1.0))
FPS_FLOOR = 0.5

# ocr_video.py defaults to 3.0, which suits whole-scene changes (photos, motion).
# frame_difference() downscales to 32x32 grayscale first, so a caption swap on an
# otherwise static background scores only ~0.3-0.4 -- a 3.0 threshold silently
# discards every distinct caption and keeps one frame per clip. Measured on a
# 720x1280 fixture: 0.4 kept all three captions, 0.5 kept one.
DEFAULT_DEDUPE = 0.4


@dataclass
class Job:
    video: Path
    output: Path
    fps: float
    duration: float | None
    source_url: str | None
    creator: str | None
    item: str


def public_path(path: Path) -> str:
    return path.name


def parse_source_record(source_path: Path) -> dict[str, str]:
    """Read a media-intake or media-ocr source.md without inventing fields."""
    if not source_path.is_file():
        return {}
    details: dict[str, str] = {}
    for line in source_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^- \*\*(.+?):\*\*\s*(.*)$", line)
        if match:
            details[match.group(1)] = match.group(2)
    return details


def provenance_for(video: Path) -> tuple[str | None, str | None]:
    """Pull post URL and creator handle from the owning item directory."""
    details = parse_source_record(video.parent / "source.md")
    url = details.get("Source URL") or details.get("Post URL")
    creator = details.get("Creator handle observed on slides") or details.get("Creator/publisher")
    if creator:
        creator = creator.split("(")[0].strip()
    return (url or None), (creator or None)


def find_videos(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in VIDEO_SUFFIXES else []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES)


def ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def probe_duration(video: Path, ffmpeg: str) -> float | None:
    """Ask ffmpeg for the container duration; None when it cannot be determined."""
    try:
        result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(video)], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr or "")
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def fps_for(duration: float | None, override: float | None, minimum: float = 0.0) -> float:
    """Choose a sampling rate from clip length, never below an explicit floor."""
    if override is not None:
        return override
    if duration is None:
        return FPS_LADDER[1][1]
    for limit, fps in FPS_LADDER:
        if duration <= limit:
            return max(fps, minimum)
    return max(FPS_FLOOR, minimum)


def output_for(video: Path) -> Path:
    """Directory beside the clip, named after it, so items stay self-contained."""
    return video.with_suffix("")


def already_done(output: Path) -> bool:
    return (output / "ocr-output" / "ocr-draft.md").is_file()


def build_jobs(root: Path, *, fps: float | None, min_fps: float, ffmpeg: str, only: Iterable[str] | None = None) -> list[Job]:
    wanted = {name.lower() for name in only} if only else None
    jobs: list[Job] = []
    for video in find_videos(root):
        if wanted and video.parent.name.lower() not in wanted:
            continue
        duration = probe_duration(video, ffmpeg)
        source_url, creator = provenance_for(video)
        jobs.append(
            Job(
                video=video,
                output=output_for(video),
                fps=fps_for(duration, fps, min_fps),
                duration=duration,
                source_url=source_url,
                creator=creator,
                item=video.parent.name,
            )
        )
    return jobs


def run_job(job: Job, script: Path, python: str, threads: int, timeout: int, dedupe: float, roi: str | None) -> dict[str, Any]:
    command = [
        python, str(script),
        "--input", str(job.video),
        "--output", str(job.output),
        "--fps", f"{job.fps:g}",
        "--dedupe-threshold", f"{dedupe:g}",
    ]
    if job.source_url:
        command += ["--source-url", job.source_url]
    if job.creator:
        command += ["--creator", job.creator]
    if roi:
        command += ["--roi", roi]

    env = {**os.environ, "OMP_NUM_THREADS": str(threads), "OpenBLAS_NUM_THREADS": str(threads), "MKL_NUM_THREADS": str(threads)}
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"video": public_path(job.video), "item": job.item, "status": "timeout", "fps": job.fps, "duration": job.duration}
    elapsed = round(time.monotonic() - started, 1)

    frames = 0
    manifest = job.output / "frame-manifest.json"
    if manifest.is_file():
        try:
            frames = len(json.loads(manifest.read_text(encoding="utf-8")).get("frames", []))
        except (OSError, json.JSONDecodeError):
            frames = 0
    if result.returncode != 0:
        return {
            "video": public_path(job.video), "item": job.item, "status": "failed", "fps": job.fps,
            "duration": job.duration, "seconds": elapsed, "stderr": (result.stderr or "")[-600:],
        }
    return {
        "video": public_path(job.video), "item": job.item, "status": "ok", "fps": job.fps,
        "duration": job.duration, "frames": frames, "seconds": elapsed,
    }


def summarise(results: Sequence[dict[str, Any]], skipped: int) -> dict[str, Any]:
    ok = [item for item in results if item["status"] == "ok"]
    return {
        "videos_attempted": len(results),
        "videos_ok": len(ok),
        "videos_failed": len([item for item in results if item["status"] not in {"ok"}]),
        "videos_skipped_existing": skipped,
        "frames_retained": sum(item.get("frames", 0) for item in ok),
        "seconds_total": round(sum(item.get("seconds", 0) for item in ok), 1),
        "failures": [item for item in results if item["status"] != "ok"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch text-on-video OCR over local clips. Never fetches URLs.")
    parser.add_argument("--input", required=True, type=Path, help="Directory tree, item directory, or single video file.")
    parser.add_argument("--report", type=Path, help="Where to write the JSON report (default: INPUT/_video-ocr-report.json).")
    parser.add_argument("--fps", type=float, help="Fixed sampling rate; omit to choose per clip from duration.")
    parser.add_argument("--min-fps", type=float, default=0.0, help="Floor for automatic sampling (e.g. 1.0 for sparse captions).")
    parser.add_argument("--dedupe-threshold", type=float, default=DEFAULT_DEDUPE, help="Mean 32x32 grayscale difference below which frames are dropped. Text-on-video needs ~0.3-0.5; whole-scene changes tolerate 2-3 (default 0.4).")
    parser.add_argument("--roi", help="Optional foreground crop: left,top,right,bottom as frame fractions.")
    parser.add_argument("--workers", type=int, default=3, help="Clips processed concurrently (default 3).")
    parser.add_argument("--threads", type=int, default=4, help="ONNX/OpenMP threads per worker (default 4).")
    parser.add_argument("--timeout", type=int, default=1800, help="Per-clip timeout in seconds.")
    parser.add_argument("--only", action="append", help="Restrict to these item directory names (repeatable).")
    parser.add_argument("--force", action="store_true", help="Re-run clips that already have a draft.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and exit; no frames, no OCR.")
    args = parser.parse_args(argv)

    root = args.input.expanduser().resolve()
    if not root.exists():
        print(f"Input does not exist: {public_path(root)}", file=sys.stderr)
        return 2
    script = Path(__file__).with_name("ocr_video.py")
    if not script.is_file():
        print("ocr_video.py is missing beside this script", file=sys.stderr)
        return 2

    ffmpeg = ffmpeg_executable()
    jobs = build_jobs(root, fps=args.fps, min_fps=args.min_fps, ffmpeg=ffmpeg, only=args.only)
    pending = [job for job in jobs if args.force or not already_done(job.output)]
    skipped = len(jobs) - len(pending)

    if args.dry_run:
        print(f"plan: {len(jobs)} video(s), {len(pending)} pending, {skipped} already drafted")
        for job in pending[:20]:
            duration = f"{job.duration:.1f}s" if job.duration else "unknown"
            print(f"  {job.item}/{public_path(job.video)}  duration={duration} fps={job.fps:g}")
        if len(pending) > 20:
            print(f"  … {len(pending) - 20} more")
        return 0

    if not pending:
        print(f"Nothing to do: {len(jobs)} video(s), all already drafted.")

    results: list[dict[str, Any]] = []
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(run_job, job, script, sys.executable, args.threads, args.timeout, args.dedupe_threshold, args.roi): job
            for job in pending
        }
        for future in as_completed(futures):
            outcome = future.result()
            results.append(outcome)
            done += 1
            if done % 10 == 0 or outcome["status"] != "ok":
                print(f"progress {done}/{len(pending)}: {outcome['item']}/{outcome['video']} {outcome['status']}", flush=True)

    summary = summarise(results, skipped)
    summary["ran_at_utc"] = datetime.now(timezone.utc).isoformat()
    summary["input"] = public_path(root)
    summary["fps_mode"] = f"fixed {args.fps:g}" if args.fps else "auto by duration"
    report = args.report or (root / "_video-ocr-report.json" if root.is_dir() else root.parent / "_video-ocr-report.json")
    report.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        f"video OCR complete: {summary['videos_ok']} ok, {summary['videos_failed']} failed, "
        f"{summary['videos_skipped_existing']} skipped, {summary['frames_retained']} frame(s) retained → {public_path(report)}"
    )
    return 0 if summary["videos_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
