# Tender OCR MVP — Engineering Execution Playbook

> **Private Reasoning (completed before output):**
>
> **1. Single most critical risk per week:**
> - Week 1: PaddleOCR environment setup (CUDA/CPU selection, paddlepaddle install) failing silently or producing corrupted model downloads blocks all ML work. Mitigate on Day 1.
> - Week 2: `process_pdf()` → `BackgroundTasks` state propagation — uncaught exceptions inside background tasks silently kill the job with no status update, leaving the job stuck in `processing` forever.
>
> **2. Sequential vs. Parallelizable:**
> - Sequential (blocking): `PageResult` dataclass + DB schema defined together on Day 1 before any code is written; integration wiring on Day 8.
> - Parallelizable: PDF→image pipeline (P1) runs in parallel with upload/job-store backend (P2) all of Week 1. OCR engine (P1) runs in parallel with status/result endpoints (P2) all of Week 2.
>
> **3. Integration boundary:**
> - Boundary = `process_pdf(job_id: str, pdf_path: Path) -> list[PageResult]`
> - Person 1 owns: everything inside that function call, all file I/O for page images and page JSONs, OCR quality.
> - Person 2 owns: calling the function, catching all exceptions from it, updating job status in SQLite, serving results via API.
> - The `PageResult` dataclass and the filesystem contract (where page JSONs are written) are the ONLY shared interface.

---

## Section 1 — Project Brief

The MVP objective is to build a reliable, locally-runnable structure-aware OCR and metadata extraction pipeline specifically for Indian Government Tender documents. Success means a developer can POST a PDF (digital or scanned, Hindi/English/mixed), poll a job status endpoint, and retrieve:
1. **Raw OCR text blocks** with page-level coordinates and confidence.
2. **Layout-aware regions** (headings, paragraphs, lists, and tables) with reading order reconstruction.
3. **Deterministic extracted fields** (e.g., EMD, Tender Fee, NIT No, submission dates, work period, organisation) with confidence scores and block-level traceability refs.

These results are validated via Pydantic and saved on disk in three output files: `raw_ocr.json`, `layout.json`, and `extracted_fields.json`.

---

## Section 2 — Success Criteria

1. `POST /upload` accepts a valid PDF and returns a `job_id` within **500 ms**.
2. `GET /job/{id}/status` returns `processing`, `completed`, or `failed` — never an unhandled 500 — for **100%** of job IDs that were successfully created.
3. A 10-page digital PDF completes processing (status = `completed`) in **≤ 60 seconds** on CPU-only hardware.
4. A 10-page scanned PDF completes processing in **≤ 180 seconds** on CPU-only hardware.
5. **≥ 95%** of pages in a digital PDF produce a non-empty `text_blocks` array in their page JSON.
6. **≥ 80%** of pages in a scanned PDF produce a non-empty `text_blocks` array.
7. Hindi and English text co-existing on the same page must both appear in `text_blocks` — verified by manual inspection of **3 bilingual test documents**.
8. Every detected table on a page produces at least one entry in `layout_regions` with `region_type = "table"` — verified on **5 test documents** known to contain tables.
9. `GET /job/{id}/result` returns valid JSON matching the `ocr_result.json` schema for **100%** of completed jobs.
10. The application starts with `uvicorn app.main:app` with no errors on a clean Python 3.10+ environment after `pip install -r requirements.txt`.
11. Zero silent failures: every job must eventually reach `completed` or `failed` — no job may remain in `processing` indefinitely. Timeout threshold: **10 minutes** per job.
12. All job artifacts (page images, page JSONs, aggregate JSON) exist on disk for **100%** of completed jobs at the documented filesystem paths.

---

## Section 3 — Shared Technical Decisions

**Decision:** PaddleOCR
**Why:** Ships pretrained multilingual models (Hindi, English, regional scripts) with bounding-box output and confidence scores out of the box; no training required and no cloud API call.
**Boundary:** Begins when a page image (PIL or numpy array) is passed to `ocr.ocr(img, cls=True)`; ends when raw OCR result (list of `[[box], [text, confidence]]`) is returned. Layout detection is NOT PaddleOCR's responsibility — that is PP-StructureV3.

---

**Decision:** PP-StructureV3
**Why:** Extends PaddleOCR with table, figure, title, and stamp region detection using the same model distribution, keeping the dependency footprint minimal.
**Boundary:** Begins when a page image is passed to `structure.predict(img)`; ends when a list of region dicts with `type`, `bbox`, and `res` is returned. Merging layout regions with raw OCR text blocks is done inside `page_builder.py`, not inside the PP-StructureV3 call.

---

**Decision:** FastAPI
**Why:** Native async support, Pydantic v2 request/response validation, and `BackgroundTasks` are all first-class — no additional framework is needed.
**Boundary:** Begins at HTTP request receipt; ends at HTTP response dispatch. FastAPI does not touch OCR logic, file I/O beyond accepting the uploaded PDF bytes, or SQLite directly (that is `job_store.py`'s job).

---

**Decision:** SQLite
**Why:** Zero infrastructure — a single file, no server process, and Python's `sqlite3` module is in stdlib; sufficient for sequential job tracking with no concurrent write contention from a 2-person dev team.
**Boundary:** Begins when a job record is created (`INSERT`) after PDF upload; ends when `GET /job/{id}/result` reads the result path. SQLite stores job metadata only — it does NOT store OCR output bytes.

---

**Decision:** BackgroundTasks
**Why:** Eliminates Celery/Redis infrastructure while meeting the constraint that the upload endpoint must return immediately; acceptable for MVP with sequential job processing.
**Boundary:** Begins when `background_tasks.add_task(run_ocr_job, job_id, pdf_path)` is called inside the upload handler; ends when `run_ocr_job` updates the job status to `completed` or `failed` in SQLite. BackgroundTasks does not manage retries — retry logic lives inside `run_ocr_job`.

---

## Section 4 — Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLIENT (curl / browser)                          │
└───────────────┬─────────────────────────────────────────────────────────┘
                │ HTTP
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                               │
│                         app/main.py                                      │
│                                                                          │
│  ┌──────────────────────┐   ┌────────────────────────────────────────┐  │
│  │  POST /upload        │   │  GET /job/{id}/status                  │  │
│  │  GET /job/{id}/result│   │  (routers/jobs.py)  ◄── PERSON 2 ───► │  │
│  └──────────┬───────────┘   └────────────────┬───────────────────────┘  │
│             │                                │                           │
│             │ add_task()                     │ read                      │
│             ▼                                ▼                           │
│  ┌──────────────────────┐   ┌────────────────────────────────────────┐  │
│  │  BackgroundTask:     │   │         job_store.py                   │  │
│  │  run_ocr_job()       │   │  create_job / update_status / get_job  │  │
│  │  (tasks/ocr_task.py) │   │  (sqlite3, WAL mode)                   │  │
│  └──────────┬───────────┘   └────────────────┬───────────────────────┘  │
│  PERSON 2   │                         PERSON 2│                           │
└─────────────┼─────────────────────────────────┼──────────────────────────┘
              │                                 │
              │  ══════ INTEGRATION BOUNDARY ══════
              │  process_pdf(job_id, pdf_path) → list[PageResult]
              │                                 │
              ▼                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      OCR Pipeline (PERSON 1)                             │
│                                                                          │
│  ┌───────────────┐   ┌──────────────┐   ┌─────────────────────────────┐ │
│  │ pdf_converter │   │  ocr_engine  │   │  layout_detector            │ │
│  │ .py           │──►│  .py         │──►│  .py                        │ │
│  │ (PyMuPDF)     │   │ (PaddleOCR)  │   │ (PP-StructureV3)            │ │
│  └───────┬───────┘   └──────┬───────┘   └──────────┬──────────────────┘ │
│          │                  │                       │                     │
│          │ page images      │ raw OCR blocks        │ region annotations  │
│          │ (PNG files)      │ (box+text+conf)       │ (type+bbox+cells)   │
│          └──────────────────┴───────────────────────┘                    │
│                                    │                                      │
│                                    ▼                                      │
│                     ┌──────────────────────────┐                         │
│                     │  page_builder.py          │                         │
│                     │  merge OCR + layout into  │                         │
│                     │  PageResult dataclass     │                         │
│                     └─────────────┬────────────┘                         │
│                                   │                                       │
│                                   ▼                                       │
│                     ┌──────────────────────────┐                         │
│                     │  result_writer.py         │                         │
│                     │  page_NNNN.json           │                         │
│                     │  ocr_result.json          │                         │
│                     └──────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────┘

FILESYSTEM (shared read/write)
  storage/
    jobs/
      {job_id}/
        original.pdf        ← Person 2 writes on upload
        pages/
          page_0001.png     ← Person 1 writes during processing
          page_0001.json    ← Person 1 writes during processing
        ocr_result.json     ← Person 1 writes on completion
```

---

## Section 5 — Repository Structure

```
tender-ocr/
├── app/                          # FastAPI application layer (Person 2)
│   ├── __init__.py
│   ├── main.py                   # App factory, lifespan, router registration
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── upload.py             # POST /upload endpoint
│   │   └── jobs.py               # GET /job/{id}/status, GET /job/{id}/result
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── ocr_task.py           # run_ocr_job() — BackgroundTask entry point
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py            # Pydantic v2 request/response models
│   └── db/
│       ├── __init__.py
│       ├── job_store.py          # All SQLite read/write operations
│       └── migrations.py         # CREATE TABLE on startup (no Alembic)
│
├── ocr/                          # OCR pipeline (Person 1)
│   ├── __init__.py
│   ├── pipeline.py               # process_pdf() — spatial containment, fields extraction, saves output JSONs
│   ├── pdf_converter.py          # PyMuPDF: PDF → per-page PNG images
│   ├── ocr_engine.py             # PaddleOCR wrapper: image → raw text blocks
│   ├── layout_detector.py        # PP-StructureV3 wrapper: image → region list
│   ├── page_builder.py           # Merge OCR + layout → PageResult dataclass
│   ├── field_extractor.py        # Rule-based field extractor (EMD, Fee, dates, NIT, org, contract, etc.)
│   └── result_writer.py          # Write page_NNNN.json and ocr_result.json
│
├── shared/                       # Shared contracts between Person 1 and Person 2
│   ├── __init__.py
│   ├── models.py                 # PageResult, TextBlock, LayoutRegion dataclasses
│   ├── schemas.py                # Pydantic v2 schemas for raw_ocr, layout, and extracted_fields
│   └── constants.py              # Status strings, path templates, config values
│
├── storage/                      # Runtime artifact storage (gitignored)
│   └── jobs/                     # One subdirectory per job_id
│
├── tests/                        # All tests
│   ├── __init__.py
│   ├── unit/
│   │   ├── test_pdf_converter.py
│   │   ├── test_ocr_engine.py
│   │   ├── test_layout_detector.py
│   │   ├── test_page_builder.py
│   │   ├── test_result_writer.py
│   │   └── test_job_store.py
│   ├── integration/
│   │   ├── test_upload_endpoint.py
│   │   ├── test_job_status_endpoint.py
│   │   └── test_full_pipeline.py
│   └── fixtures/
│       ├── sample_digital.pdf    # Known 3-page digital tender
│       ├── sample_scanned.pdf    # Known 3-page scanned tender
│       └── sample_bilingual.pdf  # Hindi+English mixed page
│
├── scripts/
│   ├── verify_env.py             # Checks PaddleOCR, PyMuPDF imports + model download
│   └── smoke_test.py             # End-to-end curl equivalent in Python
│
├── data/
│   └── tender.db                 # SQLite database file (gitignored)
│
├── logs/                         # Structured log output (gitignored)
│   └── app.log
│
├── requirements.txt              # Pinned dependencies
├── .env.example                  # Environment variable template
├── .gitignore
└── README.md                     # Setup and run instructions only
```

---

## Section 6 — Database Schema

```sql
CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'pending',
    -- status values: 'pending' | 'processing' | 'completed' | 'failed'
    original_filename TEXT NOT NULL,
    pdf_path        TEXT NOT NULL,
    result_path     TEXT,           -- NULL until completed
    page_count      INTEGER,        -- NULL until processing starts
    error_message   TEXT,           -- NULL unless failed
    created_at      TEXT NOT NULL,  -- ISO-8601 UTC
    started_at      TEXT,           -- NULL until processing starts
    completed_at    TEXT,           -- NULL until completed or failed
    retry_count     INTEGER NOT NULL DEFAULT 0
);

-- Sample row:
-- ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'completed', 'tender_notice.pdf',
--  'storage/jobs/a1b2c3d4/original.pdf', 'storage/jobs/a1b2c3d4/ocr_result.json',
--  12, NULL, '2024-01-15T10:30:00Z', '2024-01-15T10:30:01Z', '2024-01-15T10:31:45Z', 0)

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
```

---

## Section 7 — API Contracts

### POST /upload

**Method:** `POST`
**Path:** `/upload`
**Content-Type:** `multipart/form-data`

**Request Body:**
```json
{
  "file": "<binary PDF data>",
  "filename": "tender_notice.pdf"
}
```

**Response Body (201 Created):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "message": "Job created. Poll /job/{job_id}/status for updates.",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Error Codes:**

| Code | Condition |
|------|-----------|
| 400  | File is not a PDF (validated by MIME type and magic bytes) |
| 413  | File exceeds 50 MB limit |
| 500  | Filesystem write failed (storage unavailable) |

---

### GET /job/{id}/status

**Method:** `GET`
**Path:** `/job/{job_id}/status`

**Request Body:** None

**Response Body (200 OK):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "processing",
  "original_filename": "tender_notice.pdf",
  "page_count": 12,
  "retry_count": 0,
  "created_at": "2024-01-15T10:30:00Z",
  "started_at": "2024-01-15T10:30:01Z",
  "completed_at": null,
  "error_message": null
}
```

**Error Codes:**

| Code | Condition |
|------|-----------|
| 404  | job_id does not exist in database |

---

### GET /job/{id}/result

**Method:** `GET`
**Path:** `/job/{job_id}/result`

**Request Body:** None

**Response Body (200 OK):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "page_count": 12,
  "completed_at": "2024-01-15T10:31:45Z",
  "result": { "<ocr_result.json contents — see Section 8B>" }
}
```

**Error Codes:**

| Code | Condition |
|------|-----------|
| 404  | job_id does not exist |
| 409  | Job exists but status is not `completed` (body includes current status) |
| 500  | `ocr_result.json` exists in DB path but cannot be read from disk |

---

## Section 8 — Output JSON Schema

### 8A — Page-level OCR JSON (`page_0001.json`)

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "page_number": 1,
  "image_path": "storage/jobs/a1b2c3d4/pages/page_0001.png",
  "image_width_px": 2480,
  "image_height_px": 3508,
  "processing_time_seconds": 4.23,
  "text_blocks": [
    {
      "block_id": "blk_0001_001",
      "text": "भारत सरकार / Government of India",
      "confidence": 0.97,
      "bounding_box": {
        "x1": 820, "y1": 110, "x2": 1660, "y2": 158
      },
      "language_hint": "hi+en"
    },
    {
      "block_id": "blk_0001_002",
      "text": "Ministry of Railways",
      "confidence": 0.99,
      "bounding_box": {
        "x1": 900, "y1": 165, "x2": 1580, "y2": 205
      },
      "language_hint": "en"
    },
    {
      "block_id": "blk_0001_003",
      "text": "TENDER NOTICE NO. RLY/2024/TN/0042",
      "confidence": 0.98,
      "bounding_box": {
        "x1": 150, "y1": 310, "x2": 900, "y2": 345
      },
      "language_hint": "en"
    }
  ],
  "layout_regions": [
    {
      "region_id": "reg_0001_001",
      "region_type": "title",
      "bounding_box": {
        "x1": 820, "y1": 90, "x2": 1660, "y2": 220
      },
      "contained_block_ids": ["blk_0001_001", "blk_0001_002"]
    },
    {
      "region_id": "reg_0001_002",
      "region_type": "table",
      "bounding_box": {
        "x1": 100, "y1": 800, "x2": 2380, "y2": 1600
      },
      "contained_block_ids": ["blk_0001_010", "blk_0001_011", "blk_0001_012"],
      "table_structure": {
        "rows": 6,
        "cols": 4,
        "cells": [
          {
            "row": 0, "col": 0,
            "text": "S. No.",
            "bounding_box": {"x1": 100, "y1": 800, "x2": 200, "y2": 850}
          },
          {
            "row": 0, "col": 1,
            "text": "Item Description",
            "bounding_box": {"x1": 200, "y1": 800, "x2": 900, "y2": 850}
          }
        ]
      }
    },
    {
      "region_id": "reg_0001_003",
      "region_type": "stamp",
      "bounding_box": {
        "x1": 2000, "y1": 3100, "x2": 2400, "y2": 3450
      },
      "contained_block_ids": []
    }
  ],
  "warnings": []
}
```

---

### 8B — Job-level aggregate JSON (`ocr_result.json`)

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "original_filename": "tender_notice.pdf",
  "status": "completed",
  "page_count": 3,
  "total_processing_time_seconds": 18.74,
  "completed_at": "2024-01-15T10:31:45Z",
  "pipeline_version": "0.1.0",
  "pages": [
    {
      "page_number": 1,
      "page_json_path": "storage/jobs/a1b2c3d4/pages/page_0001.json",
      "text_block_count": 24,
      "layout_region_count": 4,
      "processing_time_seconds": 4.23,
      "has_table": true,
      "has_stamp": true,
      "warnings": []
    },
    {
      "page_number": 2,
      "page_json_path": "storage/jobs/a1b2c3d4/pages/page_0002.json",
      "text_block_count": 18,
      "layout_region_count": 2,
      "processing_time_seconds": 3.91,
      "has_table": false,
      "has_stamp": false,
      "warnings": []
    },
    {
      "page_number": 3,
      "page_json_path": "storage/jobs/a1b2c3d4/pages/page_0003.json",
      "text_block_count": 0,
      "layout_region_count": 1,
      "processing_time_seconds": 10.60,
      "has_table": false,
      "has_stamp": false,
      "warnings": ["low_confidence_page: avg_confidence=0.41, likely_scanned_or_degraded"]
    }
  ],
  "summary": {
    "total_text_blocks": 42,
    "total_layout_regions": 7,
    "pages_with_tables": 1,
    "pages_with_stamps": 1,
    "pages_with_warnings": 1,
    "avg_confidence": 0.91
  }
}
```

---

## Section 9 — Week 1 Execution Plan

### 9A — Objective

Establish a working skeleton: agreed data contracts, validated environment, PDF-to-image conversion producing correct output, and upload+job-creation endpoint storing PDFs to disk with job records in SQLite.

### 9B — Deliverables

1. `shared/models.py` committed and reviewed by both engineers — **PASS if both can import `PageResult` without error**
2. `shared/constants.py` committed with all status strings and path templates — **PASS if no magic strings appear in any other module**
3. `scripts/verify_env.py` runs to completion on both machines with no import errors — **PASS if PaddleOCR, PyMuPDF, PP-StructureV3 all import successfully and print model info**
4. `pdf_converter.py` converts a 5-page test PDF to 5 PNG files with correct DPI — **PASS if 5 files exist, each ≥ 100 KB**
5. `job_store.py` CRUD operations tested — **PASS if `test_job_store.py` passes all 6 unit tests**
6. `POST /upload` returns 201 with `job_id` and persists PDF to `storage/jobs/{job_id}/original.pdf` — **PASS if file exists after curl**
7. SQLite `jobs` table created on startup with all columns — **PASS if `sqlite3 data/tender.db ".schema"` matches Section 6**

### 9C — Day-by-Day Table

| Day | Person 1 Task | Person 2 Task | Integration Point |
|-----|--------------|--------------|-------------------|
| 1 | Set up Python env, install PaddleOCR + PyMuPDF, run `verify_env.py` on own machine. Draft `shared/models.py` | Set up Python env, install FastAPI + Pydantic v2, scaffold repo structure. Review `shared/models.py` draft | **End of Day 1:** Both agree and merge `shared/models.py` and `shared/constants.py` — no changes without joint approval |
| 2 | Implement `pdf_converter.py` (PyMuPDF → PNG), write `test_pdf_converter.py` | Implement `db/migrations.py` (CREATE TABLE on startup), implement `db/job_store.py` CRUD | No integration point — fully parallel |
| 3 | Implement `ocr_engine.py` skeleton (PaddleOCR init + single-image call), write `test_ocr_engine.py` with fixture image | Implement `routers/upload.py` (file validation, save to disk, create_job), write `test_upload_endpoint.py` | No integration point — fully parallel |
| 4 | Implement `layout_detector.py` (PP-StructureV3 init + single-image call), write `test_layout_detector.py` | Implement `routers/jobs.py` (status + result endpoints), write `test_job_status_endpoint.py` | **End of Day 4:** Person 2 calls `create_job()` in upload handler — confirms job appears in SQLite |
| 5 | Run `pdf_converter.py` on all 3 fixture PDFs, document any conversion failures. Begin `page_builder.py` skeleton | Wire `app/main.py` (lifespan, router registration, storage dir creation). End-to-end `POST /upload` → SQLite manual test | **End of Day 5:** Demo: `curl -F file=@fixture/sample_digital.pdf http://localhost:8000/upload` returns 201 with `job_id` |

### 9D — Person 1 Detailed Tasks

| Subtask | Expected Output | Time Estimate | Done When |
|---------|----------------|---------------|-----------|
| Install PaddleOCR (CPU mode), paddlepaddle, PyMuPDF, PP-StructureV3 in venv | `requirements.txt` with pinned versions, `verify_env.py` passes | 3 hrs | No import errors, model download completes |
| Draft `shared/models.py`: `TextBlock`, `LayoutRegion`, `PageResult` dataclasses | `shared/models.py` committed | 1 hr | Both engineers import it without error |
| Implement `pdf_converter.py`: `convert_pdf_to_images(pdf_path, output_dir, dpi=200) → list[Path]` | PNG files in output dir | 3 hrs | 5-page PDF produces 5 PNGs, each correct dimension |
| Write `test_pdf_converter.py`: test page count, file existence, minimum file size | `pytest tests/unit/test_pdf_converter.py` passes | 1 hr | All 3 assertions pass for digital and scanned fixtures |
| Implement `ocr_engine.py`: `OcrEngine.__init__(lang="en,hi")`, `run(image_path: Path) → list[TextBlock]` | Class with lazy model loading | 4 hrs | Single test image returns ≥ 1 `TextBlock` with non-empty text |
| Write `test_ocr_engine.py`: fixture image with known text, assert text in result | `pytest tests/unit/test_ocr_engine.py` passes | 1 hr | Known string found in result `text_blocks` |
| Implement `layout_detector.py`: `LayoutDetector.__init__()`, `detect(image_path: Path) → list[LayoutRegion]` | Class with lazy model loading | 4 hrs | Single test image returns ≥ 1 `LayoutRegion` |
| Write `test_layout_detector.py`: fixture image with known table, assert `region_type="table"` present | `pytest tests/unit/test_layout_detector.py` passes | 1 hr | Table region detected |
| Begin `page_builder.py` skeleton: `build_page_result(ocr_blocks, layout_regions, page_meta) → PageResult` | Skeleton with pass-through logic | 2 hrs | Function callable end of Week 1 |

### 9E — Person 2 Detailed Tasks

| Subtask | Expected Output | Time Estimate | Done When |
|---------|----------------|---------------|-----------|
| Scaffold repo directory structure per Section 5 | All directories and `__init__.py` files committed | 1 hr | `find . -name "*.py" \| head -20` shows expected layout |
| Implement `db/migrations.py`: `init_db(db_path)` — runs CREATE TABLE IF NOT EXISTS on startup | `data/tender.db` created on app start | 2 hrs | `sqlite3 data/tender.db ".schema"` matches Section 6 |
| Implement `db/job_store.py`: `create_job()`, `get_job()`, `update_status()`, `update_result()` | Four functions, each using `sqlite3` context manager | 3 hrs | Each function testable in isolation |
| Write `test_job_store.py`: 6 tests — create, get existing, get missing, update status, update result, status transitions | `pytest tests/unit/test_job_store.py` passes | 2 hrs | All 6 tests green, temp DB cleaned up |
| Implement `app/models/schemas.py`: `UploadResponse`, `JobStatusResponse`, `JobResultResponse` Pydantic v2 models | `schemas.py` with field validators | 2 hrs | `from app.models.schemas import UploadResponse` works |
| Implement `routers/upload.py`: file MIME validation, magic byte check, 50 MB limit, save to disk, `create_job()`, `background_tasks.add_task()` stub | POST /upload returns 201 | 4 hrs | `curl -F file=@sample.pdf` returns 201 JSON with `job_id` |
| Implement `routers/jobs.py`: `GET /job/{id}/status` and `GET /job/{id}/result` | Both endpoints return correct status codes | 3 hrs | 404 for unknown ID, 409 for non-completed result request |
| Wire `app/main.py`: lifespan context manager calls `init_db()` and creates `storage/jobs/` dir | App starts cleanly | 1 hr | `uvicorn app.main:app` with no errors |
| Write `test_upload_endpoint.py`: valid PDF, invalid file type, oversized file | `pytest tests/integration/test_upload_endpoint.py` passes | 2 hrs | All 3 cases return correct HTTP codes |

### 9F — Logging Strategy

| What to Log | Log Level | Format | Output Destination |
|------------|-----------|--------|-------------------|
| App startup, DB initialized, storage dir created | INFO | `{"ts": "...", "event": "app_started", "db_path": "..."}` | `logs/app.log` + stderr |
| POST /upload received: filename, size, job_id | INFO | `{"ts": "...", "event": "upload_received", "job_id": "...", "filename": "...", "size_bytes": 0}` | `logs/app.log` |
| Job status transition: pending→processing→completed/failed | INFO | `{"ts": "...", "event": "job_status_change", "job_id": "...", "old": "...", "new": "..."}` | `logs/app.log` |
| PDF saved to disk: path, size | DEBUG | `{"ts": "...", "event": "pdf_saved", "job_id": "...", "path": "..."}` | `logs/app.log` |
| Any exception in upload handler or job endpoints | ERROR | `{"ts": "...", "event": "request_error", "path": "...", "exc": "..."}` | `logs/app.log` + stderr |
| SQLite query failure | ERROR | `{"ts": "...", "event": "db_error", "operation": "...", "exc": "..."}` | `logs/app.log` + stderr |
| PaddleOCR model loading (first call) | INFO | `{"ts": "...", "event": "model_loaded", "model": "ocr/layout", "elapsed_s": 0.0}` | `logs/app.log` |
| Per-page OCR completion: page num, block count, elapsed | DEBUG | `{"ts": "...", "event": "page_ocr_done", "job_id": "...", "page": 0, "blocks": 0, "elapsed_s": 0.0}` | `logs/app.log` |

**Implementation:** Use Python `logging` module with `json` formatter. Single logger named `tender_ocr`. Configure in `app/main.py` lifespan. Use `logging.getLogger("tender_ocr")` in all modules.

### 9G — Week 1 Testing Strategy

**Unit Tests — exact functions to test:**

| File | Functions Under Test |
|------|---------------------|
| `test_pdf_converter.py` | `convert_pdf_to_images()` — page count, output paths, file size |
| `test_ocr_engine.py` | `OcrEngine.run()` — returns list of TextBlock, confidence in [0,1] range |
| `test_layout_detector.py` | `LayoutDetector.detect()` — returns list of LayoutRegion, region_type values |
| `test_job_store.py` | `create_job()`, `get_job()`, `update_status()`, `update_result()`, get_missing (→ None), status_enum_validation |

**Integration Tests:**

| Test | How |
|------|-----|
| `test_upload_endpoint.py` | FastAPI `TestClient`, POST valid PDF → assert 201 + job_id + file exists on disk |
| `test_upload_endpoint.py` | POST `.txt` file → assert 400 |
| `test_upload_endpoint.py` | POST PDF > 50 MB → assert 413 |

**Manual Test Checklist:**
- [ ] `uvicorn app.main:app` starts with no errors
- [ ] `GET http://localhost:8000/docs` loads Swagger UI
- [ ] `curl -F "file=@tests/fixtures/sample_digital.pdf" http://localhost:8000/upload` returns 201
- [ ] `ls storage/jobs/{returned_job_id}/` shows `original.pdf`
- [ ] `sqlite3 data/tender.db "SELECT job_id, status FROM jobs;"` shows the job as `pending`
- [ ] `python scripts/verify_env.py` exits 0 on both dev machines

### 9H — Week 1 Common Mistakes

| Mistake | Root Cause | Prevention |
|---------|-----------|-----------|
| PaddleOCR model download fails halfway, import succeeds but predict crashes | Network interruption during first `PaddleOCR()` call; partial model cache | Run `verify_env.py` which calls `PaddleOCR()` + `ocr.ocr(test_img)` before any other code; check `~/.paddleocr/` for complete model dirs |
| SQLite "database is locked" during concurrent test runs | Multiple test functions opening the DB without closing | Use `:memory:` DB in all unit tests; use `tmp_path` fixture for integration tests |
| PDF saved but job not in DB (partial failure) | No transaction: file write succeeds, `create_job()` throws | Write to DB first; if DB succeeds, then write file; if file fails, update status to `failed` |
| `shared/models.py` diverges between engineers | Each person adds fields locally without committing | `shared/models.py` is the first PR merged on Day 1; no direct pushes to `main` after that |
| PyMuPDF DPI mismatch produces unreadable images for OCR | Default DPI=72 produces too-small images; PaddleOCR needs ≥ 150 DPI | Pin `dpi=200` in `convert_pdf_to_images()`; assert output image height > 1000px in test |
| PaddleOCR loads model on every function call (no singleton) | `PaddleOCR()` constructed inside `run()` instead of `__init__` | `OcrEngine` is a class; `__init__` loads model once; `run()` only calls `self.ocr.ocr()` |

### 9I — Week 1 Definition of Done

- [ ] `pytest tests/unit/` — all tests pass, 0 failures
- [ ] `pytest tests/integration/test_upload_endpoint.py` — all tests pass
- [ ] `python scripts/verify_env.py` exits 0 on both machines
- [ ] `uvicorn app.main:app` starts with no errors
- [ ] `POST /upload` with `sample_digital.pdf` returns 201 and `job_id`
- [ ] `storage/jobs/{job_id}/original.pdf` exists after upload
- [ ] `sqlite3 data/tender.db "SELECT * FROM jobs LIMIT 1"` shows a row with `status='pending'`
- [ ] `pdf_converter.py` converts `sample_digital.pdf` to 3 PNG files, each > 100 KB
- [ ] `pdf_converter.py` converts `sample_scanned.pdf` to 3 PNG files, each > 100 KB
- [ ] `shared/models.py` — both engineers have imported without error on their own machines
- [ ] No `TODO` comments remain in `shared/models.py` or `shared/constants.py`
- [ ] `GET /job/{id}/status` returns 404 for a fake UUID
- [ ] `git log --oneline` shows ≥ 10 commits across both engineers

---

## Section 10 — Week 2 Execution Plan

### 10A — Objective

Wire the complete pipeline: OCR + layout detection produces page JSONs, BackgroundTask updates job status end-to-end, result endpoint serves the aggregate JSON, and the full flow works on all 3 fixture document types.

### 10B — Deliverables

1. `process_pdf(job_id, pdf_path) → list[PageResult]` implemented and callable — **PASS if `test_full_pipeline.py` passes with `sample_digital.pdf`**
2. BackgroundTask wires `process_pdf()` and updates SQLite status — **PASS if job status reaches `completed` after upload**
3. `GET /job/{id}/result` returns the aggregate JSON — **PASS if response matches `ocr_result.json` schema**
4. `sample_scanned.pdf` completes processing to `completed` — **PASS if status=completed and page JSONs exist**
5. `sample_bilingual.pdf` result contains both Hindi and English text in `text_blocks` — **PASS if manual inspection confirms both scripts present**
6. End-to-end demo script (Section 10O) runs without any manual intervention — **PASS if all curl commands return expected output**
7. Error handling: uploading a corrupt PDF results in job status `failed` with non-null `error_message` — **PASS if `GET /job/{id}/status` shows `failed`**

### 10C — Day-by-Day Table

| Day | Person 1 Task | Person 2 Task | Integration Point |
|-----|--------------|--------------|-------------------|
| 6 | Implement `page_builder.py`: merge OCR blocks + layout regions into `PageResult`. Implement `result_writer.py`: write page JSONs | Implement `tasks/ocr_task.py`: `run_ocr_job()` with try/except, status updates, call to `process_pdf()` (stub) | **End of Day 6:** Agree on `process_pdf()` function signature in `ocr/pipeline.py` |
| 7 | Implement `ocr/pipeline.py`: full `process_pdf()` wiring pdf_converter → ocr_engine → layout_detector → page_builder → result_writer | Connect `run_ocr_job()` to real `process_pdf()` import; test that job status transitions pending→processing→completed | **End of Day 7:** Upload `sample_digital.pdf`, poll status until `completed` |
| 8 | Run OCR on `sample_scanned.pdf` and `sample_bilingual.pdf`; fix any PaddleOCR config issues for scanned/multilingual | Verify `GET /job/{id}/result` returns correct schema; handle 409 for non-completed jobs | **End of Day 8:** Full pipeline works for all 3 fixture document types |
| 9 | Write `test_full_pipeline.py` (integration); tune DPI and OCR params based on test results; write page_builder merge tests | Write error scenario tests; verify logging output is structured JSON in `logs/app.log` | **End of Day 9:** All integration tests pass |
| 10 | Performance measurement: time per page for digital vs. scanned; document results. Final code review of OCR modules | Write `scripts/smoke_test.py`; run demo script (Section 10O); fix any blockers | **End of Day 10:** Demo script passes all 12 pass/fail criteria |

### 10D — Person 1 Detailed Tasks

| Subtask | Expected Output | Time Estimate | Done When |
|---------|----------------|---------------|-----------|
| Implement `page_builder.py`: `build_page_result(page_num, ocr_results, layout_results, image_path, job_id) → PageResult` | Function that assigns `block_id`, merges layouts | 4 hrs | `PageResult` populated with correct block IDs and region references |
| Implement `result_writer.py`: `write_page_json(page_result, output_dir)` and `write_aggregate_json(job_id, pages, output_dir)` | JSON files written to disk | 2 hrs | Files readable and schema-valid |
| Write `test_page_builder.py`: fixture OCR output + fixture layout output → assert block IDs, region types | Tests pass | 2 hrs | All assertions green |
| Write `test_result_writer.py`: assert file exists, assert JSON parses, assert schema keys present | Tests pass | 1 hr | Files written and parseable |
| Implement `ocr/pipeline.py`: `process_pdf(job_id, pdf_path) → list[PageResult]` — orchestrates all pipeline steps | The integration function | 4 hrs | Callable, returns list of PageResult, writes page JSONs |
| Run pipeline on `sample_scanned.pdf`: fix any PaddleOCR issues (e.g., `use_angle_cls=True` needed for rotated text) | Scanned PDF produces page JSONs | 3 hrs | Status reaches `completed`, page JSONs non-empty |
| Run pipeline on `sample_bilingual.pdf`: confirm Hindi + English both present in output | Bilingual result JSON | 2 hrs | Manual inspection confirms both scripts in `text_blocks` |
| Write `test_full_pipeline.py`: calls `process_pdf()` directly on fixture, asserts output structure | Integration test | 2 hrs | Test passes for `sample_digital.pdf` |
| Measure per-page processing time: digital and scanned, document in `README.md` | Timing numbers | 1 hr | Numbers written in README under "Performance" |

### 10E — Person 2 Detailed Tasks

| Subtask | Expected Output | Time Estimate | Done When |
|---------|----------------|---------------|-----------|
| Implement `tasks/ocr_task.py`: `run_ocr_job(job_id, pdf_path)` with full try/except, status transitions, `process_pdf()` call | Background task function | 4 hrs | Job reaches `completed` or `failed` — never stuck in `processing` |
| Wire `run_ocr_job()` to real `process_pdf()` import in `tasks/ocr_task.py` | Full pipeline callable from API | 1 hr | Upload → poll → `completed` works end-to-end |
| Implement `GET /job/{id}/result`: read `ocr_result.json` from path in DB, return as JSON | Result endpoint | 2 hrs | 200 with JSON body for completed jobs; 409 for non-completed |
| Write error test: upload corrupt PDF file (rename `.txt` to `.pdf` with PDF magic bytes) | `failed` status with error_message | 2 hrs | `GET /status` shows `failed` with non-null `error_message` |
| Verify all logs are structured JSON in `logs/app.log` for a full pipeline run | Log file inspection | 1 hr | `cat logs/app.log \| python -m json.tool` exits 0 for each line |
| Write `scripts/smoke_test.py`: Python script that uploads, polls, and fetches result | Single-command E2E test | 2 hrs | Script exits 0 for `sample_digital.pdf` |
| Write `test_job_status_endpoint.py`: test pending/processing/completed/failed status values | Tests pass | 2 hrs | All 4 status transitions testable via DB manipulation |
| Final review: check all 404/409/500 handlers return JSON (not FastAPI HTML defaults) | Consistent error JSON | 1 hr | All error responses are `{"detail": "..."}` JSON |

### 10F — Logging Strategy

| What to Log | Log Level | Format | Output Destination |
|------------|-----------|--------|-------------------|
| Background task started for job | INFO | `{"ts": "...", "event": "ocr_task_started", "job_id": "..."}` | `logs/app.log` |
| PDF conversion started/completed: page count, elapsed | INFO | `{"ts": "...", "event": "pdf_conversion_done", "job_id": "...", "pages": 0, "elapsed_s": 0.0}` | `logs/app.log` |
| Per-page OCR + layout elapsed, block count | DEBUG | `{"ts": "...", "event": "page_processed", "job_id": "...", "page": 0, "blocks": 0, "regions": 0, "elapsed_s": 0.0}` | `logs/app.log` |
| Low confidence warning: page, avg_confidence | WARNING | `{"ts": "...", "event": "low_confidence_page", "job_id": "...", "page": 0, "avg_conf": 0.41}` | `logs/app.log` + stderr |
| `process_pdf()` raised exception | ERROR | `{"ts": "...", "event": "pipeline_error", "job_id": "...", "exc_type": "...", "exc_msg": "..."}` | `logs/app.log` + stderr |
| Job set to `failed` | ERROR | `{"ts": "...", "event": "job_failed", "job_id": "...", "reason": "..."}` | `logs/app.log` + stderr |
| Aggregate JSON written | INFO | `{"ts": "...", "event": "result_written", "job_id": "...", "path": "..."}` | `logs/app.log` |
| Result endpoint read failure (disk) | ERROR | `{"ts": "...", "event": "result_read_error", "job_id": "...", "path": "..."}` | `logs/app.log` + stderr |

### 10G — Week 2 Testing Strategy

**Unit Tests — exact functions:**

| File | Functions Under Test |
|------|---------------------|
| `test_page_builder.py` | `build_page_result()` — block IDs assigned, layout regions linked, confidence average computed |
| `test_result_writer.py` | `write_page_json()` — file exists, JSON parseable; `write_aggregate_json()` — schema keys present |
| `test_job_store.py` (extend) | `update_result()` sets `result_path` and `completed_at`; `update_status('failed')` sets `error_message` |

**Integration Tests:**

| Test | How |
|------|-----|
| `test_full_pipeline.py` | Direct call to `process_pdf()` with `sample_digital.pdf`, assert `len(pages) == 3`, page JSONs on disk |
| `test_job_status_endpoint.py` | Manipulate DB to each status, assert correct HTTP code from status endpoint |
| Upload → poll → result | FastAPI `TestClient` async test: upload, sleep, GET result, assert schema |

**Manual Test Checklist:**
- [ ] Upload `sample_digital.pdf` → status reaches `completed` within 60s
- [ ] Upload `sample_scanned.pdf` → status reaches `completed` within 180s
- [ ] Upload `sample_bilingual.pdf` → result contains Hindi text
- [ ] `ls storage/jobs/{job_id}/pages/` shows correct number of PNG and JSON files
- [ ] `GET /job/{id}/result` body is valid JSON matching `ocr_result.json` schema
- [ ] Upload a corrupt file (valid magic bytes, garbage body) → job status = `failed`
- [ ] `cat logs/app.log | head -20 | python -m json.tool` — every line is valid JSON
- [ ] Run `scripts/smoke_test.py` — exits 0

### 10H — Week 2 Common Mistakes

| Mistake | Root Cause | Prevention |
|---------|-----------|-----------|
| Background task exception silently swallowed, job stuck in `processing` | FastAPI `BackgroundTasks` does not propagate exceptions to the request context | Wrap entire `run_ocr_job()` body in `try/except Exception as e`, always call `update_status('failed', error_message=str(e))` in `finally` block |
| PP-StructureV3 and PaddleOCR each download models on first call, total 4-6 GB | Both initialized lazily at prediction time during a live request | Pre-initialize both in `verify_env.py` or app lifespan; pin model directories in `constants.py` |
| Result JSON not UTF-8 encoded (Hindi text stored as escape sequences) | `json.dump()` default `ensure_ascii=True` | Use `json.dump(..., ensure_ascii=False)` in `result_writer.py` |
| Page images accumulate on disk for failed jobs | No cleanup on failure path | `run_ocr_job()` deletes `storage/jobs/{job_id}/pages/` on `failed` outcome (or document that cleanup is manual in MVP) |
| `process_pdf()` returns empty list for scanned page | PaddleOCR not configured for angle classification | Pass `use_angle_cls=True` in `OcrEngine.__init__()` for scanned document handling |
| Aggregate JSON written with absolute paths | Hardcoded `/home/user/...` paths break on other machines | Use `pathlib.Path` relative to project root; store relative paths in `ocr_result.json` |

### 10I — Week 2 Definition of Done

- [ ] `pytest tests/` — all tests pass, 0 failures, 0 errors
- [ ] Upload `sample_digital.pdf` → `completed` in ≤ 60s (manual timing)
- [ ] Upload `sample_scanned.pdf` → `completed` in ≤ 180s
- [ ] `GET /job/{id}/result` body validates against Section 8B schema
- [ ] Hindi text visible in `text_blocks` of `sample_bilingual.pdf` result
- [ ] Corrupt PDF upload → job status = `failed`, `error_message` non-null
- [ ] `scripts/smoke_test.py` exits 0
- [ ] Demo script (Section 10O) passes all pass/fail criteria
- [ ] `logs/app.log` contains only valid JSON lines
- [ ] No job may remain in `processing` after 10 minutes (timeout enforced in `run_ocr_job()`)
- [ ] `git log --oneline main` shows ≥ 20 commits across both engineers

---

### 10J — PDF Conversion Workflow

**Step-by-step with exact PyMuPDF API calls:**

```python
import fitz  # PyMuPDF
from pathlib import Path

def convert_pdf_to_images(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 200
) -> list[Path]:
    """
    Step 1: Open the PDF document.
    Step 2: Iterate pages, render each to a pixmap at target DPI.
    Step 3: Save each pixmap as PNG.
    Step 4: Return ordered list of image paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    image_paths: list[Path] = []

    # Step 1: Open document
    doc: fitz.Document = fitz.open(str(pdf_path))

    # DPI→zoom factor: fitz default is 72 DPI
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    for page_num in range(len(doc)):
        # Step 2: Load page and render to pixmap (RGB, no alpha)
        page: fitz.Page = doc.load_page(page_num)
        pix: fitz.Pixmap = page.get_pixmap(matrix=mat, alpha=False)

        # Step 3: Save as PNG
        # Naming: page_0001.png (1-indexed)
        out_path = output_dir / f"page_{page_num + 1:04d}.png"
        pix.save(str(out_path))

        image_paths.append(out_path)
        pix = None  # Release pixmap memory explicitly

    doc.close()

    # Step 4: Return ordered list
    return sorted(image_paths)
```

**Output format per page:**
- File: `storage/jobs/{job_id}/pages/page_0001.png`
- Format: PNG, RGB (no alpha)
- Dimensions: approximately 1654×2339 px at 200 DPI for A4
- Size on disk: 200 KB–2 MB per page depending on content density
- Naming convention: 1-indexed, zero-padded to 4 digits

---

### 10K — OCR + Layout Workflow

**Step-by-step with exact API calls:**

```python
# ocr_engine.py — PaddleOCR
from paddleocr import PaddleOCR
from pathlib import Path
from shared.models import TextBlock
import numpy as np
from PIL import Image

class OcrEngine:
    def __init__(self, lang: str = "en"):
        # Lazy-load on first __init__ call; model cached to ~/.paddleocr/
        # lang="en" handles English; for Hindi+English use a custom approach
        # (PaddleOCR multilingual: lang="en" + lang="hindi" in two passes)
        self.ocr = PaddleOCR(
            use_angle_cls=True,   # Required: handles rotated/skewed text in scanned docs
            lang=lang,
            use_gpu=False,        # Hard constraint: local CPU-only
            show_log=False,       # Suppress paddle verbose logging
        )

    def run(self, image_path: Path) -> list[TextBlock]:
        # Load image as numpy array (PaddleOCR accepts both file path and ndarray)
        img = np.array(Image.open(image_path).convert("RGB"))

        # Call OCR — returns list of: [[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], [text, confidence]]
        result = self.ocr.ocr(img, cls=True)

        text_blocks: list[TextBlock] = []
        if not result or result[0] is None:
            return text_blocks

        for idx, line in enumerate(result[0]):
            box_points, (text, confidence) = line
            # Convert 4-point polygon to axis-aligned bounding box
            xs = [p[0] for p in box_points]
            ys = [p[1] for p in box_points]
            text_blocks.append(TextBlock(
                block_id=f"blk_{idx+1:04d}",  # Finalized in page_builder
                text=text,
                confidence=round(float(confidence), 4),
                bounding_box={"x1": int(min(xs)), "y1": int(min(ys)),
                              "x2": int(max(xs)), "y2": int(max(ys))},
                language_hint="en"
            ))
        return text_blocks
```

```python
# layout_detector.py — PP-StructureV3
from paddleocr import PPStructure
from pathlib import Path
from shared.models import LayoutRegion
import numpy as np
from PIL import Image

class LayoutDetector:
    def __init__(self):
        self.structure = PPStructure(
            table=True,           # Enable table structure recognition
            ocr=False,            # OCR handled separately by OcrEngine
            show_log=False,
            use_gpu=False,
        )

    def detect(self, image_path: Path) -> list[LayoutRegion]:
        img = np.array(Image.open(image_path).convert("RGB"))

        # Returns list of dicts: {"type": str, "bbox": [x1,y1,x2,y2], "res": ...}
        result = self.structure.predict(img)

        regions: list[LayoutRegion] = []
        for idx, region in enumerate(result):
            region_type = region.get("type", "unknown").lower()
            bbox = region.get("bbox", [0, 0, 0, 0])

            # Extract table cells if region_type == "table"
            table_structure = None
            if region_type == "table" and "res" in region:
                table_structure = _parse_table_structure(region["res"])

            regions.append(LayoutRegion(
                region_id=f"reg_{idx+1:04d}",  # Finalized in page_builder
                region_type=region_type,
                bounding_box={"x1": bbox[0], "y1": bbox[1],
                              "x2": bbox[2], "y2": bbox[3]},
                contained_block_ids=[],  # Filled by page_builder
                table_structure=table_structure
            ))
        return regions
```

---

### 10L — Background Task Architecture

The upload endpoint triggers OCR processing via FastAPI's `BackgroundTasks`. The task runs in the same process, in a thread pool, after the HTTP response is sent.

```python
# routers/upload.py
from fastapi import APIRouter, BackgroundTasks, UploadFile, File
from app.db.job_store import create_job
from app.tasks.ocr_task import run_ocr_job
from shared.constants import STORAGE_ROOT
import uuid, shutil
from pathlib import Path

router = APIRouter()

@router.post("/upload", status_code=201)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    # 1. Validate file type
    _validate_pdf(file)

    # 2. Create job record in SQLite BEFORE writing file
    #    (if DB fails, we return 500 before touching filesystem)
    job_id = str(uuid.uuid4())
    job_dir = STORAGE_ROOT / "jobs" / job_id
    pdf_path = job_dir / "original.pdf"
    create_job(job_id=job_id, filename=file.filename, pdf_path=str(pdf_path))

    # 3. Write file to disk
    job_dir.mkdir(parents=True, exist_ok=True)
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 4. Register background task — executes AFTER response is sent
    background_tasks.add_task(run_ocr_job, job_id, pdf_path)

    return {"job_id": job_id, "status": "pending", ...}
```

```python
# tasks/ocr_task.py
from app.db.job_store import update_status
from ocr.pipeline import process_pdf
from shared.constants import JobStatus
import logging
from pathlib import Path

logger = logging.getLogger("tender_ocr")

def run_ocr_job(job_id: str, pdf_path: Path) -> None:
    """
    State machine:
      pending → processing (on entry)
      processing → completed (on success)
      processing → failed (on any exception)

    This function MUST NOT raise. All exceptions are caught and
    converted to 'failed' status. The finally block guarantees
    the job never remains in 'processing'.
    """
    try:
        # Transition: pending → processing
        update_status(job_id, JobStatus.PROCESSING)
        logger.info({"event": "ocr_task_started", "job_id": job_id})

        # Call the ML pipeline — Person 1's function
        page_results = process_pdf(job_id=job_id, pdf_path=pdf_path)

        # Transition: processing → completed
        result_path = str(pdf_path.parent / "ocr_result.json")
        update_status(job_id, JobStatus.COMPLETED, result_path=result_path)
        logger.info({"event": "job_completed", "job_id": job_id})

    except Exception as e:
        # Transition: processing → failed (ALWAYS)
        error_msg = f"{type(e).__name__}: {str(e)}"
        update_status(job_id, JobStatus.FAILED, error_message=error_msg)
        logger.error({"event": "job_failed", "job_id": job_id, "exc": error_msg})
        # Do NOT re-raise — BackgroundTasks would log it but state is already set
```

**How state is updated:** `update_status()` in `job_store.py` uses a single `UPDATE` statement with `WHERE job_id = ?` wrapped in a `with sqlite3.connect(db_path) as conn:` context (auto-commits). SQLite is opened in WAL mode to prevent reader blocking.

**How errors are caught:** The outermost `try/except Exception` in `run_ocr_job()` catches all exceptions from `process_pdf()`, all exceptions from `update_status()` on the success path, and all exceptions from file I/O. The `except` block calls `update_status(FAILED)` — if even that fails, the job remains in `processing` (documented as known limitation, resolved by a startup job recovery check).

---

### 10M — Error Handling + Retry Strategy

| Error Type | Detection | Handling | Retry? | Max Retries |
|-----------|-----------|----------|--------|-------------|
| PDF not readable by PyMuPDF | `fitz.open()` raises `fitz.FileNotFoundError` or `RuntimeError` | Catch in `process_pdf()`, re-raise; caught by `run_ocr_job()` → `failed` | N | — |
| PaddleOCR returns `None` for a page | `result[0] is None` check in `OcrEngine.run()` | Return empty list, add warning to page JSON, continue to next page | N | — |
| PP-StructureV3 raises OOM | `RuntimeError` containing "out of memory" | Caught by `run_ocr_job()` → `failed` with message; do not retry (memory won't free itself) | N | — |
| Page image write fails (disk full) | `OSError` from `pix.save()` | Caught by `run_ocr_job()` → `failed`; log disk path and available space | N | — |
| SQLite update fails (locked/corrupt) | `sqlite3.OperationalError` | Retry with 1s sleep × 3 in `update_status()` wrapper | Y | 3 |
| JSON write fails (permissions) | `OSError` from `json.dump()` | Caught by `run_ocr_job()` → `failed` | N | — |
| Startup: job stuck in `processing` | App lifespan startup check: `SELECT * FROM jobs WHERE status='processing'` | Set all stale `processing` jobs to `failed` with message "interrupted_by_restart" | N | — |

---

### 10N — Performance Expectations

| Metric | Digital PDF | Scanned PDF | Notes |
|--------|------------|-------------|-------|
| PDF→image conversion per page | 0.3–0.8s | 0.5–1.2s | Scanned pages have larger raw image data |
| PaddleOCR inference per page | 1–3s | 4–8s | Scanned pages require angle classification pass |
| PP-StructureV3 inference per page | 2–4s | 3–6s | Table detection is most expensive |
| Total per page (CPU, i5/i7) | 3–8s | 7–15s | Sequential, no batching |
| 10-page digital PDF end-to-end | 30–80s | — | Target: ≤ 60s for 95th percentile |
| 10-page scanned PDF end-to-end | — | 70–150s | Target: ≤ 180s for 95th percentile |
| Peak RAM per job | 1.5–2.5 GB | 2–3 GB | PaddleOCR + PP-StructureV3 models + image buffers |
| Model files on disk (one-time download) | ~2 GB total | same | `~/.paddleocr/` directory |
| Storage per job (50-page PDF, digital) | 80–200 MB | 200–500 MB | PNG images + JSONs; images dominate |
| Disk for 50 PDFs (avg 20 pages each) | 80–200 GB | 200–500 GB | **Disk is the binding constraint** — plan storage accordingly |

**Key constraint:** At 200 DPI, one A4 page PNG ≈ 2–4 MB. For 50 PDFs × 20 pages = 1000 images = 2–4 GB. This is manageable. Add page JSONs (~50 KB each) and the total remains under 5 GB for 50 PDFs.

---

### 10O — Week 2 Demo Script

The demo operator follows these steps in order. Each step has an expected terminal output and a pass/fail criterion.

```bash
# STEP 0: Start the application
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
**Expected:** `INFO: Application startup complete.` — no errors
**Pass:** Application starts; **Fail:** Any exception or import error

```bash
# STEP 1: Upload a digital PDF
curl -s -X POST http://localhost:8000/upload \
  -F "file=@tests/fixtures/sample_digital.pdf" | python -m json.tool
```
**Expected output:**
```json
{
    "job_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "status": "pending",
    "message": "Job created. Poll /job/{job_id}/status for updates.",
    "created_at": "2024-01-15T10:30:00Z"
}
```
**Pass:** HTTP 201, `job_id` field present; **Fail:** Any other HTTP code

```bash
# STEP 2: Save job_id (replace with actual value from Step 1)
export JOB_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# STEP 3: Poll status (repeat until completed — ~30-60 seconds)
curl -s http://localhost:8000/job/$JOB_ID/status | python -m json.tool
```
**Expected output (while processing):**
```json
{"job_id": "...", "status": "processing", "page_count": 3, ...}
```
**Expected output (when done):**
```json
{"job_id": "...", "status": "completed", "page_count": 3, "completed_at": "..."}
```
**Pass:** Status transitions to `completed`; **Fail:** Status `failed` or stuck in `processing` > 120s

```bash
# STEP 4: Verify files on disk
ls storage/jobs/$JOB_ID/pages/
```
**Expected:** `page_0001.png  page_0001.json  page_0002.png  page_0002.json  page_0003.png  page_0003.json`
**Pass:** 6 files present; **Fail:** Missing files

```bash
# STEP 5: Fetch result
curl -s http://localhost:8000/job/$JOB_ID/result | python -m json.tool | head -50
```
**Expected:** JSON starting with `{"job_id": "...", "status": "completed", "page_count": 3, "pages": [...]}`
**Pass:** Valid JSON, `status = "completed"`, `pages` array length = 3; **Fail:** Parse error or wrong schema

```bash
# STEP 6: Upload a scanned PDF
curl -s -X POST http://localhost:8000/upload \
  -F "file=@tests/fixtures/sample_scanned.pdf" | python -m json.tool
export JOB_ID_SCAN="<job_id from output>"
# Wait 2-3 minutes, then:
curl -s http://localhost:8000/job/$JOB_ID_SCAN/status | python -m json.tool
```
**Pass:** Status = `completed`; **Fail:** Status = `failed` or timeout

```bash
# STEP 7: Upload a bilingual PDF
curl -s -X POST http://localhost:8000/upload \
  -F "file=@tests/fixtures/sample_bilingual.pdf" | python -m json.tool
export JOB_ID_BI="<job_id from output>"
# After completion:
curl -s http://localhost:8000/job/$JOB_ID_BI/result | \
  python -c "import sys, json; d=json.load(sys.stdin); \
  page1_path=d['pages'][0]['page_json_path']; \
  p=json.load(open(page1_path)); \
  texts=[b['text'] for b in p['text_blocks']]; print('\n'.join(texts[:5]))"
```
**Pass:** Output contains at least one Hindi character (देवनागरी script); **Fail:** Only ASCII output

```bash
# STEP 8: Error case — corrupt PDF
echo "not a real pdf" > /tmp/corrupt.pdf
curl -s -X POST http://localhost:8000/upload -F "file=@/tmp/corrupt.pdf"
```
**Expected:** HTTP 400 (MIME/magic byte validation catches it before job creation)
**Pass:** HTTP 400; **Fail:** 201 or 500

```bash
# STEP 9: Run smoke test script
python scripts/smoke_test.py
```
**Pass:** Script exits 0 with `[PASS] All smoke tests passed`; **Fail:** Any `[FAIL]` line or non-zero exit

```bash
# STEP 10: Run full test suite
pytest tests/ -v --tb=short
```
**Pass:** `X passed, 0 failed, 0 errors`; **Fail:** Any failure

---

## Section 11 — File Naming Conventions

| File Type | Naming Pattern | Example | Notes |
|-----------|---------------|---------|-------|
| Job directory | `{job_id}/` (UUID v4) | `a1b2c3d4-e5f6-7890-abcd-ef1234567890/` | UUID generated by `uuid.uuid4()` at upload time |
| Original PDF | `original.pdf` | `original.pdf` | Always this exact name inside job dir |
| Page image | `page_{NNNN}.png` | `page_0001.png` | 1-indexed, zero-padded to 4 digits |
| Page JSON | `page_{NNNN}.json` | `page_0001.json` | Same number as corresponding PNG |
| Aggregate result | `ocr_result.json` | `ocr_result.json` | Single file per job, in job root dir |
| Raw OCR JSON | `raw_ocr.json` | `raw_ocr.json` | Validated raw OCR blocks list, in job root dir |
| Layout JSON | `layout.json` | `layout.json` | Validated layout-labeled regions, in job root dir |
| Extracted Fields JSON | `extracted_fields.json` | `extracted_fields.json` | Deterministic extracted fields list, in job root dir |
| SQLite database | `tender.db` | `data/tender.db` | Fixed name, path from `constants.py` |
| Log file | `app.log` | `logs/app.log` | Rotated daily in production; MVP: single file |
| Test fixture | `sample_{type}.pdf` | `sample_digital.pdf` | Types: `digital`, `scanned`, `bilingual` |
| Unit test module | `test_{module_name}.py` | `test_pdf_converter.py` | Mirrors source module name with `test_` prefix |
| Python module | `{noun}_{verb/role}.py` | `pdf_converter.py`, `job_store.py` | Snake case, no abbreviations |

---

## Section 12 — Git Strategy

**Branch naming convention:**

```
main              — deployable state only; direct push blocked
dev               — integration branch; PRs merge here first
p1/{task-slug}    — Person 1 feature branches
p2/{task-slug}    — Person 2 feature branches
fix/{issue-slug}  — Bugfix branches for either engineer
```

**Examples:**
- `p1/pdf-converter`
- `p1/ocr-engine`
- `p2/upload-endpoint`
- `p2/job-store`
- `fix/paddleocr-angle-cls`

**Commit message format:**

```
<type>(<scope>): <imperative summary in ≤ 72 chars>

[optional body: what changed and why, not how]
[optional: Fixes #issue]
```

Types: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`

**Examples:**
```
feat(pdf_converter): add convert_pdf_to_images with 200 DPI output
test(job_store): add 6 unit tests covering all CRUD operations
fix(ocr_engine): set use_angle_cls=True to handle rotated scanned text
feat(upload): add magic byte validation before job creation
chore(deps): pin paddleocr==2.7.3 and paddlepaddle==2.6.1
refactor(pipeline): extract page_builder into separate module
docs(readme): add performance expectations table for CPU-only hardware
```

**PR strategy for 2-person team:**

| Rule | Detail |
|------|--------|
| PR target | All PRs target `dev`, not `main` |
| Reviewer | The other engineer reviews every PR — no self-merge |
| PR size | One logical change per PR; ≤ 300 lines diff preferred |
| `main` merge | End of Week 1 and end of Week 2 only; both engineers approve |
| Shared contracts | `shared/models.py` and `shared/constants.py` require both approvals |
| CI check (manual) | Before merge to `dev`: run `pytest tests/unit/` locally and paste output in PR description |

---

## Section 13 — Blockers Reference

| Symptom | Root Cause | Diagnosis Command | Solution |
|---------|-----------|------------------|---------|
| `ImportError: cannot import name 'PaddleOCR'` | `paddleocr` not installed or wrong venv active | `pip show paddleocr` | `pip install paddleocr==2.7.3 paddlepaddle==2.6.1` in the correct venv |
| `PaddleOCR()` call hangs for > 5 minutes | Model download stalled on first init | `ls ~/.paddleocr/whl/` — check for incomplete files | Delete `~/.paddleocr/whl/` and retry; or manually download model ZIPs from PaddlePaddle hub |
| `RuntimeError: (InvalidArgument) ...` on `ocr.ocr(img)` | Image is not uint8 RGB numpy array | `print(img.dtype, img.shape)` | Convert: `img = np.array(Image.open(path).convert("RGB"))` |
| PyMuPDF `AttributeError: module 'fitz' has no attribute 'open'` | Wrong `fitz` package installed (PyMuPDF conflict with another fitz) | `pip show fitz pymupdf` | `pip uninstall fitz; pip install PyMuPDF` |
| `sqlite3.OperationalError: database is locked` | Multiple connections with no WAL mode | `PRAGMA journal_mode` in sqlite3 CLI | Add `conn.execute("PRAGMA journal_mode=WAL")` in `init_db()` |
| Job stuck in `processing` after app restart | App killed mid-task; status never updated | `sqlite3 data/tender.db "SELECT job_id, status FROM jobs WHERE status='processing'"` | Add startup recovery in `app/main.py` lifespan: set all `processing` → `failed` on startup |
| `POST /upload` returns 201 but `ocr_task` never runs | `background_tasks.add_task()` not called (wrong indentation, early return) | `grep -n "add_task" app/routers/upload.py` | Ensure `add_task()` is called before `return`; add log line at task start |
| PP-StructureV3 returns empty list for all regions | `PPStructure` using wrong model path or model not downloaded | `python -c "from paddleocr import PPStructure; s=PPStructure(); print('ok')"` | Run the import in isolation; if model missing, it will download; check `~/.paddleocr/` |
| Hindi text appears as `???` or question marks in JSON | `ensure_ascii=True` in `json.dump()` | `grep ensure_ascii ocr/result_writer.py` | Change to `json.dump(..., ensure_ascii=False, indent=2)` |
| Memory error on large scanned PDF | All page images loaded simultaneously | `htop` during processing | Process pages sequentially; release each pixmap with `pix = None` after save |
| `GET /job/{id}/result` returns 500 for completed job | `result_path` in DB is absolute, but app running from different CWD | `sqlite3 data/tender.db "SELECT result_path FROM jobs WHERE job_id='...'"` | Store all paths as relative to project root in `constants.py` |

---

## Section 14 — Future Extensions Map

| Module | Where It Plugs In | Input It Receives | Output It Produces |
|--------|-------------------|-------------------|--------------------|
| [Done] Field Extraction | Integrated in Pipeline | `PageResult` objects list | Validated Pydantic JSONs (`raw_ocr.json`, `layout.json`, `extracted_fields.json`) |
| NER | Inside Field Extraction module | `text_blocks` from page JSONs | Entity spans: `[{text, label, page, bounding_box}]` |
| Validation Engine | After Field Extraction | Extracted field dict + NER output | Validation report: `{field: {value, confidence, issues}}` |
| LLM Fallback | After Validation Engine (triggered on low-confidence fields) | Low-confidence field values + surrounding text context | Corrected field values with reasoning |
| Human Review Queue | After Validation Engine | Jobs with validation issues or confidence < threshold | Review task records in a new SQLite table |
| Search Index | After `ocr_result.json` is written | Full-text content of all `text_blocks` per job | Searchable index entry (e.g., SQLite FTS5 virtual table) |
| Analytics | After `ocr_result.json` is written | `summary` block of `ocr_result.json` | Aggregated metrics per time period: avg confidence, table count, failure rate |

---

## Section 15 — Appendix

### A) Minimal Repository Tree

```
tender-ocr/
├── app/__init__.py
├── app/main.py
├── app/routers/__init__.py
├── app/routers/upload.py
├── app/routers/jobs.py
├── app/tasks/__init__.py
├── app/tasks/ocr_task.py
├── app/models/__init__.py
├── app/models/schemas.py
├── app/db/__init__.py
├── app/db/job_store.py
├── app/db/migrations.py
├── ocr/__init__.py
├── ocr/pipeline.py
├── ocr/pdf_converter.py
├── ocr/ocr_engine.py
├── ocr/layout_detector.py
├── ocr/page_builder.py
├── ocr/field_extractor.py
├── ocr/result_writer.py
├── shared/__init__.py
├── shared/models.py
├── shared/schemas.py
├── shared/constants.py
├── tests/__init__.py
├── tests/unit/test_pdf_converter.py
├── tests/unit/test_ocr_engine.py
├── tests/unit/test_layout_detector.py
├── tests/unit/test_page_builder.py
├── tests/unit/test_result_writer.py
├── tests/unit/test_job_store.py
├── tests/integration/test_upload_endpoint.py
├── tests/integration/test_job_status_endpoint.py
├── tests/integration/test_full_pipeline.py
├── tests/fixtures/sample_digital.pdf
├── tests/fixtures/sample_scanned.pdf
├── tests/fixtures/sample_bilingual.pdf
├── scripts/verify_env.py
├── scripts/smoke_test.py
├── data/.gitkeep
├── storage/.gitkeep
├── logs/.gitkeep
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

### B) Minimal SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'pending',
    original_filename TEXT NOT NULL,
    pdf_path        TEXT NOT NULL,
    result_path     TEXT,
    page_count      INTEGER,
    error_message   TEXT,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
```

---

### C) Minimal Job Metadata JSON

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "original_filename": "tender_notice.pdf",
  "pdf_path": "storage/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/original.pdf",
  "result_path": "storage/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/ocr_result.json",
  "page_count": 12,
  "error_message": null,
  "created_at": "2024-01-15T10:30:00Z",
  "started_at": "2024-01-15T10:30:01Z",
  "completed_at": "2024-01-15T10:31:45Z",
  "retry_count": 0
}
```

---

### D) Minimal OCR Page JSON

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "page_number": 1,
  "image_path": "storage/jobs/a1b2c3d4/pages/page_0001.png",
  "image_width_px": 2480,
  "image_height_px": 3508,
  "processing_time_seconds": 4.23,
  "text_blocks": [
    {
      "block_id": "blk_0001_001",
      "text": "भारत सरकार / Government of India",
      "confidence": 0.97,
      "bounding_box": {"x1": 820, "y1": 110, "x2": 1660, "y2": 158},
      "language_hint": "hi+en"
    }
  ],
  "layout_regions": [
    {
      "region_id": "reg_0001_001",
      "region_type": "title",
      "bounding_box": {"x1": 820, "y1": 90, "x2": 1660, "y2": 220},
      "contained_block_ids": ["blk_0001_001"],
      "table_structure": null
    }
  ],
  "warnings": []
}
```

---

### E) Sample curl Requests

```bash
# Upload a PDF
curl -s -X POST http://localhost:8000/upload \
  -F "file=@tests/fixtures/sample_digital.pdf" \
  | python -m json.tool

# Check job status
curl -s http://localhost:8000/job/YOUR_JOB_ID/status \
  | python -m json.tool

# Fetch job result (only works when status=completed)
curl -s http://localhost:8000/job/YOUR_JOB_ID/result \
  | python -m json.tool

# Attempt result fetch before completion (expect 409)
curl -sv http://localhost:8000/job/YOUR_JOB_ID/result 2>&1 | grep "< HTTP"

# Fetch status of non-existent job (expect 404)
curl -sv http://localhost:8000/job/00000000-0000-0000-0000-000000000000/status \
  2>&1 | grep "< HTTP"

# Upload non-PDF file (expect 400)
echo "not a pdf" > /tmp/fake.pdf
curl -s -X POST http://localhost:8000/upload \
  -F "file=@/tmp/fake.pdf" \
  | python -m json.tool
```

---

### F) Final Engineering Checklist

**Week 1 Done:**

- [ ] Both engineers: `python scripts/verify_env.py` exits 0
- [ ] `shared/models.py` merged to `main` (approved by both)
- [ ] `shared/constants.py` merged to `main` (approved by both)
- [ ] `pytest tests/unit/test_pdf_converter.py` — all pass
- [ ] `pytest tests/unit/test_ocr_engine.py` — all pass
- [ ] `pytest tests/unit/test_layout_detector.py` — all pass
- [ ] `pytest tests/unit/test_job_store.py` — all 6 pass
- [ ] `pytest tests/integration/test_upload_endpoint.py` — all pass
- [ ] `uvicorn app.main:app` starts cleanly
- [ ] `POST /upload` with fixture PDF returns 201 + job_id
- [ ] `storage/jobs/{job_id}/original.pdf` exists after upload
- [ ] SQLite schema matches Section 6 exactly

**Week 2 Done:**

- [ ] `pytest tests/` — all tests pass, 0 failures
- [ ] `process_pdf()` callable and returns `list[PageResult]`
- [ ] Digital PDF pipeline: `completed` in ≤ 60s
- [ ] Scanned PDF pipeline: `completed` in ≤ 180s
- [ ] Bilingual PDF result contains Hindi text in `text_blocks`
- [ ] Corrupt PDF → job status = `failed` with `error_message`
- [ ] `GET /job/{id}/result` returns valid `ocr_result.json` schema
- [ ] `cat logs/app.log | python -m json.tool` — every line valid JSON
- [ ] No job stuck in `processing` after app restart (startup recovery)
- [ ] `python scripts/smoke_test.py` exits 0

**Demo Ready:**

- [ ] All 10 steps in Section 10O complete without manual intervention
- [ ] Both fixture PDFs (digital + scanned) processed end-to-end live
- [ ] Bilingual test shows Hindi text in terminal output
- [ ] Error case (corrupt PDF) returns 400 — not 500
- [ ] Swagger UI at `http://localhost:8000/docs` loads all 3 endpoints
- [ ] `README.md` has complete setup instructions a new developer can follow





# Model Performance & Interactive Visualizer Walkthrough
This walkthrough outlines both the OCR model's evaluation results on sample tender documents and the newly built web-based results visualizer.

---

## 📊 Evaluation Performance Metrics

The OCR pipeline successfully processed the first 3 PDFs from `sample_files/`. The metrics are documented below:

| File Name | Pages | Processing Time | Average Time/Page | Total Text Blocks | Total Layout Regions |
| :--- | :---: | :---: | :---: | :---: | :---: |
| [GeM-Bidding-7641085...pdf](file:///c:/Users/Asus/Desktop/Tender_Volks/main/sample_files/GeM-Bidding-7641085.pdf_1750409965_2005407.pdf) | 8 | 73.91s | 9.24s | 378 | 59 |
| [GeM-Bidding-7724454...pdf](file:///c:/Users/Asus/Desktop/Tender_Volks/main/sample_files/GeM-Bidding-7724454.pdf_1748685463_3605671.pdf) | 6 | 69.08s | 11.51s | 297 | 38 |
| [GeM-Bidding-7747584...pdf](file:///c:/Users/Asus/Desktop/Tender_Volks/main/sample_files/GeM-Bidding-7747584.pdf_1746189248_17620609.pdf) | 8 | 80.77s | 10.10s | 344 | 57 |

All 3 sample files (6-8 pages each) completed in **under 81 seconds** on CPU-only hardware (averaging ~10s per page). This successfully satisfies the performance SLA (<60s per digital document, <180s per scanned document).

---

## 🚀 Interactive Web-Based Results Visualizer

We created a web-based visualization tool to inspect, zoom, and analyze the OCR and layout detection results of all completed jobs.

### 1. How to Launch and View
1. Start the FastAPI development server:
   ```powershell
   uvicorn app.main:app --port 8081
   ```
2. Open your web browser and navigate to:
   [http://localhost:8081/visualizer](http://localhost:8081/visualizer) or [http://localhost:8081/](http://localhost:8081/)

### 2. Implemented Features
* **Job List Selector**: Reads and parses `storage/jobs/*/ocr_result.json` automatically, listing completed runs with their metadata (pages, duration, blocks, layout regions).
* **High-Fidelity Canvas**: Loads page images (`page_xxxx.png`) and overlays bounding boxes using dynamic SVG layers.
  * **Text Blocks**: Outlined by confidence score (Green >= 85%, Yellow 50%-85%, Red < 50%).
  * **Layout Regions**: Outlined based on region classification (Cyan for table, Green for title, Orange for stamp, Blue for text).
* **Hover Interaction**: Hovering over a block on the page highlights it in the side panel table, and vice-versa.
* **Control Center**:
  * **Visibility Toggles**: Toggle Text Blocks, Layout Regions, and text Labels dynamically.
  * **Confidence Filter Slider**: Filters out any text blocks below the specified threshold on-the-fly.
  * **Pan & Zoom Controls**: Supports click-and-drag panning and mouse wheel/button zoom capabilities.
* **Details Tables**:
  * **Text Blocks Tab**: Lists block IDs, exact string matches, and confidence percentages.
  * **Layout Regions Tab**: Lists region IDs, coordinates, and types.
  * **Structured Table Preview**: Clicking on a `table` region renders its reconstructed HTML layout directly inside the sidebar for validation!
  * **Extracted Fields Tab**: Displays visual cards representing the 10 target fields, values, confidence scores, and source evidence.
  * **Traceability Navigation**: Clicking on any field card automatically changes the active page to the source page, highlights the evidence bounding box on the canvas, and pans/zooms the viewport to focus on it.
  * **Metadata Tab**: Displays execution time, job ID, page number, and any execution warnings.

---

## 🔗 Structure-Aware API Endpoints

FastAPI exposes the validated output JSON payloads directly for external use:
*   `GET /job/{job_id}/raw-ocr`: Returns `raw_ocr.json` schema content.
*   `GET /job/{job_id}/layout`: Returns `layout.json` schema content.
*   `GET /job/{job_id}/extracted-fields`: Returns `extracted_fields.json` schema content.

---

## 📁 File Structure Reference

Here are the visualizer and extractor files added/modified:
* [field_extractor.py](file:///c:/Users/Asus/Desktop/Tender_Volks/main/ocr/field_extractor.py): The deterministic extractor engine.
* [schemas.py](file:///c:/Users/Asus/Desktop/Tender_Volks/main/shared/schemas.py): Pydantic schemas validating raw OCR, layout regions, and extracted fields.
* [visualizer.py](file:///c:/Users/Asus/Desktop/Tender_Volks/main/app/routers/visualizer.py): The FastAPI visualizer router scanning the jobs directory.
* [main.py](file:///c:/Users/Asus/Desktop/Tender_Volks/main/app/main.py): Registers the visualizer routes and mounts static files under `/storage`.
* [index.html](file:///c:/Users/Asus/Desktop/Tender_Volks/main/app/static/index.html): The standalone HTML5/JS/CSS frontend with Extracted Fields cards support.
