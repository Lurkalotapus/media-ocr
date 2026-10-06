---
name: media-ocr
description: "Use when OCRing local images, image sequences, or text-on-video into reviewable evidence."
source: user-created
risk: medium
---

# Media OCR

Use this workflow to turn local text-over-image media, image sequences, and text-on-video into a reviewable corpus. Instagram saves, carousels, and Reels are examples of media that may be staged separately. The output is a draft, not an authority: OCR can confidently misread stylised typography, line breaks, emoji, names, and attribution.

## Scope: local processing only

Media OCR processes **local image, video, and audio files only**. It does not fetch URLs, open sites, log in, download, scrape, crawl, or otherwise acquire media. Acquisition is a separate stage that places local files alongside their provenance record.

## Acquisition Contract

There are exactly three acquisition modes:

1. **Manual local import (default).** The operator imports local files they hold or are authorised to process and records available provenance.
2. **User-directed browser capture (optional).** This is limited to specific authorised items or small batches. It must not bypass access controls, login walls, private-account restrictions, rate limits, or other platform protections.
3. **Automated collection (not included).** Media OCR has no downloader, crawler, scraper, or URL-fetching capability. Automated collection needs a separate approved design.

This contract preserves operator agency: source selection and authorisation remain explicit operator decisions. It preserves provenance by associating it with the staged media, protects privacy by limiting unnecessary collection, and avoids indiscriminate collection. These are transparent constraints, not covert persuasion or a claim that a source is authorised.

## What this skill does

- processes **local media files** supplied by a separate acquisition stage;
- preserves image/frame order and available source/provenance in a manifest;
- produces one Markdown draft and machine-readable JSON per image set;
- gives uncertain results an explicit review pass before they enter a knowledge system.

## Provenance, rights, and attribution

At intake, create `source.md` when practical. Record at least:

- local file or staged-item identifier;
- source URL or source location, if known;
- creator, publisher, or account identifier, if shown or known;
- acquisition mode and capture/import date;
- visible date, caption/context, and relevant notes; and
- rights, licence, attribution, and uncertainty notes.

Never invent these fields. A visible handle, URL, credit, or OCR output does not establish copyright, permission, authorship, or the truth of a quoted claim. Preserve missing information and uncertainty for review. Do not silently turn a quote graphic into an unattributed assertion.

## Intake convention

Create one directory per item or image sequence. Name images with zero-padded numbers so their order survives every tool:

```text
~/Documents/knowledge-vault/Inbox/media/
  2026-09-28_creator-short-title/
    01.jpg
    02.jpg
    03.jpg
    source.md
```

Example `source.md` fields:

```markdown
# Source

- **Local item ID:** 2026-09-28_creator-short-title
- **Acquisition mode:** Manual local import
- **Source URL:** https://example.invalid/original-item
- **Creator/publisher:** @creator
- **Captured/imported:** 2026-09-28
- **Rights/attribution uncertainty:** Visible handle only; permission and original authorship not verified.
- **Notes:** Caption context or other relevant observations.
```

Instagram may be named in `Source URL`, `Creator/publisher`, or `Notes` when it is the actual source; it is not required and does not change Media OCR's local-only boundary.

## Setup (one-time)

Use a dedicated virtual environment rather than installing legacy OCR dependencies globally:

```bash
mkdir -p ~/.local/share/media-ocr
uv venv ~/.local/share/media-ocr/.venv
uv pip install --python ~/.local/share/media-ocr/.venv/bin/python rapidocr onnxruntime pillow
```

If `uv` is not installed, use `python3 -m venv` and that environment's `pip`. RapidOCR plus ONNX Runtime runs locally and does not require a separately installed Tesseract binary.

### Local ZIP fallback

If PyPI is unreachable but `~/Downloads/RapidOCR-main.zip` is available, unpack the source and install it locally. This avoids redownloading the RapidOCR source, though its dependencies—especially `onnxruntime` and the OCR models—still need a usable connection at least once:

```bash
mkdir -p ~/.local/share/media-ocr/vendor
unzip -q ~/Downloads/RapidOCR-main.zip -d ~/.local/share/media-ocr/vendor
SETUPTOOLS_SCM_PRETEND_VERSION_FOR_RAPIDOCR=0.0+local \
  uv pip install --no-deps --python ~/.local/share/media-ocr/.venv/bin/python \
  ~/.local/share/media-ocr/vendor/RapidOCR-main/python
uv pip install --python ~/.local/share/media-ocr/.venv/bin/python \
  -r ~/.local/share/media-ocr/vendor/RapidOCR-main/python/requirements.txt onnxruntime
```

## Workflow

1. **Stage local media and provenance.** Use the Acquisition Contract; preserve source context in `source.md` without inventing missing rights or attribution.
2. **Preflight.** Run:
   ```bash
   python scripts/ocr_batch.py --input /path/to/local-media --check
   ```
   Resolve missing packages or unreadable files before processing.
3. **OCR.** Run:
   ```bash
   python scripts/ocr_batch.py --input /path/to/local-media --output /path/to/local-media/ocr-output
   ```
   For a whole inbox, run separately per item directory so source relationships remain intact.
4. **Review before ingestion.** Read `ocr-draft.md` against the original media. Correct errors, particularly proper nouns, numbers, negations, quotation marks, sequence order, and attributions. Keep `[illegible]` rather than guessing.
5. **Create a final note intentionally.** Move only reviewed text into `ocr-output-final/ocr-final.md` or another appropriate note, with source links and uncertainty retained. Do not dump hundreds of unreviewed OCR fragments into a knowledge graph.

## Text-on-video workflow

For a local clip where the useful material is text on screen, install the user-local FFmpeg bundle once—no sudo or system package is required:

```bash
uv pip install --python ~/.local/share/media-ocr/.venv/bin/python imageio-ffmpeg
```

Then run the video wrapper with the OCR environment's Python:

```bash
~/.local/share/media-ocr/.venv/bin/python scripts/ocr_video.py \
  --input /path/to/local-clip.mp4 \
  --output /path/to/video-note \
  --fps 1 \
  --roi '0.15,0.30,0.85,0.72' \
  --source-url 'https://source.example/item/…' \
  --creator '@creator'
```

It samples at one frame per second by default, removes visually near-identical consecutive frames, records each kept frame's approximate timestamp in `frame-manifest.json`, and runs the same OCR/note formatter over the retained frames. `--source-url` records provenance only; it is never fetched. When a person, garment, or scenery contains distracting text, use `--roi 'left,top,right,bottom'` to crop OCR to a fractional foreground region while retaining the original video as the source. The crop is intentionally opt-in: text overlays can legitimately appear anywhere. The wrapper preserves recurring text by default: animated captions can repeat across frames and must not be mistaken for a watermark. If a persistent logo is genuinely intrusive, inspect the `ocr-evidence.json` recurrence roles during review rather than globally deleting text. Raw OCR observations are retained regardless. Increase `--fps` for rapidly changing text; tune `--dedupe-threshold` only if it keeps too many static frames or removes meaningful transitions.

For word-by-word animated text, start at `--fps 4 --dedupe-threshold 0.5`; the ordinary 1 fps setting will miss short-lived words. This captures partial build states too, so reconstruct the final sentence from the most complete successive frames and preserve uncertainty where a word never appears cleanly.

This workflow is deliberately **text-on-video only** by default. It does not transcribe narration or audio unless the optional speech pass below is explicitly requested.

### Optional speech-to-text review pass

When the OCR review produces many low-confidence lines, missing frames, or evidence that useful content is spoken rather than displayed, offer an auxiliary local speech transcript if the operator can install or already has `faster-whisper`. Keep this opt-in: audio transcription adds a model download, processing time, and a second error surface. It should corroborate and repair the human review draft, never silently replace visible on-screen text.

Install the optional dependency in the dedicated OCR environment:

```bash
uv pip install --python ~/.local/share/media-ocr/.venv/bin/python faster-whisper
```

Run it against the original local video or audio source:

```bash
~/.local/share/media-ocr/.venv/bin/python scripts/transcribe_audio.py \
  --input /path/to/local-clip.mp4 \
  --output /path/to/video-note/ocr-output \
  --model small \
  --language en
```

The pass creates `speech-transcript.md` for human reading and timestamped `speech-transcript.json` for downstream provenance. Compare it against the OCR evidence and source media, identify speaker turns manually when diarization is unavailable, then incorporate only confirmed wording into `ocr-output-final/ocr-final.md`. Record speech-transcription use in the final note's review trail. Do not treat Whisper confidence or fluent wording as proof of accuracy, attribution, or authorship.

## Outputs — three deliberately separate layers

Every run creates a review chain. Do not collapse these layers: they answer different questions and prevent OCR noise from quietly becoming “knowledge.”

### 1. Evidence — machine-readable and non-destructive

Inside `ocr-output/`:

- `ocr-raw.json` — immutable, unfiltered OCR observations exactly as returned by the engine;
- `ocr-evidence.json` — the same observations enriched with cautious semantic roles and recurrence data; and
- `ocr.json` — the review projection used to render the draft (it can honour the explicit legacy overlay-filter option, while raw/evidence remain intact).

Evidence roles are deliberately conservative:

- `creator_handle` — exact match to a known creator/account identifier;
- `content_candidate` — ordinary detected text;
- `recurring_text_candidate` — text seen in at least three frames.

A recurring candidate is **not automatically a watermark**. It could be an animated caption, a title card, or a persistent overlay. The workflow never deletes it merely for recurring. The legacy `--persistent-overlay-frequency` option is an explicit review convenience only; it never changes raw evidence.

### 2. Review draft — audit-friendly Markdown

`ocr-output/ocr-draft.md` is the place to compare OCR against the original images or frames. It preserves image/frame order, text flow, confidence review items, and source context. When recurring text is found, a clearly labelled **“Repeated text candidates (not automatically excluded)”** section appears above the transcript. Creator-handle matches are hidden from the prose body but remain visible in `ocr-evidence.json`.

### 3. Final reference note — clean human text, only after review

`ocr-output-final/ocr-final.md` is created as a safe, empty reference-note template. An untouched generated template may be refreshed on rerun; any edit, including an added note while the placeholder remains, preserves the file. It contains:

- `status: needs_review` frontmatter;
- an intentionally blank `## Text` section;
- a **Review trail** linking back to the draft, evidence, and raw observations; and
- a compact `## Source` section.

After comparing the draft with the original media, replace the placeholder with clean, deduplicated prose, correct its title, and change the status to `reviewed`. A later OCR rerun will only refresh its own untouched placeholder; it will never overwrite a note containing human-curated text.

Only the reviewed final note is suitable for later extraction. Preserve source attribution and distinguish a source’s expression from a verified fact or original quotation.

`manifest.json` records a basename-only source reference, files, run timestamp, engine, confidence summary, and relative paths for each layer. Generated output never exposes absolute local paths by default.

Use `--title "Your title"` when a meaningful title is known; otherwise rename the placeholder during review.

## Quality recovery

If OCR is weak:

1. Re-stage the original image rather than re-OCRing a compressed screenshot.
2. Crop the quote card or large text region and rerun it.
3. Try high-contrast grayscale/upscaling in an image editor, keeping the original alongside it.
4. For difficult layouts, use a vision review of the image and compare it with the draft.
5. Reserve the old CRAFT notebook for cases where detecting the text region—not reading it—is the failure.

## Validation checklist

- [ ] Local media was acquired through one of the three documented modes.
- [ ] `source.md`/manifest preserves known provenance, rights/attribution uncertainty, and acquisition context.
- [ ] Image/frame files are named in true order.
- [ ] `ocr.json` and `ocr-draft.md` exist and have the same number of images/frames as input files.
- [ ] All low-confidence lines and visual ambiguities were checked against the media.
- [ ] Only reviewed, attributed material enters the main knowledge system.

## Limitations

The final Markdown is a **reference note**, not a print-layout reproduction of the original graphics. Optimise it for readable retrieval, source traceability, and easy correction in Obsidian; do not spend effort mirroring poster typography, decorative spacing, or precise visual line breaks.

OCR cannot reliably infer intended punctuation, typography, missing images/frames, authorship, rights, attribution, or whether a quote is true. Platforms—including Instagram—can require login and change their delivery behaviour; staging an authorised local media export is the most durable route.
