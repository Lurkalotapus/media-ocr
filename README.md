# Media OCR

Media OCR is a local-first, review-oriented workflow for extracting text from local images, image sequences, and text-on-video. It produces three distinct layers: raw/enriched evidence, a Markdown review draft, and a human-reviewed final reference note. Instagram is one possible source of staged media; it is not a special integration.

## Agent-assisted use

Media OCR works from the command line, but is designed to be especially useful
when paired with an agent that can follow `skill/SKILL.md`.

An agent can help stage a repeatable workflow, run preflight checks, process
local media, preserve provenance records, and prepare review drafts. It must
not independently acquire media, infer missing rights or attribution, or treat
OCR output as verified knowledge.

A human operator remains responsible for source selection, authorisation,
provenance, review, and the decision to promote material into a final note.

## Scope and acquisition boundary

Media OCR processes **only local files**. It does not fetch URLs, log into platforms, download media, or collect content. Acquisition is a separate stage that supplies local media and its provenance.

### Acquisition Contract

There are exactly three acquisition modes:

1. **Manual local import (default).** The operator imports files they already hold or are authorised to process, then records available provenance.
2. **User-directed browser capture (optional).** For specific authorised items or small batches, an operator may use a browser to capture media they can legitimately view. This must not bypass access controls, login walls, private-account restrictions, rate limits, or other platform protections.
3. **Automated collection (not included).** Media OCR contains no downloader, crawler, scraper, or URL-fetching capability. Automated collection requires a separate approved design.

This separation preserves operator agency: the operator chooses each item and remains accountable for authorisation. It also keeps provenance with the staged file, limits unnecessary exposure of personal or platform data, and avoids indiscriminate collection. These are explicit operating constraints, not a claim about what any source permits.

## Provenance and review

At intake, record the minimum available provenance fields in `source.md` or an equivalent local record:

- local file or staged-item identifier;
- source URL or source location, if known;
- creator, publisher, or account identifier, if shown or known;
- capture/import date and acquisition mode;
- visible date, caption, context, or notes relevant to interpretation; and
- rights, licence, attribution, and uncertainty notes.

Do not invent missing fields. A URL, handle, visible credit, or OCR result does not establish copyright ownership, permission, authorship, or the accuracy of a quoted claim. Retain uncertainty for later review.

Keep the layers separate:

1. **Evidence:** raw and enriched machine-readable observations; nothing is silently deleted.
2. **Review draft:** image/frame-ordered Markdown checked against the source media.
3. **Final reference note:** clean, deduplicated, attributed text only after human review.

## Requirements

- Python 3.14 (validated against the pinned dependency set)
- Local image or video files that the operator is authorised to process

Install the base runtime:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r docs/requirements.txt
```

`faster-whisper` is optional; install it only when speech-to-text review is needed. See `skill/SKILL.md` for the operational workflow, provenance guidance, constraints, and video instructions.

## Test

```bash
.venv/bin/python -m unittest discover -s skill/scripts -p 'test_*.py' -v
```

Generated outputs use file names and relative references by default, not absolute local paths. Do not treat OCR output as verified text: compare it with the original media before replacing the final-note placeholder.

## Project documents

- `CONTRIBUTING.md` — contribution and test expectations
- `SECURITY.md` — vulnerability reporting guidance
- `LICENSE` — Apache License 2.0
- `NOTICE` — copyright and attribution notice
- `docs/README.md` — package overview

Copyright 2026 Lurk & Sophia. Released under Apache License 2.0; see `LICENSE`.
