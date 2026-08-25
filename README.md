
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
| **Fine-Tuning & SFT**| [Unsloth](https://github.com/unslothai/unsloth), `transformers`, `trl`, `peft` | Latest | 4-bit LoRA fine-tuning of `Qwen2.5-7B-Instruct` with assistant-only loss masking |
| **Quant & Deploy**  | GGUF (Q4_K_M / Q8_0), [Ollama](https://ollama.com/) | Latest | Local GGUF quantization and strict JSON inference deployment |
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
├── data/                            # Processed Datasets & Corpora
│   └── processed/
│       ├── tender_corpus_unannotated.txt # DAPT continuous pretraining text corpus (~438 MB)
│       ├── dataset_sft.jsonl            # Unified SFT instruction tuning dataset (12 pairs, UTF-8)
│       ├── sft_train.jsonl              # Training set split (10 records, 83.3%)
│       └── sft_val.jsonl                # Validation set split (2 records, 16.7%)
├── frontend/                        # Modern React 19 + TypeScript + Vite + TailwindCSS Workspace UI
├── gold_standard/                   # Evaluation ground truth datasets, audit dumps & test PDFs
├── scripts/                         # CLI utilities, dataset builders & validation suites
│   ├── build_dapt_corpus.py         # DAPT corpus builder with multi-tier table grid parsing
│   ├── build_sft_dataset.py         # Multi-source SFT dataset merger & deduplicator
│   ├── split_and_validate_sft.py    # Train/Val splitter, quality check & Qwen token audit
│   └── verify_env.py                # System environment & dependency diagnostic tool
└── verify_sft.py                    # Standalone JSON & schema verification script
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

---

## 4. Extraction & Parsing Subsystem

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

---

## 5. Domain Adaptation & LLM Fine-Tuning Pipeline (DAPT & SFT)

To achieve **zero-preamble, strict-JSON field extractions** without relying solely on system prompt instructions, Tender Volks includes an end-to-end domain adaptation pipeline:

### 5.1 Domain-Adaptive Pre-Training (DAPT) Corpus Builder
Located in [`scripts/build_dapt_corpus.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/scripts/build_dapt_corpus.py):
* **Goal**: Converts raw GeM/GAIL/PSU procurement documents into a continuous pre-training corpus ([`data/processed/tender_corpus_unannotated.txt`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/data/processed/tender_corpus_unannotated.txt), **~438 MB**).
* **Multi-Tier Table Grid Parsing**:
  * *Tier 1*: Native `pdfplumber` cell extraction for bordered tables.
  * *Tier 2*: Spatial 2D Bounding-Box Grid Reconstruction (`reconstruct_grid`) for borderless and complex tables.
* **Font Corruption & Glyph Detection**: Identifies corrupted font maps (`(cid:X)`) and switches automatically to 300 DPI image enhancement + `pytesseract` (`lang="eng+hin"`).
* **Bilingual & Symbol Normalization**: Maps Wingdings checkbox characters (`\uf050` / `\uf0fe` $\rightarrow$ `[X]`, `\uf04f` $\rightarrow$ `[ ]`), preserves Indian currency (`₹`, Lakh, Crore), and strips headers/footers while retaining ~2,000-word table-safe chunk boundaries.

---

### 5.2 Supervised Fine-Tuning (SFT) Dataset Construction
Located in [`scripts/build_sft_dataset.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/scripts/build_sft_dataset.py):
* **Multi-Source Ingestion & Merging**:
  1. *SOURCE 1 (Primary)*: Ground truth gold standard ([`gold_standard/ground_truth.json`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/gold_standard/ground_truth.json)).
  2. *SOURCE 2 (Secondary)*: Fresh pipeline audit dumps ([`gold_standard/fresh_pipeline_audit_dump.json`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/gold_standard/fresh_pipeline_audit_dump.json)). Filters out `"⚠️ MISSING"` sentinels and pipeline metadata keys (`_info_sheet_statuses`, `status_summary`, `missing_fields`, `_info_sheet_sources`).
  3. *SOURCE 3 (Supplementary)*: Few-shot memory store ([`backend/app/storage/llm_memory/extraction_memory.json`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/backend/app/storage/llm_memory/extraction_memory.json)). Groups entries by shared `anchor_text` requiring $\ge 2$ distinct fields and $\ge 30$ characters.
* **Deduplication & Hygiene**: Calculates SHA-256 hashes over normalized `(input + output)` strings and logs all skipped records to `logs/sft_skipped_records.log`.
* **Output Format**: Pure UTF-8 JSON-Lines (`data/processed/dataset_sft.jsonl`):
  ```json
  {
    "instruction": "Extract the critical procurement fields from the following tender clause into structured JSON.",
    "input": "Tender: GeM-Bidding-9062837\nOrganization: Gail India Limited\nFields to extract: ...",
    "output": "{\n  \"tender_id_display\": \"GEM/2026/B/7306631\",\n  \"emd_amount_display\": \"₹1,94,177\"\n}"
  }
  ```

---

### 5.3 Train/Val Dataset Metrics & Token Audit
Located in [`scripts/split_and_validate_sft.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/scripts/split_and_validate_sft.py) and [`verify_sft.py`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/verify_sft.py):
* **Data Splits**:
  * **Train Set** ([`data/processed/sft_train.jsonl`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/data/processed/sft_train.jsonl)): **10 records** (83.3%)
  * **Validation Set** ([`data/processed/sft_val.jsonl`](file:///c:/Users/Asus/Desktop/Tender_Volks/main/data/processed/sft_val.jsonl)): **2 records** (16.7%, held-out tender + multi-field clause sample)
* **Token Length Audit (`Qwen/Qwen2.5-7B-Instruct` Tokenizer)**:

| Metric | Input Tokens | Output (JSON) Tokens | Total Sequence Tokens |
| :--- | :--- | :--- | :--- |
| **Minimum** | 33 tokens | 25 tokens | **58 tokens** |
| **Median** | 242.5 tokens | 580.5 tokens | **823.0 tokens** |
| **Maximum** | 474 tokens | 1,696 tokens | **2,170 tokens** |

* **Compute Safety**: Maximum total sequence length is **2,170 tokens** — fitting comfortably within a **4,096 context budget** on a free **Google Colab T4 GPU (16 GB VRAM)** using Unsloth 4-bit LoRA.

---

### 5.4 Fine-Tuning (Unsloth), Quantization (GGUF) & Ollama Local Inference
1. **Loss Masking (`DataCollatorForCompletionOnlyLM`)**: Computes training loss **strictly on assistant JSON output tokens** (masking user instruction tokens), forcing the fine-tuned model to output clean JSON without preamble like *"Sure! Here's the JSON:"*.
2. **GGUF Quantization**: Converts fine-tuned LoRA weights to `Q4_K_M` and `Q8_0` GGUF formats for zero-latency local CPU/GPU inference via `llama.cpp`.
3. **Ollama Deployment**: Deploys via local Ollama `Modelfile` linking the fine-tuned GGUF model with the exact training system instruction.

---

## 6. CLI Quickstart & Data Pipeline Workflows

### 6.1 Run Environment Diagnostic
```bash
python scripts/verify_env.py
```

### 6.2 Build Domain-Adaptive Pre-Training (DAPT) Corpus
```bash
python scripts/build_dapt_corpus.py --input-dir tender-documents --output data/processed/tender_corpus_unannotated.txt
```

### 6.3 Build SFT Dataset from Multi-Source Extractions
```bash
python scripts/build_sft_dataset.py \
  --primary gold_standard/ground_truth.json \
  --audit-dump gold_standard/fresh_pipeline_audit_dump.json \
  --memory-file backend/app/storage/llm_memory/extraction_memory.json \
  --output-file data/processed/dataset_sft.jsonl \
  --min-chars 30 \
  --min-fields 2
```

### 6.4 Split Dataset & Run Data Quality / Qwen Token Audit
```bash
python scripts/split_and_validate_sft.py
```

### 6.5 Verify SFT Dataset Syntax & JSON Integrity
```bash
python verify_sft.py
```

### 6.6 Start Backend API Server
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6.7 Start Frontend Workspace UI
```bash
cd frontend
npm run dev
```

---

## 7. Identified Gaps vs. Production Readiness

### 7.1 Architectural Gaps Summary Table

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

## 8. Strategic Recommendations for Next Milestone

1. **Worker Decoupling:** Extract `ocr/pipeline.py` and `backend/app/services/pdf_parent_ingest.py` into standalone Celery task workers consuming from a Redis queue.
2. **PostgreSQL Consolidation:** Deprecate `data/tender.db` (SQLite) and route all job status tracking through the PostgreSQL `jobs` table using SQLAlchemy async sessions.
3. **Switch Storage to Real S3/MinIO:** Flip `minio_client` from the `LocalObjectStore` shim to standard `boto3` S3 client targeting the MinIO container (`minio:9000`).

