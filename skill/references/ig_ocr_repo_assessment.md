# Assessment: `ScrPzz/IG_ocr`

Repository examined: <https://github.com/ScrPzz/IG_ocr> (public GitHub repository).

## What it is

A fork of CRAFT-pytorch adapted as an Instagram-post OCR experiment. Its stated pipeline is:

1. CRAFT detects text bounding boxes.
2. MeanShift clustering joins/expands boxes to isolate text areas.
3. Tesseract and PaddleOCR are benchmarked to transcribe the isolated regions.
4. Future/unfinished ideas include background classification and CLIP analysis.

The project documents an interactive notebook (`boxes.ipynb`) as the usage path: edit the `_IMAGE` path and run the notebook.

## Why it is not the default runtime

The repository's pinned requirements are:

```text
torch==0.4.1.post2
torchvision==0.2.1
opencv-python==3.4.2.17
scikit-image==0.14.2
scipy==1.1.0
```

Those versions are from an older Python/PyTorch ecosystem and are likely to be awkward or unsafe to install beside a modern environment. The checked-in `test.py` expects external CRAFT weights at `weights/craft_mlt_25k.pth` and defaults to CUDA. It only detects/saves text regions and bounding-box metadata; the notebook carries the OCR integration.

## Practical recommendation

Use a current OCR engine for day-to-day local image batches. The bundled `ocr_batch.py` uses `rapidocr-onnxruntime`, avoiding the legacy dependency pinning and a separate system Tesseract requirement. Retain the repository as a reference if a future batch needs CRAFT region detection or a visual comparison of detected text boxes.

## Attribution and safety

The repository itself is publicly available and says it is forked from CRAFT-pytorch. That does not grant rights to republish the Instagram images or quote graphics processed with it. Preserve the original post URL and creator where known.