# Media OCR

This package contains a local-first workflow for extracting text from local images, image sequences, text-on-video, and optional local audio/video speech review. It processes staged local media only; it does not fetch URLs or acquire content from any platform. Instagram carousels and Reels are examples of source formats that an operator may stage separately.

## Package contents

- `skill/SKILL.md` — operational workflow, acquisition boundary, provenance, and review guidance;
- `skill/scripts/ocr_batch.py` — local image-sequence OCR and three-layer output generation;
- `skill/scripts/ocr_video.py` — local frame sampling for text-on-video sources;
- `skill/scripts/transcribe_audio.py` — optional local faster-whisper speech-to-text review pass;
- `skill/scripts/test_ocr_safety.py` — regression tests for safe, repeatable outputs;
- `skill/references/ig_ocr_repo_assessment.md` — assessment of an Instagram-specific CRAFT-based reference project;
- `docs/requirements.txt` — base and optional dependencies.

## Acquisition Contract

1. **Manual local import is the default.** Import local files the operator already holds or is authorised to process, and record available provenance.
2. **User-directed browser capture is optional.** It is limited to specific authorised items or small batches and must not bypass access controls, login walls, private-account restrictions, rate limits, or platform protections.
3. **Automated collection is not included.** This package has no downloader, crawler, scraper, or URL-fetching component. It needs a separate approved design.

The contract protects operator agency by leaving source selection and authorisation with the operator. It keeps provenance attached to staged material, reduces privacy exposure, and avoids indiscriminate collection. It is transparent about scope rather than attempting to persuade users to collect more content.

## Provenance and review model

Acquisition stages local media and its provenance; Media OCR processes only those local files. Record, at minimum: a local identifier, source URL/location when known, creator/publisher/account identifier when known, acquisition mode and date, relevant visible context, and rights/licence/attribution uncertainty. Missing information remains missing; URLs, handles, and OCR output do not establish rights or authorship.

Every run separates three layers:

1. **Evidence:** raw and enriched machine-readable observations. Nothing is silently deleted.
2. **Review draft:** frame/image-ordered Markdown for checking against the source.
3. **Final reference note:** clean, deduplicated, attributed text suitable for later use only after review.

Speech transcription is optional and produces timestamped evidence. It supports review; it does not silently replace OCR or establish speaker attribution by itself.

This package is depersonalised for publication or transfer. Replace generic examples with a local user or workspace path only at runtime; generated artifacts use basenames and relative links so they do not expose absolute local paths by default. Do not put personal paths back into the published skill.
