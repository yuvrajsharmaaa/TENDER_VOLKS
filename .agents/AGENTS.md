# Tender Field Extraction & Merging Standards

## Document Source Provenance
Every extracted field object (`ExtractedFieldSchema`) produced during processing must explicitly declare a `source` tag from the following canonical set:
- `"main_tender"`: Field value extracted from the primary tender PDF.
- `"atc"`: Field value extracted from the Additional Terms and Conditions (ATC) PDF.
- `"derived"`: Field value dynamically calculated post-extraction (e.g., `emd_total`, `emd_required`).
- `"ambiguous_preserved"`: Composite payload created when both documents yield valid, unresolvable extractions for designated ambiguous fields.

## Field Precedence & Merging Protocols
1. **Explicit ATC Authoritative Overrides (`ATC_SOURCED_LABELS`)**:
   - An explicit, valid extraction from an ATC document for operational fields (e.g., `Processing Fee`, `Tender Fee`, `EMD Amount`, `Payment Terms %`, `Delivery Time`, `SD` fields, `LD` fields, `Courier Info`, `Client Contacts`) **always takes precedence** over `main_tender` extractions.
   - **Non-Zero / Non-Stub Protection**: An ATC extraction overrides main-doc values ONLY if the extracted ATC value is non-empty, non-zero, and non-stubbed (`val not in (None, "", "Not Found", "Out of Scope (Stage 1)", 0, 0.0, "0", "0.0", "0.00")`). Default stub zeroes (`0.0`) from non-financial ATC annexures must never overwrite valid primary tender values.
2. **Main Document Field Ownership (`MAIN_SOURCED_LABELS`)**:
   - Primary tender identification and qualification fields (`PBG Required`, `PBG Percentage`, `Eligibility Criterion (Years)`, `Bid Validity (Days)`, `Tender Title`, `NIT No`, `Estimated Tender Value`, `Organisation`, `Authority Agency`) must **never** be overridden by ATC extractions.
3. **Ambiguous Field Preservation (`AMBIGUOUS_LABELS`)**:
   - Designated multi-source fields (`custom_eligibility_criteria`, `delivery_time_installation_inclusive`, `custom_rules`) must not be prematurely resolved when extracted from both sources. If both `main_tender` and `atc` produce valid extractions, preserve both candidates as a dictionary:
     `{"main_tender": main_val, "atc": atc_val}` with `source="ambiguous_preserved"`.
4. **Structured Audit Logging**:
   - Every field merge operation must emit a standardized log entry structured as follows:
     `[FIELD_MERGE] Field: {field_name} | Old value: {old_val!r} | New value (atc): {val!r} | Reason: {reason}`

## System Dependencies & Multi-Language OCR
- Setting `lang="eng+hin"` in `pytesseract` requires system dependency `tesseract-ocr-hin` (Hindi `hin.traineddata`). Ensure system diagnostics verify language pack availability before initializing OCR engines.

## Link-Based ATC Discovery & Resolver Standards
1. **Annotation-Based URL Resolution**: ATC target discovery must not rely on visible text alone. The pipeline must call `page.get_links()`, inspect `kind == fitz.LINK_URI`, match bounding box text via `page.get_textbox(l["from"])` or intersecting words with +5pt padding tolerance, and extract the underlying URI annotation target.
2. **Image-Based Scanned Page OCR Fallback**: If native page text is unreadable or garbled (`is_text_scrambled_or_garbage`), lazily render the link bounding box and run Tesseract OCR (`lang="eng+hin"`) to verify anchor text ("Click here to view the file").
3. **Strict PDF Content & Magic Byte Validation**: Link anchor verification (`is_atc_anchor`) raises download priority, but **must NEVER bypass PDF magic byte validation** (`file_bytes.startswith(b"%PDF")` or `Content-Type: application/pdf`). Non-PDF responses (403 Forbidden pages, HTML login redirects) must be logged as `ATC_DOWNLOAD_INVALID` and skipped.
4. **Scope-Protected Download Logic**: Reject generic portal homepages (`https://gem.gov.in`, `https://mkp.gem.gov.in`) and limit unverified link downloads to explicit document extensions (`.pdf`, `.xlsx`, `.docx`, `.zip`) or known procurement document path endpoints (`/buyer-atc/`, `/doc/`, `/download/`). Unverified links are tagged with `extractionConfidence = 70.0` (vs `95.0` for verified anchors).
5. **HTTP Request Headers & Referer**: HTTP requests must include standard browser `User-Agent`, `Accept: application/pdf,*/*`, and `Referer: https://bidplus.gem.gov.in/` headers to handle session-gated portal endpoints gracefully.
6. **Structured Event Logging & Fallback**:
   - Log `ATC_LINK_NOT_FOUND` if anchor phrases exist without resolvable URI annotations.
   - Log `ATC_DOWNLOAD_FAILED` if target HTTP/HTTPS download fails or returns an HTTP status error.
   - Log `ATC_DOWNLOAD_INVALID` if target returns non-PDF content.
   - Log `ATC_PARSE_NO_FIELDS` if ATC PDF parses successfully but yields 0 mergeable fields.
   - Fallback gracefully to main tender parsing without crashing the job.
