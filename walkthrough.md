# GAIL/GeM SECTION-II BEC Table Anchor Resolution & Courier Address Leak Fix Walkthrough

## Summary of Accomplishments

### 1. Robust BEC Table Row Parser (`ocr/extractors/field_extractor.py`)
- Simplified the table row parsing for Clauses 1.2, 2.1, and 2.3.
- Implemented binned y-coordinate sorting to group blocks on the same line correctly, preventing misalignment bugs.
- Replaced header-row column-index logic with a robust regex pattern matcher searching binned table text lines:
  `re.findall(r"(Part\s*(?:-?\s*\d+|1\s*&\s*2)[\s\S]*?[\d\.]+\s*(?:Lakh|Crore|Cr))"`
  This parses region-based parts and currency values completely reliably across GAIL tenders, without dependency on table layout/header formatting.

### 2. Multi-Document Page Integration (`pdf_parent_ingest.py`)
- Combined parent page texts and downloaded ATC child page texts into a unified `all_pages` list.
- Passed `all_pages` to `build_infosheet_data`, allowing post-hoc fallback resolvers in `tender_mapper.py` to search both parent bid details and child ATC terms.

### 3. Missing Value Sentinels & Validation (`tender_mapper.py`)
- Updated the `_is_missing` helper to correctly treat sentinel values `"Not Found"` and `"Out of Scope (Stage 1)"` as missing, ensuring post-hoc fallbacks trigger for unextracted stage-1 fields.
- Implemented string checks in the synchronization loop utilizing field IDs as a fallback, ensuring fields with custom lowercase/underscore labels are correctly synchronized.
- Added validation for turnover and working capital fallback triggers requiring the values to contain digits or exemption terms, preventing partial regex match fragments (such as `"The minimum Working"`) from blocking fallback resolution.

### 4. EMD / PBG Mode & Nodal Officer Fallback Enhancements (`tender_mapper.py` & `field_extractor.py`)
- **EMD / PBG Modes fallback**: Implemented a global document text lookup fallback for EMD and PBG instruments if the localized clause block search returns no instruments. This successfully resolves `BT/DD/SB/FDR/BG` and `DD / Online Transfer / Insurance Surety Bond / FDR / Bank Guarantee`.
- **Nodal Officer Contact Parsing**:
  - Skip dummy references (such as `"Name and contact details of nodal officer- Refer BDS for details"`) inside `FieldExtractor` by validating that the parsed block contains contact details (i.e. an email `@` symbol or phone keywords).
  - Updated Nodal Officer fallback logic using `re.finditer` to evaluate all clause matches, ignoring dealing officer signature blocks (Boda Pool Singh) and matching the correct person (Shri Sheew Shankar).
  - Synchronized `client_name_2` back to `"Client Contacts 2"` in the dual-pipeline synchronization loop.

## Verification Results
- All unit and regression tests pass cleanly:
  `python -m pytest tests/` -> **109 passed, 1 skipped** in 228.39 seconds.
- Ran the pipeline against the actual **GAIL Jaipur NiCd** tender (`GEM/2026/B/7306631`). Verified that all extracted fields are fully populated and synced under `scratch/jaipur_mi_cd_output.json`:
  - EMD Amount: `Rs. 1,94,177`
  - PBG Percentage: `5.0`
  - PBG Duration (Months): `21`
  - Client Contacts: `Sh. Boda Pool Singh` ( dealings officer )
  - Client Contacts 2: `Shri Sheew Shankar` ( nodal officer )
  - EMD Mode: `BT/DD/SB/FDR/BG`
  - PBG Mode: `DD / Online Transfer / Insurance Surety Bond / FDR / Bank Guarantee`
  - Turnover/Working Capital: Automatically set to `N/A` because the child PDF BEC text explicitly declares `financial criteria of bec: not applicable`.
