
**System Name:** Tender Volks Engine (EPIC-AI Backend & Pipeline)  
**Repository Path:** `c:\Users\Asus\Desktop\Tender_Volks\main`  
**Analysis Date:** August 2026  

---

## Executive Summary

The **Tender Volks Engine** is a specialized, multi-stage document processing and extraction engine designed to ingest, parse, normalize, and reason over Indian government procurement tenders (specifically GeM — Government e-Marketplace, GAIL, and PSU tenders) and enterprise NIT (Notice Inviting Tender) documents.

The engine employs a **two-layer hybrid architecture**:
1. **Layer 1 (Deterministic Extraction):** Fast spatial bounding-box OCR, heuristic table grid reconstruction, Wingdings checkbox detection, hyperlink-based Additional Terms & Conditions (ATC) PDF child-document resolution, and regex rule matching.
2. **Layer 2 (Generative LLM Resolution & Memory):** Multi-model fallback (Google Gemini 2.5 Flash / Groq LLaMA 3.3 70B) acting exclusively on unextracted/ambiguous fields, backed by a persistent few-shot learning memory store that learns continuously from user corrections in the frontend UI.

---

## 1. System Architecture & Tech Stack

### 1.1 Core Technologies & Dependency Inventory

| Layer / Component | Technology / Library | Version Constraint | Primary Role & Location |
| :--- | :--- | :--- | :--- |
| **API Framework** | [FastAPI](https://fastapi.tiangolo.com/) | `>=0.100.0` | High-performance async REST API framework ([`backend/app/main.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/main.py)) |
| **ASGI Server** | [Uvicorn](https://www.uvicorn.org/) | `>=0.22.0` (standard) | HTTP / WebSockets application server |
| **Data Validation** | [Pydantic](https://docs.pydantic.dev/) & `pydantic-settings` | `>=2.0.0` | Schema definitions, request validation, and environment config ([`config.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/core/config.py)) |
| **Relational ORM** | [SQLAlchemy](https://www.sqlalchemy.org/) | `>=2.0.0` | ORM for PostgreSQL mapping ([`session.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/db/session.py), [`models/`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/models)) |
| **Database Drivers** | `psycopg2-binary`, `sqlite3` | `>=2.9.0` | PostgreSQL connection pool and local SQLite job store |
| **PDF Processing** | [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/) | Latest | Native text extraction, PDF rasterization (300 DPI), URI annotation extraction, checkbox extraction ([`pdf_text_extractor.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/services/pdf_text_extractor.py)) |
| **OCR Engines** | `pytesseract` & `PaddleOCR` | `>=0.3.10` | Multilingual OCR (`eng+hin` Hindi traineddata fallback) ([`ocr_engine.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/ocr/ocr_engine.py)) |
| **Image Processing** | `Pillow (PIL)`, `OpenCV` | `>=8.0.0` / `>=4.5.0` | Grayscale, contrast enhancement (2.0x), image sharpening, table line detection |
| **LLM & Reasoning** | `google-genai` / `google-generativeai` | `>=0.8.0` | Structured JSON field extraction via Gemini 2.5 Flash / Groq ([`llm_field_resolver.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/services/llm_field_resolver.py)) |
| **Fuzzy Matching** | `rapidfuzz` | Latest | High-speed fuzzy string comparison across field aliases |
| **Spreadsheet Gen** | `openpyxl`, `pandas` | `>=3.0.0` / `>=1.3.0` | Multi-tab Excel / InfoSheet CSV export ([`info_sheet_generator.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/services/info_sheet_generator.py)) |
| **Frontend** | React 19, TypeScript, Vite, TailwindCSS v4 | Vite 8, React 19.2 | Interactive workspace UI, field inspection, spreadsheet preview ([`frontend/`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/frontend)) |

---

### 1.2 Infrastructure & Containerization Topology

The infrastructure definition is located in [`infra/docker-compose.dev.yml`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/infra/docker-compose.dev.yml) and [`backend/Dockerfile`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/Dockerfile):

```
                       +-----------------------------------+
                       |        Frontend SPA (Vite/React)  |
                       |    http://localhost:5173 / 5174   |
                       +-----------------+-----------------+
                                         |
                                         | HTTP / REST (CORS enabled)
                                         v
+-----------------------------------------------------------------------------------+
|  Tender Backend (FastAPI / Uvicorn) - Port 8000                                   |
|  - RequestIDMiddleware (Tracing)                                                  |
|  - In-Process BackgroundTasks Pipeline                                            |
|  - Disk-backed LocalObjectStore Shim (MinIO API Drop-in)                          |
+---------+--------------------+--------------------+-------------------------------+
          |                    |                    |
          v                    v                    v
+------------------+  +------------------+  +------------------+
|    PostgreSQL    |  |      Redis       |  |      MinIO       |
|    (Port 5433)   |  |   (Port 6379)    |  | (Port 9000/9001) |
|  tender_projects |  |   Health check   |  | S3 Object Store  |
|  documents       |  |   configured     |  | (Raw/Processed)  |
|  tender_info     |  |                  |  |                  |
+------------------+  +------------------+  +------------------+
```

* **Backend Container (`tender_backend`):** Built on `python:3.11-slim` with system packages `build-essential`, `curl`, `libgl1`, `libglib2.0-0`, and `tesseract-ocr`.
* **PostgreSQL (`tender_postgres`):** `postgres:15-alpine` mapped to host port `5433:5432` with healthcheck `pg_isready`.
* **Redis (`tender_redis`):** `redis:7-alpine` on port `6379` with `redis-cli ping` healthcheck.
* **MinIO (`tender_minio`):** S3-compatible object storage on ports `9000` (API) and `9001` (Console UI).

---

### 1.3 Directory Structure & Separation of Concerns

```
TENDER_VOLKS/
├── backend/
│   ├── Dockerfile                   # Python 3.11 + Tesseract + OpenCV container
│   ├── requirements.txt             # Python backend dependencies
│   └── app/
│       ├── main.py                  # App entrypoint, lifespan startup/recovery, CORS, SPA static mount
│       ├── api/
│       │   ├── upload.py            # Unified PDF upload & process triggers (/tenders/upload, /tenders/process)
│       │   ├── jobs.py              # Job status, report downloads, legacy OCR endpoints (/jobs/{id})
│       │   ├── visualizer.py        # Legacy visualizer JSON inspection routes
│       │   └── routes/
│       │       ├── health.py        # Multi-service health probe (Postgres, Redis, MinIO, RAM, CPU)
│       │       ├── notify.py        # Telegram team alerting webhook integration
│       │       └── tenders.py       # Core workspace CRUD, verification, field edit, InfoSheet generation
│       ├── core/
│       │   ├── config.py            # Pydantic Settings (.env.dev / env vars)
│       │   ├── constants.py         # Root paths, serverless/Vercel tempdir detection, JobStatus enum
│       │   ├── logging.py           # Structured JSON / console logger
│       │   ├── minio.py             # LocalObjectStore shim implementing MinIO client interface
│       │   └── request_id.py        # Request ID tracing middleware
│       ├── db/
│       │   └── session.py           # SQLAlchemy Engine, SessionLocal, get_db dependency
│       ├── models/                  # SQLAlchemy ORM Models
│       │   ├── tender_project.py    # TenderProject (top-level project grouping)
│       │   ├── document.py          # Document (parent and child PDF files)
│       │   ├── tender_information.py# TenderInformation (70+ mapped columns)
│       │   ├── job.py               # Postgres Job status table
│       │   └── models.py            # Data classes: TextBlock, LayoutRegion, PageResult
│       ├── repositories/
│       │   ├── job_store.py         # SQLite job status state machine (thread-safe, retry loops)
│       │   ├── migrations.py        # SQLite table initialization & safe column migrations
│       │   └── tender_repository.py # Raw SQL & ORM upsert helpers for TenderInformation
│       ├── schemas/
│       │   ├── tender_project.py    # Request/Response schemas for Projects, Uploads, Jobs
│       │   └── schemas.py           # BoundingBox, OCRBlockSchema, LayoutRegionSchema, ExtractedFields
│       ├── services/
│       │   ├── pdf_parent_ingest.py # Master Ingest Orchestrator (Hybrid OCR -> ATC -> LLM -> XLSX)
│       │   ├── pdf_link_extractor.py# PyMuPDF fitz.LINK_URI annotation extractor & GeM session downloader
│       │   ├── pdf_text_extractor.py# Hybrid digital vs scanned page classifier & Wingdings checkbox parser
│       │   ├── field_registry.py    # Single source of truth for keyword synonyms across engines
│       │   ├── field_extractor.py   # Deterministic regex field parser (Layer 1)
│       │   ├── tender_mapper.py     # Schema normalizer, 4-tier status calculator (2,500+ LOC)
│       │   ├── llm_field_resolver.py# Gemini 2.5 Flash / Groq LLM fallback & Few-Shot memory (Layer 2)
│       │   ├── info_sheet_generator.py# OpenPyXL styler for multi-section evaluation spreadsheets
│       │   ├── storage.py           # Upload / download abstractions over MinIO / LocalObjectStore
│       │   └── email_service.py     # SMTP dispatcher for CSV summary & evidence attachments
│       └── workers/
│           └── ocr_task.py          # Background worker tasks for automated pipeline runs
├── ocr/                             # Independent Core OCR Engine Subsystem
│   ├── pipeline.py                  # End-to-end OCR pipeline (Page images -> OCR -> Layout -> JSON)
│   ├── ocr_engine.py                # PaddleOCR / Tesseract abstraction with language pack verifier
│   ├── table_grid_parser.py         # Spatial table cell reconstruction and column grouping
│   ├── pdf_converter.py             # PyMuPDF fitz.Matrix rasterizer (300 DPI)
│   ├── layout/
│   │   ├── layout_detector.py       # Tesseract-based paragraph and multi-column table box detector
│   │   └── layoutlm_stage.py        # Hugging Face LayoutLM token classification wrapper
│   └── extractors/
│       ├── field_extractor.py       # Generic NIT spatial field extractor
│       └── gem_field_extractor.py   # GeM-specific structured field & product item extractor
├── frontend/                        # Modern React 19 + TypeScript + Vite + TailwindCSS Workspace UI
├── gold_standard/                   # Evaluation ground truth datasets and test tender PDFs
└── scripts/                         # Evaluation, integration test, and smoke test scripts
```

---

## 2. Data Flow & Execution Model

### 2.1 Document Ingestion Lifecycle

```
[User / Client]
       │
       ▼  POST /tenders/upload (multipart/form-data)
[FastAPI: upload_pdf]
       │
       ├─► 1. Validate PDF magic bytes and filename extension
       ├─► 2. Generate UUID job_id
       ├─► 3. Write binary stream to disk: STORAGE_ROOT/jobs/{job_id}/original.pdf
       ├─► 4. Store in Object Storage via upload_file_to_minio()
       ├─► 5. Insert SQLite Job Record (status: 'pending')
       ├─► 6. Enqueue FastAPI BackgroundTasks -> _run_ingest_background()
       │
       ▼ Returns HTTP 201: { job_id, file_id, tender_id, status: "pending" }
```

```
[Background Worker: _run_ingest_background]
       │
       ├─► Status Update: 'processing'
       │
       ▼ [Step 1: Hybrid PDF Extraction] (pdf_text_extractor.py)
       │  - Classifies each page: Native Digital vs. Scanned Raster
       │  - Native: extracts word boxes & Wingdings checkbox states (checked/unchecked)
       │  - Scanned: renders to 300 DPI PNG, applies contrast/sharpening, runs Tesseract (eng+hin)
       │
       ▼ [Step 2: Hyperlink & ATC Discovery] (pdf_link_extractor.py)
       │  - Inspects page.get_links() for fitz.LINK_URI annotations
       │  - Identifies "Click here to view file" / ATC document links
       │  - Warm-up session to GeM portal (bidplus.gem.gov.in) with browser headers
       │  - Downloads child ATC PDF to extracted_children/, validates PDF magic bytes (%PDF)
       │
       ▼ [Step 3: Layer 1 Deterministic Field Extraction] (field_extractor.py)
       │  - Classifies document type: 'gem_structured' vs 'generic_nit'
       │  - Extracts 30+ core procurement fields via spatial anchors and regex patterns
       │
       ▼ [Step 4: ATC Child Document Merging & Field Precedence] (pdf_parent_ingest.py)
       │  - Parses downloaded ATC PDF
       │  - Applies AGENTS.md Precedence Rules:
       │    * ATC_SOURCED_LABELS (Payment Terms, LD/PRS, SD, Contacts, Courier) -> ATC Overrides
       │    * MAIN_SOURCED_LABELS (PBG %, Tender Title, NIT No, Bid Validity) -> Main Doc Locked
       │    * AMBIGUOUS_LABELS -> Preserves both: {"main_tender": ..., "atc": ...}
       │  - Handles Financial Criteria Exemption (auto-exempts turnover, solvency, net worth)
       │
       ▼ [Step 5: Layer 2 LLM Fallback Resolution] (llm_field_resolver.py)
       │  - Gathers all remaining "MISSING" or "NA" fields
       │  - Injects few-shot examples from storage/llm_memory/extraction_memory.json
       │  - Calls Gemini 2.5 Flash (or Groq LLaMA 3.3 70B fallback) with structured JSON schema
       │  - Validates non-hallucination against source text; merges extracted values
       │
       ▼ [Step 6: Spreadsheet Generation & DB Persistence] (info_sheet_generator.py)
       │  - Generates multi-section stylized Excel workbook ({Filename}_InfoSheet.xlsx)
       │  - Writes tender_detail.json to job directory
       │  - Persists TenderProject and Document records in PostgreSQL
       │
       ▼ Status Update: 'completed'
```

### 2.2 Execution Concurrency Model

* **In-Process BackgroundTasks:** Ingestion tasks run in background threads managed by FastAPI's `BackgroundTasks` execution loop, calling `asyncio.to_thread` / `loop.run_in_executor`.
* **State Persistence:** Job state is maintained in SQLite (`data/tender.db`) with retry loops and `PRAGMA journal_mode=DELETE`/`WAL` to avoid locking during concurrent writes.
* **Boot-Time Job Recovery:** In [`backend/app/main.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/main.py#L86-L107), a startup task automatically scans SQLite for any jobs stuck in `pending` or `processing` (e.g., following a server restart or crash) and re-queues them into the background pipeline.

---

## 3. Complete API Surface (FastAPI)

All endpoints are registered under [`backend/app/main.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/main.py) via modular routers:

### 3.1 Document Ingestion & Project Management (`/tenders`)

| Method | Endpoint | Core Purpose | Request Schema / Params | Response Schema |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/tenders/upload` | Uploads PDF, saves locally/MinIO, creates job, triggers background ingest | `file: UploadFile` (multipart/form-data) | [`TenderUploadResponse`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/schemas/tender_project.py#L46) (`job_id`, `file_id`, `tender_id`, `status`) |
| `POST` | `/tenders/workspace/ingest` | Alias for single-call workspace upload & extraction | `file: UploadFile` (multipart/form-data) | [`TenderUploadResponse`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/schemas/tender_project.py#L46) |
| `POST` | `/tenders/process` | Re-triggers or polls processing for a given job | [`TenderProcessRequest`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/schemas/tender_project.py#L55) (`job_id`, `file_id`, `tender_id`, `email`) | [`TenderProcessResponse`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/schemas/tender_project.py#L70) (`status`, `message`) |
| `POST` | `/tenders` | Creates a new Tender Project record in PostgreSQL | [`TenderProjectCreate`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/schemas/tender_project.py#L5) (`project_id`, `tender_name`, `source_label`) | [`TenderProjectResponse`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/schemas/tender_project.py#L23) |
| `POST` | `/tenders/{tender_id}/documents` | Attaches additional child documents to a tender | `files: List[UploadFile]`, `document_type: Optional[str]` | JSON list of uploaded document metadata |
| `GET` | `/tenders/{tender_id}` | Retrieves tender metadata and all linked document records | `tender_id: str` (path) | [`TenderProjectDetailResponse`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/schemas/tender_project.py#L34) |
| `POST` | `/tenders/{tender_id}/documents/{document_id}/process` | Triggers standalone OCR pipeline for a document | `run_layoutlm: bool`, `force_reprocess: bool` | JSON confirmation with `processing_status` |

### 3.2 Workspace & Review Endpoints (`/tenders/workspace`)

| Method | Endpoint | Core Purpose | Request Schema / Params | Response Schema |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/tenders/workspace/list` | Returns list of all tender payloads for the workspace table | None | JSON Array of tender detail payloads |
| `GET` | `/tenders/workspace/{job_id}` | Fetches full conforming tender detail JSON (fields, sections, pages) | `job_id: str` (path) | Conforming Tender Detail JSON |
| `DELETE` | `/tenders/workspace/{job_id}` | Deletes job from SQLite, PostgreSQL, and removes files on disk | `job_id: str` (path) | `{"status": "success", "message": "..."}` |
| `GET` | `/tenders/workspace/{job_id}/infosheet/download` | Re-generates Excel spreadsheet from current state and downloads | `job_id: str` (path) | `FileResponse` (`.xlsx` binary stream) |
| `GET` | `/tenders/documents/{document_id}/download` | Downloads extracted child/parent document from disk | `document_id: str` (path) | `FileResponse` (raw PDF binary stream) |
| `PUT` | `/tenders/workspace/{job_id}/fields/{field_id}` | Updates a single field value; **records correction to few-shot memory** | `payload: FieldUpdateRequest` (`value: str`) | Updated Tender Detail JSON |
| `POST` | `/tenders/workspace/{job_id}/fields/{field_id}/verify` | Marks a specific field as human-verified | `job_id`, `field_id` (path) | Updated Tender Detail JSON |
| `POST` | `/tenders/workspace/{job_id}/review` | Finalizes review, marks all fields verified, sets reviewer name | `payload: ReviewCompleteRequest` (`reviewer_name: str`) | Updated Tender Detail JSON |

### 3.3 Job Status, Downloads & Observability (`/jobs`, `/job`, `/health`, `/api`)

| Method | Endpoint | Core Purpose | Request / Response |
| :--- | :--- | :--- | :--- |
| `GET` | `/jobs/{job_id}` | Unified job status check | Response: [`JobStatusResponse`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/schemas/tender_project.py#L78) |
| `GET` | `/jobs/{job_id}/download` | Downloads generated Layer 1 summary CSV or Layer 2 evidence CSV | Param: `format: "summary" \| "evidence"`; Response: `FileResponse` |
| `GET` | `/job/{job_id}/status` | Legacy job status dictionary | Raw SQLite job row |
| `GET` | `/job/{job_id}/result` | Reads `ocr_result.json` | JSON aggregate result |
| `GET` | `/job/{job_id}/raw-ocr` | Reads `raw_ocr.json` (word-level boxes) | JSON word bounding boxes |
| `GET` | `/job/{job_id}/layout` | Reads `layout.json` (layout regions) | JSON region bounding boxes |
| `GET` | `/job/{job_id}/extracted-fields`| Reads `extracted_fields.json` | JSON field extractions |
| `GET` | `/health` & `/api/health` | Comprehensive multi-system health probe | Response: Status of Postgres, Redis, MinIO, RAM, CPU load |
| `POST` | `/api/notify` | Dispatches message/alert to team Telegram bot | Request: `NotifyRequest` (`message: str`, `sender: str`) |

---

## 4. Data Models & Storage Architecture

### 4.1 Dual Database Storage Strategy

The system currently operates with a **dual database architecture**:

1. **SQLite (`data/tender.db`):** Lightweight, zero-latency local job queue state machine.
   * **Table `jobs`:**
     * `job_id` (TEXT, PK), `status` (TEXT: pending/processing/completed/failed)
     * `original_filename` (TEXT), `pdf_path` (TEXT), `result_path` (TEXT), `page_count` (INT)
     * `error_message` (TEXT), `created_at` (TEXT), `started_at` (TEXT), `completed_at` (TEXT)
     * `email_recipient` (TEXT), `tender_id` (INTEGER)
   * Managed via [`job_store.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/repositories/job_store.py) and [`migrations.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/repositories/migrations.py).

2. **PostgreSQL (`tender_db` via SQLAlchemy):** Relational enterprise entity storage.
   * **`tender_projects`:** Grouping container for a tender project.
     * `id` (String(36) UUID, PK), `project_id` (String(255), Index), `tender_name` (String(255)), `source_label` (String(255)), `created_at`, `updated_at`.
   * **`documents`:** Linked files associated with a tender.
     * `id` (String(36) UUID, PK), `tender_project_id` (FK `tender_projects.id`, ON DELETE CASCADE).
     * `original_filename`, `storage_bucket`, `storage_key`, `mime_type`, `size_bytes`, `upload_status`, `processing_status`, `document_type` (`parent` or `child_document`), `created_at`, `updated_at`.
   * **`tender_information`:** Comprehensive normalized procurement schema (70+ columns).
     * **Identities:** `tender_id` (Unique, Index), `tender_name`, `nit_number`, `client`, `department`, `organization`.
     * **Dates:** `publish_date`, `pre_bid_meeting_date`, `bid_submission_start_date`, `bid_submission_end_date`, `bid_opening_date`.
     * **Financials:** `estimated_cost`, `emd_amount`, `emd_required`, `emd_mode` (ARRAY(String)), `tender_fee`, `tender_fee_mode` (ARRAY(String)), `processing_fee_amount`, `processing_fee_mode` (ARRAY(String)), `security_deposit`, `sd_percentage`, `sd_duration`, `sd_mode`, `pbg_percentage`, `pbg_duration`, `pbg_mode`.
     * **Eligibility Criteria:** `technical_experience`, `financial_turnover`, `avg_annual_turnover_value`, `avg_annual_turnover_type`, `working_capital_value`, `working_capital_type`, `solvency_certificate_value`, `solvency_certificate_type`, `net_worth_value`, `net_worth_type`, `order_value_1`, `order_value_2`, `order_value_3`, `maf_required`, `oem_authorization`, `oem_experience`, `certifications_required`.
     * **Commercial & Delivery:** `payment_terms_supply`, `payment_terms_installation`, `delivery_time_supply`, `delivery_time_installation_days`, `delivery_time_installation_inclusive`, `liquidated_damages_percentage`, `maximum_ld_cap`, `reverse_auction_applicable`.
     * **Contacts & Courier:** `contact_person`, `email`, `phone`, `address`, `courier_name`, `courier_phone`, `courier_address_line_1`, `courier_address_line_2`, `courier_city`, `courier_state`, `courier_pincode`, `courier_address`.
   * **`jobs` (Postgres model):** `job_id` (UUID PK), `status`, `file_path`, `email_recipient`, `error_message`, `created_at`, `updated_at`.

### 4.2 Object Storage: The MinIO Shim

In [`backend/app/core/minio.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/core/minio.py), `minio_client` is implemented as a **`LocalObjectStore`**:
* Replicates the `minio.Minio` client methods (`put_object`, `fget_object`, `list_objects`, `make_bucket`, `bucket_exists`, `remove_object`).
* Directs storage to local filesystem disk under `STORAGE_ROOT/objects/{bucket_name}/{key}`.
* Enforces directory traversal protection (`..` escape guards).
* Can be hot-swapped for a live MinIO / AWS S3 client without changing caller service logic.

### 4.3 Vector & Graph Database Integration State

* **Vector Databases (pgvector, Qdrant, Chroma):** **Not yet integrated into runtime code.** Conceptual references exist in roadmap documentation (`docs/scope_wk1to2.md`), but no embedding models or vector indices are currently running in the ingest pipeline.
* **Graph Databases (Neo4j):** **Not present.** No graph relationship models or drivers are currently configured.

---

## 5. Extraction & Parsing Subsystem

```
                                  [Input PDF]
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
        [Native Digital Stream]                 [Scanned Image Stream]
        (PyMuPDF get_text/words)                (PyMuPDF 300 DPI Pixmap)
                    │                                     │
                    │                           [Image Preprocessing]
                    │                           (Contrast 2x, Sharpen)
                    │                                     │
                    │                           [Tesseract / PaddleOCR]
                    │                           (Bounding box text blocks)
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                       [Unified Spatial Text Blocks]
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
[Wingdings Checkbox Parser]  [Heuristic Layout Detector]  [PDF Hyperlink Resolver]
  - \uf050 (Checked)           - Paragraph bounding boxes    - page.get_links()
  - \uf04f (Unchecked)         - Multi-column tables         - Bounding box matching
  - Euclidean label match      - Table grid reconstruction   - Session warm-up download
         │                             │                             │
         └─────────────────────────────┼─────────────────────────────┘
                                       │
                                       ▼
                        [Layer 1: Deterministic Rules]
                        - Field Registry keywords (synonyms)
                        - Clause-level anchor slicing (BDS, IFB)
                        - Precedence: ATC Authoritative overrides
                                       │
                                       ▼
                        [Are any critical fields missing?]
                                ├── No ──► [Generate InfoSheet & DB Record]
                                │
                                └── Yes ─► [Layer 2: LLM Field Resolver]
                                             - Gemini 2.5 Flash / Groq
                                             - GAIL/GeM Domain Instruction
                                             - Few-Shot Memory Injection
                                             - Non-hallucination validation
                                             │
                                             ▼
                                    [Merge Validated Fields]
                                             │
                                             ▼
                             [Generate Stylized Excel InfoSheet]
                             [Persist Conforming JSON & PostgreSQL]
```

### 5.1 Geometry & Bounding Box Extraction

The pipeline preserves exact 2D pixel coordinates across all stages:
* **`TextBlock` Schema:** `{ block_id, text, confidence, bounding_box: {x1, y1, x2, y2}, language_hint }`.
* **Reading Order Sorting:** Lines are clustered using vertical proximity ($\pm 12\text{pt}$ tolerance) and columns sorted horizontally ($x_1$).
* **Table Grid Reconstruction:** [`ocr/table_grid_parser.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/ocr/table_grid_parser.py) reconstructs structured matrix rows and columns from overlapping cell boxes.
* **LayoutLM Integration:** [`ocr/layout/layoutlm_stage.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/ocr/layout/layoutlm_stage.py) tokenizes bounding boxes normalized to $[0, 1000]$ for LayoutLM token classification (with rule-based fallback if PyTorch is unavailable).

### 5.2 Layer 2: LLM Resolver & Continuous Learning Memory

The LLM resolution engine in [`backend/app/services/llm_field_resolver.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/services/llm_field_resolver.py):
* **Domain Knowledge Prompting:** System prompt encodes deep knowledge of Indian PSU tenders (GAIL GCC-Goods Rev.1, BDS Section-III second occurrence, IFB tags A–H, Price Reduction Schedule vs. Liquidated Damages terminology).
* **Multi-Provider Fallback:**
  1. Primary: Google Gemini (`gemini-2.5-flash`) via `google-genai` SDK v2 structured JSON schema.
  2. Secondary: Groq API (`llama-3.3-70b-versatile`) via OpenAI-compatible endpoint.
* **Continuous Learning Memory:**
  * Memory store at `storage/llm_memory/extraction_memory.json`.
  * When a human reviewer edits a field in the frontend UI (`PUT /tenders/workspace/{job_id}/fields/{field_id}`), `record_correction()` writes the anchor context and correct value into the few-shot memory store.
  * Subsequent extractions inject these verified corrections directly into the LLM prompt.

---

## 6. Identified Gaps vs. Production Readiness

### 6.1 Architectural Gaps Summary Table

| Subsystem | Current State | Production Readiness Gap | Recommended Architecture |
| :--- | :--- | :--- | :--- |
| **Task Queue** | In-process `FastAPI.BackgroundTasks` & threads | No process isolation, tasks lost if container restarts mid-OCR, no rate limiting, cannot scale horizontally across worker nodes. | Migrate to **Celery + Redis** or **Temporal.io** with dedicated OCR worker pools. |
| **Object Storage** | `LocalObjectStore` disk shim | Stores files in local directory; fails in multi-replica / containerized deployments without shared persistent volumes. | Connect directly to live **MinIO cluster / AWS S3** using official `boto3` / `minio` client SDKs. |
| **Database Architecture** | Hybrid SQLite (`jobs.db`) + PostgreSQL | Split-brain state management; two different database engines holding overlapping job metadata. | Consolidate entirely into **PostgreSQL** with Celery task state backend in Redis. |
| **DB Migrations** | `Base.metadata.create_all()` + raw SQLite try-except | No schema versioning, risky live DDL alterations, no rollback capabilities. | Establish formal **Alembic** migration scripts for all PostgreSQL schema evolution. |
| **Authentication & AuthZ** | None (All endpoints public) | No user identities, no JWT tokens, no RBAC (Admin vs. Reviewer), no tenant isolation. | Implement **FastAPI OAuth2 with JWT tokens** and organization-level row security. |
| **Vector / Semantic Search** | None | Users cannot query across tenders, ask natural language questions, or do clause similarity search. | Deploy **pgvector** or **Qdrant** with chunked embedding pipeline (e.g. `text-embedding-3-small`). |
| **Resilience & Dead Lettering**| String error messages in job store | No automatic retry backoff for OCR/network timeouts, no Dead Letter Queue (DLQ). | Implement exponential backoff retries with Celery/Redis DLQ and Prometheus alerting. |
| **CORS & Security** | Wildcard `*` in CORS origins | Security vulnerability in production environment. | Restrict CORS strictly to verified staging and production domain origins in `.env`. |

---

## 7. Strategic Recommendations for Next Milestone

1. **Worker Decoupling:** Extract `ocr/pipeline.py` and `backend/app/services/pdf_parent_ingest.py` into standalone Celery task workers consuming from a Redis queue.
2. **PostgreSQL Consolidation:** Deprecate `data/tender.db` (SQLite) and route all job status tracking through the PostgreSQL `jobs` table using SQLAlchemy async sessions.
3. **Switch Storage to Real S3/MinIO:** Flip `minio_client` from the `LocalObjectStore` shim to standard `boto3` S3 client targeting the MinIO container (`minio:9000`).
4. **Vector Search Layer (RAG):** Introduce `pgvector` alongside the existing PostgreSQL database to index parsed layout text blocks and enable cross-tender compliance search.

