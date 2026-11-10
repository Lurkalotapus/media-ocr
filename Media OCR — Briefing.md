## Media OCR — plain-English briefing

**Purpose and activation.** Use Media OCR when you have local images, an image sequence, or video containing text that you want to turn into a reviewable corpus. Its OCR output is a draft, not an authority. [Source: lines 3, 10]

**Acquisition.** Media must be acquired separately. The workflow itself does not download or scrape it; manual import is the default, with limited user-directed capture described separately. [Lines 12–22]

**Dependencies.** The documented local setup uses a dedicated environment with RapidOCR, ONNX Runtime and Pillow. Video sampling adds `imageio-ffmpeg`; speech transcription with `faster-whisper` is optional. [Lines 75–85, 117–122, 143–150]

**Workflow.** Stage the media and provenance, preflight and run OCR, compare the draft against the originals, then create a reviewed final note. [Lines 101–115]

**Outputs.** The workflow separates raw and enriched machine-readable evidence, a review draft, and an initially blank final reference-note template. [Lines 165–175, 185–198]

**Risks and limitations.** Check wording, attribution and uncertain text against the original media. OCR cannot reliably establish missing content, authorship, rights or whether a quotation is true; repeated text is not automatically a watermark. [Lines 183, 225–229]

**Unverified:** The document describes the workflow; this briefing does not establish that the scripts or dependencies currently work on your machine.

Source: `/mnt/Echo/AI/Projects/media-ocr/skill/SKILL.md`. It was treated as document data; none of its commands were executed.
