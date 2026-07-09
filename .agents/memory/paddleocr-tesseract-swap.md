---
name: PaddleOCR → Tesseract swap
description: Why PaddleOCR can't be installed in this Replit env and what replaced it.
---

## Rule
Use `pytesseract` (wrapping the `tesseract` Nix package) as the OCR engine. Do not attempt to install `paddleocr`, `paddlepaddle`, or `imgaug`.

**Why:** `imgaug 0.4.0` is permanently blocked by Replit's package firewall. No newer version exists. PaddleOCR requires imgaug, so the entire paddle stack is uninstallable in this environment. The swap preserves the exact `TextBlock`/`LayoutRegion`/`PageResult` contracts consumed downstream, so no other code needed changing.

**How to apply:** If OCR needs to be re-evaluated or upgraded, look at `ocr/ocr_engine.py` and `ocr/layout/layout_detector.py`. The Nix package `tesseract` is already listed in the environment. In the Docker image (`backend/Dockerfile`), `tesseract-ocr` must be in the apt install list — it was missing originally and has since been added.
