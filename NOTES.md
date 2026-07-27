# Pipeline Observations & Recommendations (Non-Scoped Items)

## 1. PyMuPDF Deprecation Warnings
- **File**: `backend/app/services/pdf_text_extractor.py:146`
- **Observation**: PyMuPDF deprecated `page.get_text()` string call without flags in upcoming 2.0 release in favor of explicit flags.
- **Recommendation**: Standardize on `page.get_text("text")` or `page.get_text("dict")` across all ingestion services.

## 2. Pydantic V2 Config Migration
- **File**: `backend/app/schemas/tender_project.py:11`
- **Observation**: Legacy `class Config:` inner classes trigger `PydanticDeprecatedSince20` warnings under Pydantic 2.13+.
- **Recommendation**: Migrate schemas to `model_config = ConfigDict(...)`.

## 3. Wingdings Character Map Extension
- **File**: `backend/app/services/pdf_text_extractor.py:246`
- **Observation**: Extended Wingdings fonts (Wingdings 3) in older scanned PDFs use alternative unicode private use areas for checkboxes.
- **Recommendation**: Maintain a centralized `WINGDINGS_CHECKBOX_MAP` dictionary for multi-font document pipelines.

## 4. Frontend Reprocess Parameter Integration (Task 1 Follow-Up)
- **Files**: `frontend/src/services/api.ts:673` (`triggerProcessing`), `frontend/src/App.tsx:124`
- **Observation**: The frontend `apiService.triggerProcessing(selectedTenderId)` method currently calls `POST /tenders/.../process` without query parameters.
- **Recommendation**: Update `triggerProcessing` signature to `triggerProcessing(tenderId: string, forceReprocess: boolean = false)` and append `?force_reprocess=true` when a user clicks the "Re-ingest" / "Refresh" button on an already-completed document.

## 5. Additional Binary Clause Checkbox Precedence (Task 2 Follow-Up)
- **Files**: `backend/app/services/tender_mapper.py:395` (`resolve_atc_anchor_fields`)
- **Observation**: Wingdings2 checkbox detection was integrated with priority precedence for Clause 38 (`sd_required`). Other binary APPLICABLE / NOT APPLICABLE tables (e.g. EMD Exemption for MSE/Startup in Section-I) currently extract via main cover page key-value pairs (`MAIN_SOURCED_LABELS`).
- **Recommendation**: Expand Wingdings checkbox matching to Section-I BEC tables for MSE/Startup exemption verification if scanned annexures omit plain text labels.
