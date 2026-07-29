# VolksEnergies Tender Volks Engine — Audit, Extraction & Workspace Platform

The **Tender Volks Engine** is an enterprise-grade, locally runnable, structure-aware OCR, metadata extraction, and workspace review platform specifically engineered for Indian Government & Public Sector Tender documents (GeM, PWD, GAIL, and other Central/State authorities).

---

## 🏗️ Project Layout & Structure

```
Tender_Volks/
├── backend/                        # FastAPI Backend Application
│   ├── app/
│   │   ├── api/                    # API Routers & Controllers
│   │   │   ├── upload.py           # Unified Ingest Trigger (/tenders/upload, /tenders/process)
│   │   │   ├── jobs.py             # Enriched Job Status Tracking & Downloads (/jobs/{job_id})
│   │   │   ├── visualizer.py       # High-Fidelity OCR & Layout Visualizer Router
│   │   │   └── routes/
│   │   │       ├── health.py       # System Health Endpoint (/health)
│   │   │       └── tenders.py      # Workspace Detail, Review, Verification & Download Routes
│   │   ├── core/                   # Infrastructure Core
│   │   │   ├── config.py           # Settings & Pydantic Config
│   │   │   ├── constants.py        # Constants & Job Status Enums
│   │   │   └── logging.py          # Structured JSON Logging
│   │   ├── db/                     # Database Layer
│   │   │   ├── session.py          # PostgreSQL/SQLite Session Manager
│   │   │   └── migrations.py       # Migration Utilities
│   │   ├── models/                 # SQLAlchemy ORM Models
│   │   ├── repositories/           # SQLite Job Tracker Repository (WAL mode)
│   │   ├── services/               # Core Ingestion, OCR & Extraction Services
│   │   │   ├── pdf_parent_ingest.py# Ingest Orchestrator & Link Resolver
│   │   │   ├── llm_field_resolver.py # google-genai v2 Hybrid Fallback Layer
│   │   │   ├── pdf_text_extractor.py # PyMuPDF + PaddleOCR Hybrid Extractor
│   │   │   ├── pdf_link_extractor.py # Anchor URL Detection Engine
│   │   │   ├── tender_mapper.py    # Merging Precedence & Normalization Engine
│   │   │   └── info_sheet_generator.py # openpyxl Excel InfoSheet Builder
│   │   └── main.py                 # FastAPI Entry Point
│   ├── Dockerfile                  # Container Spec
│   └── requirements.txt            # Python Dependencies
│
├── frontend/                       # React + TypeScript + Vite Workspace Dashboard
│   ├── src/
│   │   ├── App.tsx                 # Main Workspace View (Live Polling, Grid, Stats)
│   │   └── components/
│   │       └── workspace/          # WorkspaceHeader, TenderCard, TenderDetailPane, InfoSheetSectionView
│   ├── package.json                # Frontend Node Dependencies
│   └── vite.config.ts              # Vite Config
│
├── ocr/                            # Standalone OCR & Extraction Module
├── storage/                        # Persistent Storage (Jobs, LLM Few-Shot Store)
└── sample_files/                   # Sample Indian Government Tender PDFs
```

---

## ⚡ Technical Stack & Architecture

### Backend Tech Stack
* **Framework**: FastAPI (Python 3.11) with Pydantic v2 validation.
* **OCR & Computer Vision**: PyMuPDF (`fitz`), `PaddleOCR` (English & Hindi), `pdf2image`, Tesseract OCR fallback.
* **Persistence Layer**: 
  * **SQLite** (WAL mode) for lightweight background job tracking.
  * **PostgreSQL / SQLAlchemy** for relational metadata persistence.
* **Workbook Engine**: `openpyxl` for multi-tab Excel (`.xlsx`) InfoSheet generation.

### Frontend Tech Stack
* **Framework**: React 18 + TypeScript + Vite.
* **Styling**: Vanilla CSS / Tailwind CSS for modern glassmorphic dashboard.

---

## 🔗 Unified API Contract & Flow

All endpoints operate under a unified identifier model where **`job_id` $\equiv$ `file_id` $\equiv$ `tender_id`**, ensuring deterministic handoffs.

```
┌─────────────────┐       POST /tenders/upload       ┌──────────────────────┐
│  Client / UI    │─────────────────────────────────►│  FastAPI Backend     │
└────────┬────────┘                                  └──────────┬───────────┘
         │                                                      │
         │  Returns { job_id, file_id, tender_id, status }     │ Auto-enqueues
         │◄─────────────────────────────────────────────────────┤ Ingestion Pipeline
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
| `POST` | `/tenders/upload` | Uploads PDF, registers job, and enqueues background processing. |
| `GET` | `/jobs/{job_id}` | Returns enriched job status including logs and workspace status. |
| `GET` | `/tenders/workspace/list` | Returns list of all tenders for the workspace grid. |
| `GET` | `/tenders/workspace/{job_id}` | Retrieves conforming tender detail JSON. |
| `PUT` | `/tenders/workspace/{job_id}/fields/{field_id}` | Updates field value, updates issues, and regenerates the InfoSheet. |
| `GET` | `/tenders/workspace/{job_id}/infosheet/download` | Downloads the generated `.xlsx` workbook. |

---

## ⚙️ Core Ingestion & Extraction Engine

Our pipeline processes both primary tenders and secondary Additional Terms and Conditions (ATC) documents using strict merging and validation protocols:

### 1. Merging & Precedence Rules
- **ATC Authoritative**: Operational variables (e.g. Payment Terms %, Delivery Time, EMD Amount, Courier Address, Client Contacts) extracted from the ATC document take precedence over those in the main tender, ignoring empty or stub values (`0.0`).
- **Main Tender Ownership**: Identifiers (e.g. NIT No, Tender Title, Bid Validity Days) are owned strictly by the main tender.
- **Ambiguous Preservations**: Designated multi-source fields (e.g. `custom_eligibility_criteria`, `custom_rules`) preserve extractions from both sources in a structured dictionary with `source="ambiguous_preserved"`.

### 2. ATC Link Discovery & Resolver
- **PDF Annotation Resolution**: Parses URI annotations (`page.get_links()`) and maps bounding boxes containing phrases like "Click here" to detect embedded ATC download targets.
- **PDF Verification**: Every download is validated using PDF magic bytes (`b"%PDF"`) and refereed download headers.

### 3. PSU Layout Heuristics
- **EMD Instruments**: Parses phrases into standardised abbreviations (`DD`, `BG`, `BT`, `SB`, `FDR`).
- **Exemptions**: Auto-exempts financial fields if "financial criteria: not applicable" is detected in the BEC.
- **Delivery Timeline**: Formats completion durations (e.g. `3 months` -> `90 Days`).
- **SITC Mode Detection**: Automatically distinguishes goods supply from SITC (Supply, Installation, Testing, and Commissioning) to apply correct installation timelines.

---

## 🤖 LLM Fallback Layer (`llm_field_resolver.py`)

If rule-based regex fails to resolve a field, the pipeline routes extraction requests to **Google Gemini**:

- **Google GenAI SDK (v2)**: Built on the modern `google.genai` Client framework.
- **Structured Outputs**: Integrates `response_schema` utilizing the `gemini-flash-lite-latest` model to constrain model output to type-safe JSON, eliminating format truncation and hallucination.
- **Few-Shot Learning Store**: Successful extractions accumulate in `extraction_memory.json` to bootstrap extraction precision.
- **Anti-Hallucination Guard**: Matches extracted terms back to the source text before mapping.

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.10 / 3.11
- Node.js v18+ & npm
- Tesseract OCR (with package `tesseract-ocr-hin` for Hindi OCR support)

### 1. Configuration
Configure `.env.dev` in the root directory:
```bash
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/tender_db
GEMINI_API_KEY=your-gemini-api-key
LLM_FALLBACK_ENABLED=true
```

### 2. Backend Setup
```bash
# Install dependencies
pip install -r backend/requirements.txt

# Start the FastAPI server (Port 8000)
python -m uvicorn backend.app.main:app --reload --port 8000
```
- **API Swagger Docs**: `http://localhost:8000/docs`
- **OCR Layout Visualizer**: `http://localhost:8000/visualizer`

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Access the dashboard at `http://localhost:5173`.

---

## 🧪 Testing & Verification

Run the automated test suite to verify extraction correctness:
```bash
# Run all unit tests
python -m pytest tests/unit
```
