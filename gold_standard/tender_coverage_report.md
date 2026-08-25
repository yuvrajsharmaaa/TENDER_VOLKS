# Tender Coverage & Devanagari Quality Audit Report

**Execution Date**: 2026-08-20  
**Auditor**: Senior ML Data Engineer (Pre-Flight Inspection)  
**Audited Files**: `data/processed/dataset_sft.jsonl`, `data/processed/sft_train.jsonl`, `data/processed/sft_val.jsonl`  

---

## Headline Findings & Status

> **Headline**: **260 total records represent 229 unique tenders (11.9% multiplicity)**.
> 
> **Coverage Status**: **PASS**  
> - ✅ Dataset satisfies breadth criteria (>190 unique tenders in training split, max single tender concentration: 11.8%).  

---

## 1. Unique Tender Coverage & Multiplicity (Concern 1)

### A. Dataset File Split Comparison

| Metric | Full Dataset (`dataset_sft.jsonl`) | Train Split (`sft_train.jsonl`) | Validation Split (`sft_val.jsonl`) |
| :--- | :--- | :--- | :--- |
| **Total Records** | 260 | 221 | 39 |
| **Unique Tender IDs** | 229 | 190 | 39 |
| **Multiplicity Rate** | 11.9% | 14.0% | 0.0% |
| **Min Recs / Tender** | 1 | 1 | 1 |
| **Median Recs / Tender** | 1.0 | 1.0 | 1.0 |
| **Max Recs / Tender** | 26 | 26 | 1 |
| **Top Tender Share** | 10.0% (`doc_group_Extract the critical procurement fields `) | 11.8% (`doc_group_Extract the critical procurement fields `) | 2.6% (`gem/2024/b/5399638`) |

### B. Top 10 Most Represented Tenders in Dataset

| Rank | Tender Identifier / Group Key | Record Count | % of Dataset | Notes / Origin |
| :---: | :--- | :---: | :---: | :--- |
| 1 | `doc_group_Extract the critical procurement fields ` | 26 | 10.0% | Fallback Group (Clauses lacking explicit Bid ID in text) |
| 2 | `gem/2026/b/7786440` | 4 | 1.5% | Multi-Page / Linked ATC |
| 3 | `gem/2026/b/7306631` | 4 | 1.5% | Multi-Page / Linked ATC |
| 4 | `gem/2025/b/7021103` | 1 | 0.4% | Single-Page Corpus Extraction |
| 5 | `gem/2026/b/7357339` | 1 | 0.4% | Single-Page Corpus Extraction |
| 6 | `gem/2026/b/7681659` | 1 | 0.4% | Single-Page Corpus Extraction |
| 7 | `gemc-511687735658177` | 1 | 0.4% | Single-Page Corpus Extraction |
| 8 | `gem/2025/b/6652442` | 1 | 0.4% | Single-Page Corpus Extraction |
| 9 | `gem/2025/b/6607365` | 1 | 0.4% | Single-Page Corpus Extraction |
| 10 | `gem/2025/b/6551049` | 1 | 0.4% | Single-Page Corpus Extraction |

### C. Organization & Client Distribution

Total distinct organizations/clients identified: **108**.

| Rank | Organization / Client Name | Record Count | % of Dataset | Sector / Type |
| :---: | :--- | :---: | :---: | :--- |
| 1 | Gail India Limited | 25 | 9.6% | Public Sector / Government |
| 2 | Unclassified / Other | 19 | 7.3% | Public Sector / Government |
| 3 | Power Grid Corporation Of India Limited | 16 | 6.2% | Public Sector / Government |
| 4 | Indian Air Force | 15 | 5.8% | Public Sector / Government |
| 5 | GAIL | 13 | 5.0% | Public Sector / Government |
| 6 | Bharat Heavy Electricals Limited (bhel) | 9 | 3.5% | Public Sector / Government |
| 7 | Indian Oil Corporation Limited | 8 | 3.1% | Public Sector / Government |
| 8 | Indian Army | 7 | 2.7% | Public Sector / Government |
| 9 | Bharat Petroleum Corporation Ltd | 6 | 2.3% | Public Sector / Government |
| 10 | Nhpc Limited | 4 | 1.5% | Public Sector / Government |
| 11 | Rashtriya Ispat Nigam Limited | 3 | 1.2% | Public Sector / Government |
| 12 | Directorate Of Purchase And Stores | 3 | 1.2% | Public Sector / Government |
| 13 | Powergrid Teleservices Limited | 3 | 1.2% | Public Sector / Government |
| 14 | Punjab | 3 | 1.2% | Public Sector / Government |
| 15 | Mangalore Refinery & Petrochemicals Limited | 3 | 1.2% | Public Sector / Government |
| ... | *93 additional distinct organizations* | 123 | 47.3% | Diverse PSUs & State Depts |

### D. Procurement Category & Subject Distribution

Total distinct procurement categories identified: **169**.

| Rank | Category / Item Description | Record Count | % of Dataset |
| :---: | :--- | :---: | :---: |
| 1 | HVAC & Air Conditioning | 30 | 11.5% |
| 2 | Online UPS (?10 KVA) With Battery Conforming To IS 16242 | 18 | 6.9% |
| 3 | Stationary Valve Regulated Lead Acid Batteries (V3) | 11 | 4.2% |
| 4 | Batteries & Power Backup / UPS | 10 | 3.8% |
| 5 | Split Air Conditioner, Wall Mount Type (V3) ISI Marked to IS | 10 | 3.8% |
| 6 | VRLA Batteries as per Technical Specification (Q3) | 4 | 1.5% |
| 7 | Tender for “Supply, Installation, Testing and Commissioning (SITC | 3 | 1.2% |
| 8 | Online UPS (>10 KVA) With Battery (Q2) | 3 | 1.2% |
| 9 | Stationary Lead Acid Batteries (with Tubular Positive Plates) | 2 | 0.8% |
| 10 | VRLA Batteries (Q3) | 2 | 0.8% |
| 11 | Custom Bid for Services - SUPPLY INTEGRATION AND | 2 | 0.8% |
| 12 | TUBULAR CELL 2V-220 AH | 2 | 0.8% |

---

## 2. Devanagari / Hindi Text Corruption Audit (Concern 2)

### A. Findings & Metrics
- **Total Records Inspected**: 260
- **Records with Devanagari Text (U+0900–U+097F)**: **252** (96.9%)
- **Devanagari Records with Font Corruption Symptoms**: **235** (93.3%)

### B. Corruption Pattern Breakdown

| Corruption Heuristic Pattern | Occurrence Count | Typical Examples from Input Text |
| :--- | :---: | :--- |
| Embedded ASCII punctuation/digits inside Hindi word (e.g. 'व&तु', 'ा!य', '5ासंिगक') | 588 | `व&तु` (वस्तु), `रा!य` (राज्य), `काया%लय` (कार्यालय), `5ासंिगक` (प्रासंगिक), `7यूनतम` (न्यूनतम), `वष=` (वर्षों), `सं@या` (संख्या) |
| Orphaned combining vowel sign/halant at start of token without base consonant | 566 | `व&तु`, `मं ालय`, `रा!य` |
| Disconnected combining vowel mark/matra with preceding whitespace (e.g. 'मं  ालय', 'े  ि') | 509 | `मं ालय`, `ण ि`, `प ि`, `त ि` (broken ligature spaces) |
| Latin character prepended to Devanagari root (e.g. 'Eया', 'Hारा', 'Aदनांक') | 134 | `Eया` (क्या), `Hारा` (द्वारा), `Aदनांक` (दिनांक) |
| Latin character appended to Devanagari root (e.g. 'द&तावेज़G', 'हK') | 121 | `द&तावेज़G` (दस्तावेजों), `हK` / `हL` (हैं) |

### C. Root-Cause Determination: SFT Builder vs. DAPT Builder

1. **The Core Mechanism**: GeM portal PDFs generate bilingual tables using custom non-Unicode 8-bit font glyph mappings (such as KrutiDev / Walkman-Chanakya / JasperReports font streams) that lack standardized ToUnicode CMaps. When PyMuPDF extracts text natively via `page.get_text()`, complex Devanagari ligatures (matras `ि`/`ी`, half-consonants `स्`, `क्ष`, `श्र`, reph `र्`) map to raw 8-bit ASCII characters (`&`, `'`, `%`, `!`, `?`, `@`, `5`, `7`, `E`, `H`, `A`).
2. **Discrepancy with `build_dapt_corpus.py`**: In `scripts/build_dapt_corpus.py`, the DAPT pipeline explicitly detects this via `is_text_scrambled_or_garbage()` and triggers **Tier 3 High-Contrast 300 DPI OCR Fallback (`pytesseract.image_to_string(..., lang='eng+hin')`)** as well as `clean_text_block()` filtering.
3. **Bypass in `build_sft_dataset.py`**: `scripts/build_sft_dataset.py` directly calls `doc[page_idx].get_text()`, bypassing the DAPT corpus builder's OCR fallback and glyph repair pipelines. Thus, corrupted font text streams flow unaltered into the SFT `input` field.
4. **Impact Assessment**: In inference, GeM PDFs extracted natively with PyMuPDF will produce the exact same font artifacts, so the model learns to tolerate native GeM text streams. However, for clean Devanagari generalization or OCR inputs, training on corrupted font artifacts represents noisy supervision.
5. **Recommended Fix Location**: In `scripts/build_sft_dataset.py`, integrate `is_text_scrambled_or_garbage()` and `clean_text_block()` / OCR fallback from `scripts/build_dapt_corpus.py` during document text ingestion.

---

## 3. What to Upload Next: Representation & Expansion Strategy

Based on the coverage distribution across the 260 records, the following areas are identified for prioritized future uploads:

1. **Underrepresented PSU Organizations**:
   - **Healthcare & Medical**: AIIMS, Central Medical Services Society (CMSS), ESIC.
   - **Municipal & Infrastructure**: NHAI, Municipal Corporations (MCD, BMC), State PWDs.
   - **Civil Aviation & Ports**: Airports Authority of India (AAI), Port Trusts.
   - **Mining & Minerals**: NMDC, NALCO, MOIL.

2. **Underrepresented Procurement Categories**:
   - **Civil Works & Construction**: Turnkey building construction, road resurfacing, structural fabrication.
   - **Information Technology & Software**: Cloud hosting, custom software development, ERP licensing, cyber security services.
   - **Medical Equipment & Pharmaceuticals**: Diagnostic devices, generic pharmaceuticals, surgical consumables.
   - **Consultancy & Non-Consulting Professional Services**: Audit, legal advisory, third-party inspection (TPI).

3. **Diverse Document Formats**:
   - Scanned, legacy CPPP (Central Public Procurement Portal) non-GeM PDFs.
   - Multi-schedule BOQ spreadsheets converted to tabular text.
   - State portal tender formats (e.g. Maharashtra, Tamil Nadu, Uttar Pradesh e-Procurement).
