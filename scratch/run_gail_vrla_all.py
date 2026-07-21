import fitz
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.app.models.models import PageResult, TextBlock
from ocr.extractors.gem_field_extractor import GemFieldExtractor, strip_devanagari, match_field, FIELD_ANCHORS, merge_into_cells, pair_cells_by_row, detect_column_split
from rapidfuzz import fuzz

def build_text_blocks_from_words(words: list[dict]) -> list[TextBlock]:
    lines_map = {}
    for w in words:
        key = (w["block_no"], w["line_no"])
        lines_map.setdefault(key, []).append(w)
        
    blocks = []
    for idx, ((block_no, line_no), line_words) in enumerate(lines_map.items()):
        line_words.sort(key=lambda w: w["bounding_box"]["x1"])
        text = " ".join(w["text"] for w in line_words)
        x1 = int(round(min(w["bounding_box"]["x1"] for w in line_words)))
        y1 = int(round(min(w["bounding_box"]["y1"] for w in line_words)))
        x2 = int(round(max(w["bounding_box"]["x2"] for w in line_words)))
        y2 = int(round(max(w["bounding_box"]["y2"] for w in line_words)))
        blocks.append(TextBlock(
            block_id=f"native_{idx}",
            text=text,
            bounding_box={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            confidence=1.0,
            language_hint="en"
        ))
    return blocks

def detect_column_split_v3(text_blocks):
    bins = {}
    for b in text_blocks:
        x1 = b.bounding_box["x1"]
        bin_idx = x1 // 20
        bins[bin_idx] = bins.get(bin_idx, 0) + 1
    
    sorted_bins = sorted(bins.items(), key=lambda item: item[1], reverse=True)
    if len(sorted_bins) >= 2:
        bin1_x = sorted_bins[0][0] * 20 + 10
        bin2_x = sorted_bins[1][0] * 20 + 10
        split = (bin1_x + bin2_x) // 2
        return split
    return 300  # fallback

# Let's run a full extraction on GAIL VRLA Jamnagar with block_no / line_no grouping
pdf_path = 'backend/app/storage/jobs/35580348-246b-49f7-86a0-175c1bfd64ca/GAIL VRLA Jamnagar.pdf'

doc = fitz.open(pdf_path)
mock_results = []
for page_num in range(len(doc)):
    page = doc.load_page(page_num)
    words = page.get_text("words")
    words_dicts = [
        {
            "text": w[4],
            "bounding_box": {"x1": w[0], "y1": w[1], "x2": w[2], "y2": w[3]},
            "block_no": w[5],
            "line_no": w[6],
            "word_no": w[7],
        }
        for w in words
    ]
    blocks = build_text_blocks_from_words(words_dicts)
    mock_results.append(PageResult(
        job_id="test",
        page_number=page_num + 1,
        image_path="",
        image_width_px=600,
        image_height_px=800,
        processing_time_seconds=0.0,
        text_blocks=blocks,
        layout_regions=[]
    ))
doc.close()

# Let's run GemFieldExtractor but override detect_column_split and merge_into_cells
extractor = GemFieldExtractor()

# Let's define the extract_fields logic with our overrides
from ocr.extractors.gem_field_extractor import segment_by_schedule, validate_field, normalize_indian_currency, field_confidence
from backend.app.schemas.schemas import ExtractedFieldSchema, SourceBlockRef, BoundingBox
import re

extracted = []
for entry in extractor.out_of_scope_spec:
    field_name = entry.get("field")
    likely_source = entry.get("likely_source")
    notes = entry.get("notes", "")
    evidence = f"This field lives in: {likely_source}."
    if notes:
        evidence += f" Note: {notes}"
    extracted.append(ExtractedFieldSchema(
        field_name=field_name,
        value=None,
        confidence=0.0,
        source_page=1,
        evidence=evidence,
        source_blocks=[],
        source="not_available_stage1",
        likely_source=likely_source
    ))

candidates = {}
emd_dict = {}
global_emd_amount = None

for page in mock_results:
    is_native = all(b.confidence >= 1.0 for b in page.text_blocks)
    y_gap_tol = 5 if is_native else 20
    
    # 1. Same-block label-value matches
    for block in page.text_blocks:
        text = block.text.strip()
        parts = text.split(":", 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            l_text, r_text = parts[0].strip(), parts[1].strip()
            field_name = match_field(l_text, None)
            if field_name:
                spec = FIELD_ANCHORS[field_name]
                best_score = 0
                for anchor in spec["anchors"]:
                    score = fuzz.partial_ratio(anchor.lower(), strip_devanagari(l_text).lower())
                    if score > best_score:
                        best_score = score
                candidates.setdefault(field_name, []).append({
                    "value": r_text,
                    "confidence": block.confidence * (best_score / 100),
                    "source_page": page.page_number,
                    "schedule_number": None,
                    "evidence": f"Same-block colon match: '{text}'",
                    "source_blocks": [
                        SourceBlockRef(
                            page_number=page.page_number,
                            block_id=block.block_id,
                            text=block.text,
                            bounding_box=BoundingBox(**block.bounding_box)
                        )
                    ]
                })
        for field_name, spec in FIELD_ANCHORS.items():
            for anchor in spec["anchors"]:
                clean_anchor = anchor.lower()
                clean_text = strip_devanagari(text).lower()
                if clean_text.startswith(clean_anchor):
                    idx = text.lower().find(anchor.lower())
                    if idx != -1:
                        suffix = text[idx + len(anchor):].strip()
                        suffix = re.sub(r"^[:\-/\s\u0930\u093e\u093f\u0940\u0941\u0942\u0947\u0948\u094b\u094c\u0902]+", "", suffix).strip()
                        if suffix:
                            candidates.setdefault(field_name, []).append({
                                "value": suffix,
                                "confidence": block.confidence * 0.85,
                                "source_page": page.page_number,
                                "schedule_number": None,
                                "evidence": f"Same-block prefix match: '{text}'",
                                "source_blocks": [
                                    SourceBlockRef(
                                        page_number=page.page_number,
                                        block_id=block.block_id,
                                        text=block.text,
                                        bounding_box=BoundingBox(**block.bounding_box)
                                    )
                                ]
                            })
                            break
                            
    # 2. Spatial pairing
    segments = segment_by_schedule(page.layout_regions, page.text_blocks)
    for seg_num, seg_blocks in segments.items():
        col_split = detect_column_split_v3(seg_blocks)
        left_blocks = [b for b in seg_blocks if b.bounding_box["x1"] < col_split]
        right_blocks = [b for b in seg_blocks if b.bounding_box["x1"] >= col_split]
        left_cells = merge_into_cells(left_blocks, y_gap_tolerance=y_gap_tol)
        right_cells = merge_into_cells(right_blocks, y_gap_tolerance=y_gap_tol)
        pairs = pair_cells_by_row(left_cells, right_cells)
        
        from ocr.extractors.gem_field_extractor import SECTION_HEADERS
        
        current_section = None
        for lc, rc in pairs:
            clean_l = strip_devanagari(lc["text"]).lower()
            best_sec_score = 0
            best_sec = None
            for sec_header in SECTION_HEADERS:
                score = fuzz.partial_ratio(sec_header.lower(), clean_l)
                if score > best_sec_score:
                    best_sec_score = score
                    best_sec = sec_header
            if best_sec_score >= 90:
                current_section = best_sec
                continue
                
            field_name = match_field(lc["text"], current_section)
            if field_name:
                best_score = 0
                spec = FIELD_ANCHORS[field_name]
                for anchor in spec["anchors"]:
                    score = fuzz.partial_ratio(anchor.lower(), clean_l)
                    if score > best_score:
                        best_score = score
                
                # EMD special handling
                if field_name == "emd_amount":
                    try:
                        val_num = float(normalize_indian_currency(rc["text"]))
                        if seg_num > 0:
                            emd_dict[seg_num] = val_num
                        else:
                            global_emd_amount = val_num
                    except Exception:
                        pass
                
                source_blocks = [
                    SourceBlockRef(
                        page_number=page.page_number,
                        block_id=b.block_id,
                        text=b.text,
                        bounding_box=BoundingBox(**b.bounding_box)
                    ) for b in lc["blocks"] + rc["blocks"]
                ]
                
                candidates.setdefault(field_name, []).append({
                    "value": rc["text"],
                    "confidence": field_confidence(lc, rc, best_score),
                    "source_page": page.page_number,
                    "schedule_number": seg_num if seg_num > 0 else None,
                    "evidence": f"Spatial match in section '{current_section}' (schedule {seg_num}): '{lc['text']}' -> '{rc['text']}'",
                    "source_blocks": source_blocks
                })

# Process and resolve standard fields
out_of_scope_names = {entry.get("field") for entry in extractor.out_of_scope_spec}
for field_name in FIELD_ANCHORS:
    if field_name in ("emd_amount", "emd_by_schedule", "emd_total", "emd_required", "schedules"):
        continue
    if field_name in out_of_scope_names:
        continue
    field_cands = candidates.get(field_name, [])
    if field_cands:
        best_cand = sorted(field_cands, key=lambda c: c["confidence"], reverse=True)[0]
        val_raw = best_cand["value"]
        spec = extractor.fields_spec.get(field_name, {})
        val_clean = val_raw.strip()
        if field_name in ("tender_value_gst_inclusive", "annual_avg_turnover_value", "working_capital_value", "net_worth_type_value", "solvency_certificate_value", "tender_fee_amount", "processing_fee_amount"):
            val_clean = normalize_indian_currency(val_clean)
        validation_passed = validate_field(field_name, val_clean)
        extracted.append(ExtractedFieldSchema(
            field_name=field_name,
            value=val_clean if validation_passed else None,
            confidence=best_cand["confidence"] if validation_passed else 0.0,
            source_page=best_cand["source_page"],
            evidence=best_cand["evidence"],
            source_blocks=best_cand["source_blocks"],
            source="gem_parent_pdf",
            needs_review=not validation_passed
        ))
    else:
        extracted.append(ExtractedFieldSchema(
            field_name=field_name,
            value=None,
            confidence=0.0,
            source_page=1,
            evidence="No matching values found in document.",
            source_blocks=[],
            source="gem_parent_pdf"
        ))

# EMD resolve
if emd_dict:
    extracted.append(ExtractedFieldSchema(
        field_name="emd_by_schedule",
        value=emd_dict,
        confidence=0.9,
        source_page=1,
        evidence=f"Schedule EMD amounts extracted: {emd_dict}",
        source_blocks=[],
        source="gem_parent_pdf"
    ))
    total_val = sum(emd_dict.values())
    extracted.append(ExtractedFieldSchema(
        field_name="emd_total",
        value=total_val,
        confidence=0.9,
        source_page=1,
        evidence=f"Derived from schedule EMD sum: {total_val}",
        source_blocks=[],
        source="derived"
    ))
    extracted.append(ExtractedFieldSchema(
        field_name="emd_required",
        value=total_val > 0,
        confidence=0.9,
        source_page=1,
        evidence=f"Derived from schedule EMD sum: {total_val}",
        source_blocks=[],
        source="derived"
    ))
elif global_emd_amount is not None:
    extracted.append(ExtractedFieldSchema(
        field_name="emd_by_schedule",
        value={},
        confidence=0.0,
        source_page=1,
        evidence="Global EMD amount extracted, no schedule split.",
        source_blocks=[],
        source="gem_parent_pdf"
    ))
    extracted.append(ExtractedFieldSchema(
        field_name="emd_total",
        value=global_emd_amount,
        confidence=0.9,
        source_page=1,
        evidence=f"Derived from global EMD amount: {global_emd_amount}",
        source_blocks=[],
        source="derived"
    ))
    extracted.append(ExtractedFieldSchema(
        field_name="emd_required",
        value=global_emd_amount > 0,
        confidence=0.9,
        source_page=1,
        evidence=f"Derived from EMD total: {global_emd_amount}",
        source_blocks=[],
        source="derived"
    ))
else:
    extracted.append(ExtractedFieldSchema(
        field_name="emd_by_schedule",
        value={},
        confidence=0.0,
        source_page=1,
        evidence="No schedule EMD amounts found.",
        source_blocks=[],
        source="gem_parent_pdf"
    ))
    extracted.append(ExtractedFieldSchema(
        field_name="emd_total",
        value=0.0,
        confidence=0.0,
        source_page=1,
        evidence="No schedule EMD amounts found.",
        source_blocks=[],
        source="derived"
    ))
    extracted.append(ExtractedFieldSchema(
        field_name="emd_required",
        value=False,
        confidence=0.0,
        source_page=1,
        evidence="No schedule EMD amounts found.",
        source_blocks=[],
        source="derived"
    ))

print("\n--- RESOLVED FIELDS ---")
for f in extracted:
    if f.value is not None and f.value != 'NA':
        print(f"  {f.field_name}: {repr(f.value)} (source={f.source})")
