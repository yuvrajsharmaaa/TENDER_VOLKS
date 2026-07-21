# Tender Field Extraction & Merging Standards

## Document Source Provenance
Every extracted field object (`ExtractedFieldSchema`) produced during processing must explicitly declare a `source` tag from the following canonical set:
- `"main_tender"`: Field value extracted from the primary tender PDF.
- `"atc"`: Field value extracted from the Additional Terms and Conditions (ATC) PDF.
- `"derived"`: Field value dynamically calculated post-extraction (e.g., `emd_total`, `emd_required`).
- `"ambiguous_preserved"`: Composite payload created when both documents yield valid, unresolvable extractions for designated ambiguous fields.

## Field Precedence & Merging Protocols
1. **Explicit ATC Overrides**: An explicit non-null extraction from an ATC document (`atc_valid`) **always takes precedence** over `main_tender` extractions. Merging algorithms must not apply confidence-score carve-outs to override valid ATC clauses.
2. **Ambiguous Field Preservation**: Designated multi-source fields (`custom_eligibility_criteria`, `delivery_time_installation_inclusive`, `custom_rules`) must not be prematurely resolved when extracted from both sources. If both `main_tender` and `atc` produce valid extractions, preserve both candidates as a dictionary:
   `{"main_tender": main_val, "atc": atc_val}` with `source="ambiguous_preserved"`.
3. **Structured Audit Logging**: Every field merge operation must emit a standardized log entry structured as follows:
   `[FIELD_MERGE] Field: {field_name} | Winning Source: {winning_source} | Text Source: {text_source} | Page: {page_number} | Value: {value}`

## System Dependencies & Multi-Language OCR
- Setting `lang="eng+hin"` in `pytesseract` requires system dependency `tesseract-ocr-hin` (Hindi `hin.traineddata`). Ensure system diagnostics verify language pack availability before initializing OCR engines.

## Link-Based ATC Discovery & Resolver Standards
1. **Annotation-Based URL Resolution**: ATC target discovery must not rely on visible text alone. The pipeline must call `page.get_links()`, inspect `kind == fitz.LINK_URI`, match bounding box text via `page.get_textbox(l["from"])` or intersecting words, and extract the underlying URI annotation target.
2. **Download & Validation**: Downloaded targets must be validated as PDFs via magic bytes (`%PDF-`) or `Content-Type: application/pdf`.
3. **Structured Event Logging & Fallback**:
   - Log `ATC_LINK_NOT_FOUND` if anchor phrases exist without resolvable URI annotations.
   - Log `ATC_DOWNLOAD_FAILED` if target HTTP/HTTPS download fails.
   - Fallback gracefully to main tender parsing without crashing the job.

