# GeM Stage 1 Spatial Key-Value Pairing Extraction

This document explains the technical details of the **Stage 1 Spatial Key-Value Pairing** algorithm implemented to extract structured fields from Government e-Marketplace (GeM) parent tender PDFs.

---

## 1. Core Objectives & Scope

GeM parent tender documents are generated dynamically by the GeM portal using a rigid two-column key-value table layout. Standard prose-based extractors fail to parse these documents accurately because:
- OCR text extraction order can drift horizontally or vertically.
- Multi-line labels and values wrap arbitrarily, making line-by-line regex parsing unreliable.
- Generic labels (like "Required" or "Advisory Bank") repeat across different sections, causing key collisions.

To solve this, Stage 1 replaces flat text-matching with a **geometry-driven spatial pairing pipeline** utilizing text-block coordinates.

*Note: This stage extracts only fields from the parent tender PDF. All clause parsing from buyer-uploaded ATC documents is deferred to Stage 2.*

---

## 2. The Spatial Pairing Pipeline

The geometry-driven pairing runs per page in three main steps:

### Step A: Dynamic Column-Split Detection
Instead of using hardcoded coordinate values, the algorithm dynamically identifies the vertical split dividing the page into label and value columns:
1. All `x1` coordinates of the page's text blocks are collected and sorted.
2. Horizontal gaps between successive blocks are measured.
3. The vertical split point is set at the midpoint of the largest horizontal gap found in the middle 20% to 80% of the page width. This ignores small marginal gaps at page borders.

### Step B: Within-Column Vertical Cell Merging
Multi-line wrapped text blocks must be merged into single cells before horizontal pairing:
1. Text blocks are partitioned into left-column and right-column lists based on the dynamic split point.
2. Within each column, blocks are sorted vertically by their `y1` coordinates.
3. Overlapping or vertically-adjacent blocks (separated by a gap less than `y_gap_tolerance = 5`) are merged into a single logical cell, combining their text and extending their bounding box.

### Step C: Y-Overlap Row Pairing
Merged cells are paired across columns:
1. For each cell in the left column, we scan the right column for cells whose y-ranges overlap.
2. Pairing is established greedily on the maximum overlapping height.
3. This creates distinct, clean key-value candidate pairs (`(l_cell, r_cell)`).

---

## 3. Fuzzy Anchor Matching & Namespace Disambiguation

Labels are matched against the canonical field list using `rapidfuzz`:
1. **Devanagari Stripping**: Before fuzzy matching, Hindi characters are stripped using regex (`[\u0900-\u097F]+`) to maximize English matching reliability.
2. **Namespace Gates**: Several fields share anchors (e.g. `"Advisory Bank"` under `"EMD Detail"` and `"ePBG Detail"`). The matcher tracks the nearest preceding section header (e.g. `EMD Detail`, `ePBG Detail`, `Bid Details`, etc.) as a namespace:
   - If a field is namespaced in the schema, it will only match when the active namespace matches.
   - If the namespace is `None` (like in small unit tests), context is inferred directly from the label text (e.g., if the label contains `"EMD"`, we set context to `"EMD Detail"`).
3. **Fuzzy Scoring**: `rapidfuzz.fuzz.partial_ratio` is computed between the anchor and the label text. A threshold of `80` is required for matching.

---

## 4. Normalization and Validation

Before saving, values are normalized and validated to prevent garbage values or incorrect formats:
- **Indian Number Normalization**: Currency amounts containing `"Lakh"` or `"Crore"` are parsed and converted to standard numeric strings (e.g. `"15 Lakh"` -> `"1500000"`, `"2.5 Crore"` -> `"25000000"`). Currency signs (`₹`), commas, and tailing slashes (`/-`) are stripped.
- **Field-level Validators**:
  - `emd_amount`: Verified to be a pure decimal/integer string post-normalization.
  - `bid_end_datetime`: Matches `DD-MM-YYYY HH:MM:SS` datetime pattern.
  - `pbg_percentage`: Verified to be a number/percentage.
  - `bid_validity_days`: Verified to contain an integer.
- **Fail-Safe Review Flags**: If a normalized value fails its validator, the value is set to `None` and `needs_review = True` is attached to the extracted schema.

---

## 5. Multi-Schedule Segmentation

For tenders split into multiple schedules:
1. `segment_by_schedule` partitions page text blocks based on `Schedule \d+` layout regions or text headers.
2. Spatial pairing and matching run independently within each schedule segment.
3. Unmatched key-value pairs inside a schedule segment are aggregated under `technical_specs`.
4. In post-processing, EMD values are aggregated (`emd_by_schedule`) and summed (`emd_total`), ensuring per-schedule amounts remain auditable.

---

## 6. Handoff to Stage 2

The parent document extraction marks a clean boundary. If Stage 1 detects required documents indicating child files (e.g. `"Certificate (Requested in ATC)"` or any document ending with `"(Requested in ATC)"`), it flags `needs_stage2_atc_parse: true` in the output response. This signals downstream workers to initiate Stage 2 (ATC PDF extraction) to parse specific clause details.
