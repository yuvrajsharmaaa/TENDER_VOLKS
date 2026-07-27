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
