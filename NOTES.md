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

## 6. Task 2 — Full-Text Unscoped Regex Audit Table
Audit of all 8 `re.search` calls in `backend/app/services/tender_mapper.py` operating over `full_text` for open-ended `.*?` / `[\s\S]*?` cross-contamination risks:

| # | File Location | Target Field / Feature | Current Pattern Snippet | Classification | Reasoning / Bounding Strategy |
|---|---|---|---|---|---|
| 1 | `tender_mapper.py:387` | Security Deposit % & Duration | `re.search(r"(\d+(?:\.\d+)?)\s*%\s*of\s+Total\s+Order.*?(\d+)\s*days\s*of\s+FOA", full_text, re.DOTALL)` | **RISKY** | Open-ended `.*?` across 450KB+ full_text matched startup eligibility 10% instead of Clause 38 SD 5%. Fixed: Bounded to Clause 38 / Security Deposit section boundary lookahead. |
| 2 | `tender_mapper.py:864` | Commercial Evaluation Methodology | `re.search(r"(?:K\.\s*EVALUATION\s+METHODOLOGY\|EVALUATION\s+METHODOLOGY).*?(?:Overall\s+L-?1\s+basis\|item-?wise\s+L-?1)", full_text, re.DOTALL)` | **RISKY** | Matched TOC heading on page 8 and jumped 20,655 chars across full_text to item-wise L-1. Fixed: Bounded search to 2500-char window from EVALUATION METHODOLOGY heading. |
| 3 | `tender_mapper.py:902` | MAF Qualifier | `re.search(r"(?:maf\|oem\s+authorization)[^\n]*?(project\s+specific\|item\s+specific\|category\s+specific)", full_text)` | **SAFE** | `[^\n]*?` strictly bounds matching to a single line, preventing cross-clause spanning across newlines. |
| 4 | `tender_mapper.py:953` | Delivery Time Installation (SITC Scope) | `re.search(r"(?:\(A\)\s*SCOPE OF SUPPLY\|SCOPE OF SUPPLY\|SCOPE OF PROCUREMENT).*?(?:SITC\|...)", full_text, re.DOTALL)` | **RISKY** | Open-ended `.*?` with DOTALL across full_text could match SCOPE OF SUPPLY on page 10 and SITC/Installation 100 pages later. Fixed: Bounded to 1500-char window from SCOPE OF SUPPLY heading. |
| 5 | `tender_mapper.py:1066` | PRS / LD Clause Fallback | `re.search(r"(?:PRICE REDUCTION SCHEDULE\|PRS)[\s\S]*?(\u00bd\|...)\%.*?per week.*?maximum\s*(\d+(?:\.\d+)?)\%", full_text)` | **RISKY** | Unscoped `[\s\S]*?` across full_text could match PRS in TOC or intro and jump pages to LD percentages. Fixed: Bounded search to 2500-char window from PRICE REDUCTION SCHEDULE / PRS heading. |
| 6 | `tender_mapper.py:1308` | Contact Details of Officer Block | `re.search(r"(?:CONTACT DETAILS OF TENDER DEALING OFFICER\|TENDER DEALING OFFICER)(.*?)(?:SECTION\|ANNEXURE\|3\.0\|4\.0\|\Z)", full_text, re.DOTALL)` | **SAFE** | Explicitly bounded by section/annexure/clause lookahead `(?:SECTION\|ANNEXURE\|3\.0\|4\.0\|\Z)`. |
| 7 | `tender_mapper.py:1460` | Cut-Out Slip Address | `re.search(r"(?:CUT-OUT SLIP\|CUT OUT SLIP\|DO NOT OPEN).*?TO[:\-\s]+(.*?)(?:FROM\|KIND ATTN\|QUOTATION\|\Z)", full_text, re.DOTALL)` | **RISKY** | `.*?TO[:\-\s]+` with DOTALL across full_text could match CUT-OUT SLIP header on page 15 and jump to TO: on page 100. Fixed: Bounded search to 1500-char window from CUT-OUT SLIP heading. |
| 8 | `tender_mapper.py:1585` | Custom Executed Order Value Broad Match | `re.search(r"Minimum\s+Executed\s+Order\s+Value.*?(Rs\.?\s*[\d\.\,\s]+(?:Lacs\|Lakhs\|Crore\|Cr)?)", full_text)` | **RISKY** | Open-ended `.*?` could match heading on one page and jump across lines/pages to "Rs." elsewhere. Fixed: Bounded search to 500-char window from Minimum Executed Order Value heading. |

## 7. ATC Stub-vs-Appendix Pointer Pattern Audit
Audit of ATC-sourced fields checked for GCC/SCC stub pointers vs target Appendix/SCC clauses in GAIL/GGL tenders:

| Field Name | GCC/SCC Primary Heading | Observed Stub Pointer Phrase | Authoritative Target Section | Audit Finding / Resolution |
|---|---|---|---|---|
| `payment_terms_supply` / `payment_terms_installation` | `19.0 PAYMENT TERMS` (GCC) / `16.0 PAYMENT TERMS AND MODE OF PAYMENT` (SCC) | `"19.1 Please refer SCC."` / `"16.1 As per Appendix-I"` | `[APPENDIX – I TO SPECIAL CONDITION OF CONTRACT] PAYMENT TERMS & MODE OF PAYMENT` | **CONFIRMED STUB**. Primary clause 19.1 contains no values. Resolver chases pointer to Appendix-I on page 127. Full invoice paid in 15 days; no percentage split stated. |
| `prs_ld` (`ld_percentage_per_week`, `max_ld_percentage`) | `26.0 PRICE REDUCTION SCHEDULE` (GCC) / `14.0 PRS` (SCC) | `"26.1 As per SCC / BDS."` | `PRICE REDUCTION SCHEDULE (PRS) FOR DELAYED DELIVERY` (SCC / BDS) | **CONFIRMED TARGET**. Heading search locates full PRS clause with 0.5% per week up to 5% max ceiling. |
| `sd_mode` / `sd_percentage` / `sd_duration` | `38.0 CONTRACT PERFORMANCE SECURITY` (GCC) | `"38.1 As specified in BDS."` | `ePBG Detail` (BDS Cover) | **CONFIRMED STUB**. Clause 38 contains boilerplate instrument list but defers percentage to BDS. Gated on non-zero SD % in BDS; set to N/A when PBG 5% serves as CPS. |
| `client_contacts` | `39.0 NODAL OFFICER CONTACT` (GCC) | `"39.1 Refer BDS 39.2"` | `CONTACT DETAILS OF TENDER DEALING OFFICER` | **CONFIRMED TARGET**. Scoped regex extracts Nodal Officer name, email (`@gail.co.in`/`@ggl.co.in`), and phone number block. |
| `courier_address` | `8.0 SUBMISSION OF BIDS` (GCC) | `"8.1 Address specified in Cut-Out Slip"` | `CUT-OUT SLIP` / `DO NOT OPEN` | **CONFIRMED TARGET**. Bounded window search extracts receiving officer address and pincode. |

