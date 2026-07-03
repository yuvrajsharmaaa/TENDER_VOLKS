# Architecture Overview

This document describes the design principles, pipeline mechanics, and integration interface for the Tender OCR and Extraction service.

---

## Architecture Design Principles

To maintain scalability and operational visibility, the system enforces a strict boundary between layers:
- **Asynchronous Execution:** Compute-intensive OCR tasks run out-of-band in Celery background workers using Redis as the message broker.
- **Relational Integrity:** Multi-tenant jobs, documents, and extracted field rows are cataloged in PostgreSQL using unique UUID primary keys.
- **Object Storage Independence:** Original uploads and processed page-level png/json files are stored in MinIO/S3 object storage, keeping the SQL database lightweight.
- **Clean Naming Conventions:** Naming models and variables conform to canonical snake_case terms:
  - `tender_project`: The project encapsulating all bid files.
  - `document`: The individual file (e.g. NIT, BOQ).
  - `job`: The asynchronous processing state.
  - `ocr_result`: Page-level text and layout bounding boxes.
  - `extracted_field`: Canonical business fields containing trace metadata.

---

## OCR and Layout Parsing Pipeline

The pipeline is visual-first, preserving spatial hierarchy and reading sequence:
1. **PyMuPDF Extraction:** Renders PDF pages to high-resolution PNG images.
2. **PaddleOCR:** Identifies individual line-level text blocks and coordinate grids.
3. **PP-StructureV3:** Detects layout boundaries (paragraphs, headings) and tables.
4. **Spatial Mapping:** Assigns text lines to layout regions based on center-point coordinate containment, sorting text sequences by reading order index.

---

## Extraction Engine

A deterministic parser (`FieldExtractor`) evaluates page layouts:
- **Anchor Keywords:** Scans for English and Hindi keyword anchors.
- **Table Row Groupings:** Groups cells horizontally within coordinates ranges to link key labels to values in table fields (e.g. EMD, fees, estimated cost).
- **Euclidean Proximity:** Resolves vertical and horizontal pairings when values sit adjacent to or below labels.
- **Scoring and Fallbacks:** Computes confidence based on format match strength, spatial proximity, and table layout structures. Low-confidence fields trigger targeted LLM prompt fallbacks.
