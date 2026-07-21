# VolksEnergies Tender Volks Engine — Audit, Extraction & Workspace Platform

> **System Overview:**  
> The **Tender Volks Engine** is an enterprise-grade, locally runnable, structure-aware OCR, metadata extraction, and workspace review platform specifically engineered for Indian Government & Public Sector Tender documents (GeM, PWD, Railways, Central/State authorities).

---

## 🏗️ Current Project Structure

```
Tender_Volks/
├── backend/                        # FastAPI Backend Application
│   ├── app/
│   │   ├── api/                    # API Routers & Controllers
│   │   │   ├── upload.py           # Unified PDF Upload & Processing Trigger (/tenders/upload, /tenders/process)
│   │   │   ├── jobs.py             # Enriched Job Status Tracking & Data Downloads (/jobs/{job_id})
│   │   │   ├── visualizer.py       # High-Fidelity OCR & Layout Visualizer Router
│   │   │   └── routes/
│   │   │       ├── health.py       # System Health Endpoint (/health)
│   │   │       └── tenders.py      # Workspace Detail, Review, Verification & Download Routes
│   │   ├── core/                   # Infrastructure Core
│   │   │   ├── config.py           # Application Settings & Pydantic Config
│   │   │   ├── constants.py        # Constants, Job Status Enums, STORAGE_ROOT
│   │   │   ├── logging.py          # Structured JSON Logging Setup
│   │   │   ├── minio.py            # MinIO S3 Object Storage Client
│   │   │   └── request_id.py       # Request ID Tracing Middleware
│   │   ├── db/                     # Database Layer
│   │   │   ├── session.py          # SQLAlchemy PostgreSQL/SQLite Session Manager
│   │   │   └── migrations.py       # Migration Utilities
│   │   ├── models/                 # SQLAlchemy ORM Models
│   │   │   ├── tender_project.py   # TenderProject Model
│   │   │   ├── document.py         # Document Model (Parent & Child Documents)
│   │   │   ├── tender_information.py # Layer 1 Mapped Tender Summary Model
│   │   │   └── job.py              # Background Processing Job Model
│   │   ├── repositories/           # Data Repositories
│   │   │   ├── job_store.py        # SQLite Job Tracker Repository (WAL mode)
│   │   │   └── migrations.py       # DB Initialization Utilities
│   │   ├── schemas/                # Pydantic Request/Response Schemas
│   │   │   └── tender_project.py   # Unified Response Models (TenderUploadResponse, JobStatusResponse, etc.)
│   │   ├── services/               # Core Business Services
│   │   │   ├── pdf_parent_ingest.py# Parent Tender Ingest & Synthesis Orchestrator
│   │   │   ├── pdf_text_extractor.py # Hybrid PDF Text Extractor (PyMuPDF + PaddleOCR)
│   │   │   ├── pdf_link_extractor.py # Hyperlink & Mention Extraction Engine
│   │   │   ├── field_extractor.py  # Structured 6-Category Field Extraction Engine
│   │   │   ├── field_registry.py   # Field Definitions & Categorization Rules
│   │   │   ├── info_sheet_generator.py # Formatted Excel (.xlsx) InfoSheet Generator
│   │   │   ├── tender_mapper.py    # Schema Normalization & Payload Mapper
│   │   │   ├── storage.py          # Storage Service (MinIO S3 / Local Disk)
│   │   │   └── email_service.py    # Automatic Email Dispatch Service
│   │   ├── workers/                # Background Processing Workers
│   │   │   └── ocr_task.py         # Async Background Pipeline Workers
│   │   └── main.py                 # FastAPI Application Entry Point & Lifespan Hooks
│   ├── Dockerfile                  # Backend Containerization Specs
│   └── requirements.txt            # Python Dependencies
│
├── frontend/                       # React + TypeScript + Vite Workspace Frontend
│   ├── src/
│   │   ├── App.tsx                 # Main Workspace View (Live Polling, Filter Bar, Stats, Card Grid)
│   │   ├── main.tsx                # React Root Entry Point
│   │   ├── components/
│   │   │   └── workspace/          # UI Components
│   │   │       ├── WorkspaceHeader.tsx   # Top Navigation, Search & Filter Bar
│   │   │       ├── TenderCard.tsx        # Summary Card Component for Tender Grid
│   │   │       ├── TenderDetailPane.tsx    # Split View Detail & Document Inspection Panel
│   │   │       ├── InfoSheetSectionView.tsx # Editable & Verifiable InfoSheet Field Renderer
│   │   │       ├── DocumentListTab.tsx    # Source, Linked & Mentioned Document Attachments
│   │   │       └── UploadModal.tsx        # Drag-and-Drop Tender PDF Upload Modal
│   │   ├── services/
│   │   │   ├── api.ts              # API Service Adapter (Backend Communication & Fallbacks)
│   │   │   └── storage.ts          # Storage Helpers
│   │   └── types/
│   │       └── tender.ts           # Frontend TypeScript Domain Types (TenderDetail, InfoSheetSection, etc.)
│   ├── package.json                # Frontend Node Dependencies
│   └── vite.config.ts              # Vite Bundler Configuration
│
├── ocr/                            # Standalone OCR & Extraction Module
│   ├── pipeline.py                 # Low-level OCR Pipeline (pdf2image + PaddleOCR / Layout Analysis)
│   └── ...
│
├── storage/                        # Persistent Local Storage Directory
│   └── jobs/                       # Job Folders ({job_id}/original.pdf, tender_detail.json, InfoSheet.xlsx)
│
├── sample_files/                   # Sample Indian Government Tender PDFs (GeM, PWD, etc.)
├── scratch/                        # Temporary & Verification Scripts (e.g. test_api_contract.py)
├── pyproject.toml                  # Python Project Metadata
└── README.md                       # Main Engineering Documentation
```

---

## ⚡ Technical Stack & Architecture

### Backend Tech Stack
* **Framework**: FastAPI (Python 3.11) with Pydantic v2 validation and async lifecycle hooks.
* **OCR & Computer Vision**: PyMuPDF (`fitz`), `PaddleOCR` (English & Hindi support), `pdf2image`.
* **Persistence Layer**: 
  * **SQLite** (`job_store.py` in WAL mode) for lightweight, thread-safe background job state tracking.
  * **PostgreSQL / SQLAlchemy** for relational metadata persistence (`TenderProject`, `Document`, `TenderInformation`).
* **Storage Layer**: Hybrid local filesystem (`STORAGE_ROOT/jobs/{job_id}/`) and MinIO S3 object storage.
* **Workbook Engine**: `openpyxl` for multi-tab Excel (`.xlsx`) InfoSheet generation.

### Frontend Tech Stack
* **Framework**: React 18 + TypeScript + Vite.
* **Styling**: Vanilla CSS / Tailwind CSS for modern glassmorphic dashboard design.
* **Icons**: `lucide-react`.

---

## 🔗 Unified API Contract & Flow

All endpoints operate under a unified identifier model where **`job_id` $\equiv$ `file_id` $\equiv$ `tender_id`**, ensuring deterministic handoffs across upload, tracking, review, and download steps.

```
┌─────────────────┐       POST /tenders/upload       ┌──────────────────────┐
│  Client / UI    │─────────────────────────────────►│  FastAPI Backend     │
└────────┬────────┘                                  └──────────┬───────────┘
         │                                                      │
         │  Returns { job_id, file_id, tender_id, status }     │ Auto-enqueues
         │◄─────────────────────────────────────────────────────┤ _run_ingest_background
         │                                                      │
         │  GET /jobs/{job_id} (Polling)                        ▼
         │─────────────────────────────────────────────────►┌──────────────────────┐
         │  Returns { status: "completed", workspace_url } │  OCR & Extraction    │
         │◄─────────────────────────────────────────────────│  Pipeline            │
         │                                                  └──────────────────────┘
         │  GET /tenders/workspace/{job_id} (Review)
         │─────────────────────────────────────────────────►
         │  Returns full TenderDetail JSON payload
         │
         │  PUT /tenders/workspace/{job_id}/fields/{field_id} (Edit field)
         │─────────────────────────────────────────────────► (Saves JSON & regenerates .xlsx)
         │
         │  GET /tenders/workspace/{job_id}/infosheet/download
         │─────────────────────────────────────────────────► Streams valid .xlsx workbook
```

### Key API Endpoint Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | System status check. |
| `POST` | `/tenders/upload` | Uploads PDF, registers job, and enqueues background OCR processing. Returns unified `job_id`, `file_id`, `tender_id`. |
| `POST` | `/tenders/workspace/ingest` | Workspace upload endpoint (fully unified with `/tenders/upload`). |
| `POST` | `/tenders/process` | Triggers or queries processing pipeline state for a given `job_id` / `file_id` / `tender_id`. |
| `GET` | `/jobs/{job_id}` | Returns enriched job status including `status`, `original_filename`, `workspace_url`, and dates. |
| `GET` | `/tenders/workspace/list` | Returns list of all tenders for the workspace grid (includes pending skeletons & completed details). |
| `GET` | `/tenders/workspace/{job_id}` | Retrieves full conforming tender detail JSON object for workspace inspection. |
| `PUT` | `/tenders/workspace/{job_id}/fields/{field_id}` | Updates an extracted field value, updates issue count, and regenerates the `.xlsx` InfoSheet. |
| `POST` | `/tenders/workspace/{job_id}/fields/{field_id}/verify` | Marks a field as verified and regenerates the InfoSheet. |
| `POST` | `/tenders/workspace/{job_id}/review` | Marks overall tender review completed (`review_status: "completed"`). |
| `GET` | `/tenders/workspace/{job_id}/infosheet/download` | Regenerates and downloads the formatted `.xlsx` InfoSheet workbook. |
| `GET` | `/tenders/documents/{document_id}/download` | Downloads source, linked, or extracted child documents. |
| `DELETE`| `/tenders/workspace/{job_id}` | Deletes job directory from disk, SQLite job store, and PostgreSQL tables. |

---

## 📊 Extracted InfoSheet Pipeline

The extraction pipeline organizes parsed tender attributes into **6 structured categories**:

1. **Basic Information**: Tender Name/Title, NIT Reference ID, Authority Agency, Department, Site Location.
2. **Commercials & Pricing**: Estimated Tender Value, EMD Amount & Payment Mode, Tender Fee & Payment Mode, Processing Fee.
3. **Eligibility Criteria**: Minimum Annual Turnover, Experience Years, Order Values (1/2/3), Solvency, Net Worth, MAF requirement.
4. **Project Execution**: Delivery/Completion Period, Installation Days, Payment Terms.
5. **Bank Guarantees & EMD**: Performance Security (PBG %), Security Deposit (SD %), EMD Exemption rules.
6. **Terms & Conditions**: Liquidated Damages (LD % per week), Max LD %, Reverse Auction applicability.

---

## 🚀 How to Run Locally

### Prerequisites
* Python 3.10 or 3.11
* Node.js v18+ and npm
* Poppler / PyMuPDF libraries (installed automatically via `requirements.txt`)

### 1. Start Backend Server
```powershell
# Navigate to workspace root
cd c:\Users\Asus\Desktop\Tender_Volks\main

# Install dependencies if needed
pip install -r backend/requirements.txt

# Start FastAPI server on port 8000
python -m uvicorn backend.app.main:app --reload --port 8000
```
* **Swagger API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **OCR Visualizer Tool**: [http://localhost:8000/visualizer](http://localhost:8000/visualizer)

### 2. Start Frontend Web Application
```powershell
# Navigate to frontend folder
cd c:\Users\Asus\Desktop\Tender_Volks\main\frontend

# Install dependencies if needed
npm install

# Start Vite development server
npm run dev
```
* Access the Workspace UI in your browser at `http://localhost:5173` (or the URL printed by Vite).

---

## 🧪 Verification & Integration Testing

To run the automated end-to-end API contract test suite:

```powershell
python scratch/test_api_contract.py
```

This script verifies PDF upload, job tracking, workspace inspection, field editing, verification, review completion, and Excel InfoSheet generation against real GeM tender files.
