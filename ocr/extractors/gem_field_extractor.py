import re
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from ocr.extractors.field_extractor import FieldExtractor, group_blocks_into_rows
from backend.app.models.models import PageResult, TextBlock
from backend.app.schemas.schemas import ExtractedFieldSchema, SourceBlockRef, BoundingBox

logger = logging.getLogger("tender_ocr")

def merge_blocks_into_cells(blocks: List[TextBlock], y_threshold: int = 30) -> List[Dict[str, Any]]:
    if not blocks:
        return []
    # Sort blocks primarily by y1, then by x1
    sorted_blocks = sorted(blocks, key=lambda b: (b.bounding_box["y1"], b.bounding_box["x1"]))
    cells = []
    
    current_cell = [sorted_blocks[0]]
    for block in sorted_blocks[1:]:
        cell_y2 = max(b.bounding_box["y2"] for b in current_cell)
        if block.bounding_box["y1"] - cell_y2 <= y_threshold:
            current_cell.append(block)
        else:
            cells.append(current_cell)
            current_cell = [block]
    cells.append(current_cell)
    
    formatted_cells = []
    for cell in cells:
        text = " ".join(b.text.strip() for b in cell)
        x1 = min(b.bounding_box["x1"] for b in cell)
        y1 = min(b.bounding_box["y1"] for b in cell)
        x2 = max(b.bounding_box["x2"] for b in cell)
        y2 = max(b.bounding_box["y2"] for b in cell)
        formatted_cells.append({
            "text": text,
            "bounding_box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "blocks": cell
        })
    return formatted_cells

def find_paired_right_cell(left_cell: Dict[str, Any], right_cells: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not right_cells:
        return None
    ly1, ly2 = left_cell["bounding_box"]["y1"], left_cell["bounding_box"]["y2"]
    
    best_cell = None
    max_overlap = -1
    for r_cell in right_cells:
        ry1, ry2 = r_cell["bounding_box"]["y1"], r_cell["bounding_box"]["y2"]
        overlap = max(0, min(ly2, ry2) - max(ly1, ry1))
        if overlap > max_overlap:
            max_overlap = overlap
            best_cell = r_cell
            
    if max_overlap > 0:
        return best_cell
        
    l_mid = (ly1 + ly2) / 2
    best_dist = float('inf')
    for r_cell in right_cells:
        ry1, ry2 = r_cell["bounding_box"]["y1"], r_cell["bounding_box"]["y2"]
        r_mid = (ry1 + ry2) / 2
        dist = abs(l_mid - r_mid)
        if dist < best_dist:
            best_dist = dist
            best_cell = r_cell
            
    if best_dist < 150:
        return best_cell
    return None

class GemFieldExtractor(FieldExtractor):
    def __init__(self):
        super().__init__()
        yaml_path = Path(__file__).resolve().parent.parent.parent / "gem_parent_tender_extraction_map.yaml"
        logger.info(f"Loading GeM extraction spec from: {yaml_path}")
        with open(yaml_path, "r", encoding="utf-8") as f:
            self.spec = yaml.safe_load(f)
        self.fields_spec = self.spec.get("fields", {})
        self.out_of_scope_spec = self.spec.get("out_of_scope_stage1", [])
        if "bid_validity_days" in self.fields_spec:
            self.fields_spec["bid_validity_days"]["anchor_labels"] = list(set(
                self.fields_spec["bid_validity_days"].get("anchor_labels", []) + 
                ["Bid Offer Validity", "Bid Validity Period", "Bid Validity"]
            ))

    def extract_fields(self, pages: List[PageResult]) -> List[ExtractedFieldSchema]:
        extracted = []
        logger.info(f"Starting GeM field extraction on {len(pages)} page(s).")

        # 1. Build out-of-scope stubs first
        for entry in self.out_of_scope_spec:
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

        # 2. Extract EMD by Schedule & derived fields
        emd_dict = {}
        emd_source_blocks = []
        emd_evidence_parts = []
        
        for page in pages:
            for block in page.text_blocks:
                m_sch = re.search(r"Schedule\s*(\d+)\s*EMD\s*Amount", block.text, re.IGNORECASE)
                if m_sch:
                    sch_num = int(m_sch.group(1))
                    val_str = self._extract_suffix_after_anchor(block.text, [m_sch.group(0)])
                    val = None
                    if val_str:
                        val = self._match_value_pattern(val_str, "currency")
                    if not val:
                        # Try next block
                        try:
                            idx = page.text_blocks.index(block)
                            if idx + 1 < len(page.text_blocks):
                                val = self._match_value_pattern(page.text_blocks[idx+1].text, "currency")
                        except ValueError:
                            pass
                    if val:
                        clean_val = re.sub(r"[^\d.]", "", val)
                        if clean_val:
                            try:
                                emd_dict[sch_num] = float(clean_val)
                                emd_evidence_parts.append(f"Schedule {sch_num}: {clean_val}")
                                emd_source_blocks.append(SourceBlockRef(
                                    page_number=page.page_number,
                                    block_id=block.block_id,
                                    text=block.text,
                                    bounding_box=BoundingBox(**block.bounding_box)
                                ))
                            except ValueError:
                                pass

        # Fallback for global EMD if no schedule EMD is found
        if not emd_dict:
            for page in pages:
                col_split = 750 if page.image_width_px > 1000 else 260
                left_blocks = [b for b in page.text_blocks if b.bounding_box["x1"] < col_split]
                right_blocks = [b for b in page.text_blocks if b.bounding_box["x1"] >= col_split]
                left_cells = merge_blocks_into_cells(left_blocks)
                right_cells = merge_blocks_into_cells(right_blocks)
                for l_cell in left_cells:
                    if "emd" in l_cell["text"].lower() and "amount" in l_cell["text"].lower():
                        r_cell = find_paired_right_cell(l_cell, right_cells)
                        if r_cell:
                            val_str = self._match_value_pattern(r_cell["text"], "currency")
                            if val_str:
                                clean_val = re.sub(r"[^\d.]", "", val_str)
                                if clean_val:
                                    try:
                                        global_emd_val = float(clean_val)
                                        emd_dict[1] = global_emd_val
                                        emd_evidence_parts.append(f"Global EMD: {clean_val}")
                                        emd_source_blocks.append(SourceBlockRef(
                                            page_number=page.page_number,
                                            block_id=l_cell["blocks"][0].block_id,
                                            text=l_cell["text"],
                                            bounding_box=BoundingBox(**l_cell["blocks"][0].bounding_box)
                                        ))
                                        break
                                    except ValueError:
                                        pass
                if emd_dict:
                    break

        if emd_dict:
            extracted.append(ExtractedFieldSchema(
                field_name="emd_by_schedule",
                value=emd_dict,  # store dictionary directly
                confidence=0.9,
                source_page=1,
                evidence=" | ".join(emd_evidence_parts),
                source_blocks=emd_source_blocks,
                source="gem_parent_pdf"
            ))
            total_val = sum(emd_dict.values())
            extracted.append(ExtractedFieldSchema(
                field_name="emd_total",
                value=total_val,
                confidence=0.9,
                source_page=1,
                evidence=f"Derived sum of schedule EMDs: {emd_dict}",
                source_blocks=[],
                source="derived"
            ))
            extracted.append(ExtractedFieldSchema(
                field_name="emd_required",
                value=total_val > 0,
                confidence=0.9,
                source_page=1,
                evidence=f"Derived from EMD total: {total_val}",
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

        # 3. Extract schedules (consignees and technical specs)
        schedules_data = {}
        
        for page in pages:
            sorted_blocks = sorted(page.text_blocks, key=lambda b: (b.bounding_box["y1"], b.bounding_box["x1"]))
            all_rows = group_blocks_into_rows(sorted_blocks)
            
            current_schedule_num = 1
            consignee_headers = None
            
            for row_idx, row in enumerate(all_rows):
                row_text = " ".join(b.text for b in row)
                
                m_sch = re.search(r"Schedule\s*(\d+)", row_text, re.IGNORECASE)
                if m_sch:
                    current_schedule_num = int(m_sch.group(1))
                    
                # 1. Check if this is a technical spec row
                is_tech_spec = False
                if len(row) >= 2:
                    c1_text = row[0].text.strip()
                    c2_text = " ".join(b.text.strip() for b in row[1:])
                    spec_keywords = [
                        "battery capacity", "nominal battery voltage", "battery voltage",
                        "capacity at 10-h", "voltage", "capacity", "specification", "oem"
                    ]
                    if any(kw in c1_text.lower() for kw in spec_keywords):
                        if not any(k in c1_text.lower() for k in ["dated", "schedule", "consignee", "delivery"]):
                            is_tech_spec = True
                            
                if is_tech_spec:
                    schedules_data.setdefault(current_schedule_num, {
                        "schedule_number": current_schedule_num,
                        "consignee_name": "Not Found",
                        "consignee_address": "Not Found",
                        "quantity": "Not Found",
                        "delivery_days": "Not Found",
                        "item_description": "Not Found",
                        "technical_specs": {}
                    })
                    clean_param = re.sub(r"^[^a-zA-Z0-9\s]+", "", c1_text)
                    clean_param = re.sub(r"^[/\\_.:\-]+\s*", "", clean_param).strip()
                    schedules_data[current_schedule_num]["technical_specs"][clean_param] = c2_text.strip()
                    continue
                    
                # 2. Check for Consignees header row
                row_texts_lower = [b.text.lower() for b in row]
                has_consignee = any("consignee" in txt or "reporting" in txt or "officer" in txt for txt in row_texts_lower)
                has_qty = any("quantity" in txt or "मात्रा" in txt for txt in row_texts_lower)
                has_days = any("delivery" in txt or "days" in txt for txt in row_texts_lower)
                
                if has_consignee and (has_qty or has_days):
                    consignee_headers = {}
                    for col_idx, block in enumerate(row):
                        txt = block.text.lower()
                        if "consignee" in txt or "reporting" in txt or "officer" in txt:
                            consignee_headers["consignee_name"] = col_idx
                        elif "address" in txt or "पता" in txt:
                            consignee_headers["consignee_address"] = col_idx
                        elif "quantity" in txt or "मात्रा" in txt:
                            consignee_headers["quantity"] = col_idx
                        elif "delivery" in txt or "days" in txt:
                            consignee_headers["delivery_days"] = col_idx
                    continue
                    
                # 3. If we have active consignee headers, parse this row as a consignee row
                if consignee_headers and len(row) >= 2:
                    if any("total" in b.text.lower() or "योग" in b.text.lower() or "schedule" in b.text.lower() for b in row):
                        consignee_headers = None
                        continue
                        
                    schedules_data.setdefault(current_schedule_num, {
                        "schedule_number": current_schedule_num,
                        "consignee_name": "Not Found",
                        "consignee_address": "Not Found",
                        "quantity": "Not Found",
                        "delivery_days": "Not Found",
                        "item_description": "Not Found",
                        "technical_specs": {}
                    })
                    
                    entry = schedules_data[current_schedule_num]
                    for field, col_idx in consignee_headers.items():
                        if col_idx < len(row):
                            val = row[col_idx].text.strip()
                            if field in ("quantity", "delivery_days"):
                                clean_val = re.sub(r"\D", "", val)
                                if clean_val:
                                    try:
                                        entry[field] = int(clean_val)
                                    except ValueError:
                                        pass
                            else:
                                entry[field] = val
                    continue

            for block in sorted_blocks:
                m_sch = re.search(r"Schedule\s*(\d+)", block.text, re.IGNORECASE)
                if m_sch:
                    current_schedule_num = int(m_sch.group(1))
                if current_schedule_num in schedules_data:
                    if "pieces" in block.text or "quantity" in block.text.lower() or "stationary" in block.text.lower():
                        if not any(k in block.text.lower() for k in ["dated", "consignee", "address", "delivery", "schedule"]):
                            schedules_data[current_schedule_num]["item_description"] = block.text.strip()

        if schedules_data:
            flat_schedules = list(schedules_data.values())
            extracted.append(ExtractedFieldSchema(
                field_name="schedules",
                value=flat_schedules,
                confidence=0.9,
                source_page=1,
                evidence=f"Extracted {len(flat_schedules)} schedules/consignees.",
                source_blocks=[],
                source="gem_parent_pdf"
            ))
        else:
            extracted.append(ExtractedFieldSchema(
                field_name="schedules",
                value=[],
                confidence=0.0,
                source_page=1,
                evidence="No schedules found.",
                source_blocks=[],
                source="gem_parent_pdf"
            ))

        # 4. Standard Field Extraction based on YAML fields mapping
        for field_name, spec in self.fields_spec.items():
            if field_name in ("emd_by_schedule", "emd_total", "emd_required", "schedules"):
                continue
                
            if field_name == "buyer_added_text_atc_clauses":
                clauses = []
                found_heading = False
                target_page_idx = -1
                heading_block_idx = -1
                
                for p_idx, page in enumerate(pages):
                    sorted_blocks = sorted(page.text_blocks, key=lambda b: (b.bounding_box["y1"], b.bounding_box["x1"]))
                    for b_idx, block in enumerate(sorted_blocks):
                        block_text_lower = block.text.lower()
                        if any(h in block_text_lower for h in [
                            "buyer added bid specific terms and conditions",
                            "buyer added text based atc clauses",
                            "buyer added bid specific atc"
                        ]):
                            found_heading = True
                            target_page_idx = p_idx
                            heading_block_idx = b_idx
                            break
                    if found_heading:
                        break
                        
                if found_heading:
                    curr_page_idx = target_page_idx
                    start_block_idx = heading_block_idx + 1
                    gathering = True
                    evidence_blocks = []
                    
                    while curr_page_idx < len(pages) and gathering:
                        page = pages[curr_page_idx]
                        sorted_blocks = sorted(page.text_blocks, key=lambda b: (b.bounding_box["y1"], b.bounding_box["x1"]))
                        
                        for b_idx in range(start_block_idx, len(sorted_blocks)):
                            block = sorted_blocks[b_idx]
                            block_text = block.text.strip()
                            block_text_lower = block_text.lower()
                            
                            if "disclaimer" in block_text_lower:
                                gathering = False
                                break
                            if "this bid is also governed by" in block_text_lower:
                                gathering = False
                                break
                            m_head = re.match(r"^(\d+)\.\s+[A-Z]", block_text)
                            if m_head:
                                sec_num = int(m_head.group(1))
                                if sec_num > 9:
                                    gathering = False
                                    break
                                    
                            if block_text:
                                clauses.append(block_text)
                                evidence_blocks.append(SourceBlockRef(
                                    page_number=page.page_number,
                                    block_id=block.block_id,
                                    text=block.text,
                                    bounding_box=BoundingBox(**block.bounding_box)
                                ))
                                
                        curr_page_idx += 1
                        start_block_idx = 0
                        
                if clauses:
                    extracted.append(ExtractedFieldSchema(
                        field_name="buyer_added_text_atc_clauses",
                        value="\n".join(clauses),
                        confidence=0.95,
                        source_page=pages[target_page_idx].page_number,
                        evidence=f"Extracted {len(clauses)} clauses under Buyer Added ATC section.",
                        source_blocks=evidence_blocks,
                        source="gem_parent_pdf"
                    ))
                else:
                    extracted.append(ExtractedFieldSchema(
                        field_name="buyer_added_text_atc_clauses",
                        value=None,
                        confidence=0.0,
                        source_page=1,
                        evidence="Buyer Added ATC section not found or empty.",
                        source_blocks=[],
                        source="gem_parent_pdf"
                    ))
                continue
                
            anchors = spec.get("anchor_labels", [])
            field_type = spec.get("type", "text")
            pattern = spec.get("pattern")
            
            candidates = []
            
            for page in pages:
                page_num = page.page_number
                col_split = 750 if page.image_width_px > 1000 else 260
                left_blocks = [b for b in page.text_blocks if b.bounding_box["x1"] < col_split]
                right_blocks = [b for b in page.text_blocks if b.bounding_box["x1"] >= col_split]
                
                left_cells = merge_blocks_into_cells(left_blocks)
                right_cells = merge_blocks_into_cells(right_blocks)
                
                # Check 1: Same block match
                for block in page.text_blocks:
                    for anchor in anchors:
                        if self._anchor_matches(anchor, block.text):
                            suffix = self._extract_suffix_after_anchor(block.text, [anchor])
                            val = None
                            if suffix:
                                if pattern:
                                    m = re.search(pattern, suffix, re.IGNORECASE)
                                    if m:
                                        val = m.group(1) if len(m.groups()) >= 1 else m.group(0)
                                    else:
                                        # Fallback to full block text
                                        m = re.search(pattern, block.text, re.IGNORECASE)
                                        if m:
                                            val = m.group(1) if len(m.groups()) >= 1 else m.group(0)
                                        else:
                                            # Label-less fallback patterns
                                            if "GEM/" in pattern:
                                                m2 = re.search(r"GEM/[A-Z0-9/]+", block.text, re.IGNORECASE)
                                                if m2:
                                                    val = m2.group(0)
                                            elif "Dated" in pattern:
                                                m2 = re.search(r"\d{2}-\d{2}-\d{4}", block.text)
                                                if m2:
                                                    val = m2.group(0)
                                            elif field_type == "integer":
                                                m2 = re.search(r"\d+", block.text)
                                                if m2:
                                                    val = m2.group(0)
                                            elif field_type in ("float", "number"):
                                                m2 = re.search(r"\d+(?:\.\d+)?", block.text)
                                                if m2:
                                                    val = m2.group(0)
                                else:
                                    if field_type in ["date", "datetime", "email", "currency", "fee", "nit"]:
                                        val = self._match_value_pattern(suffix, field_type)
                                    else:
                                        val = suffix
                            if val:
                                candidates.append({
                                    "value": val,
                                    "confidence": 0.95,
                                    "source_page": page_num,
                                    "evidence": f"Same-block match: '{block.text}'",
                                    "source_blocks": [SourceBlockRef(
                                        page_number=page_num,
                                        block_id=block.block_id,
                                        text=block.text,
                                        bounding_box=BoundingBox(**block.bounding_box)
                                    )]
                                })
                
                # Check 2: Cell proximity match
                for l_cell in left_cells:
                    for anchor in anchors:
                        if self._anchor_matches(anchor, l_cell["text"]):
                            r_cell = find_paired_right_cell(l_cell, right_cells)
                            if r_cell:
                                val = None
                                r_text = r_cell["text"]
                                if pattern:
                                    m = re.search(pattern, r_text, re.IGNORECASE)
                                    if m:
                                        val = m.group(1) if len(m.groups()) >= 1 else m.group(0)
                                    else:
                                        # Fallback to combined label + value text
                                        combined_text = f"{l_cell['text']} {r_text}"
                                        m = re.search(pattern, combined_text, re.IGNORECASE)
                                        if m:
                                            val = m.group(1) if len(m.groups()) >= 1 else m.group(0)
                                        else:
                                            # Label-less fallback patterns
                                            if "GEM/" in pattern:
                                                m2 = re.search(r"GEM/[A-Z0-9/]+", combined_text, re.IGNORECASE)
                                                if m2:
                                                    val = m2.group(0)
                                            elif "Dated" in pattern:
                                                m2 = re.search(r"\d{2}-\d{2}-\d{4}", combined_text)
                                                if m2:
                                                    val = m2.group(0)
                                            elif field_type == "integer":
                                                m2 = re.search(r"\d+", combined_text)
                                                if m2:
                                                    val = m2.group(0)
                                            elif field_type in ("float", "number"):
                                                m2 = re.search(r"\d+(?:\.\d+)?", combined_text)
                                                if m2:
                                                    val = m2.group(0)
                                else:
                                    if field_type in ["date", "datetime", "email", "currency", "fee", "nit"]:
                                        val = self._match_value_pattern(r_text, field_type)
                                    else:
                                        val = r_text
                                if val:
                                    candidates.append({
                                        "value": val,
                                        "confidence": 0.90,
                                        "source_page": page_num,
                                        "evidence": f"Cell-pair match: Label '{l_cell['text']}' -> Value '{r_text}'",
                                        "source_blocks": [
                                            SourceBlockRef(
                                                page_number=page_num,
                                                block_id=b.block_id,
                                                text=b.text,
                                                bounding_box=BoundingBox(**b.bounding_box)
                                            ) for b in l_cell["blocks"] + r_cell["blocks"]
                                        ]
                                    })
            
            # Resolve best candidate
            if candidates:
                best_cand = sorted(candidates, key=lambda c: c["confidence"], reverse=True)[0]
                val = best_cand["value"]
                
                if field_type == "integer":
                    clean_val = re.sub(r"\D", "", str(val))
                    val = int(clean_val) if clean_val else None
                elif field_type == "float" or field_type == "number":
                    clean_val = re.sub(r"[^\d.]", "", str(val))
                    val = float(clean_val) if clean_val else None
                elif field_type == "boolean" or field_type == "yes_no":
                    val = "yes" in str(val).lower() or "true" in str(val).lower() or "हाँ" in str(val).lower() or "required" in str(val).lower()
                elif field_type == "list":
                    split_on = spec.get("split_on", ",")
                    items = [item.strip() for item in str(val).split(split_on) if item.strip()]
                    formatted_items = []
                    for item in items:
                        needs_stage2 = "(Requested in ATC)" in item
                        formatted_items.append({
                            "document_name": item,
                            "needs_stage2": needs_stage2
                        })
                    val = formatted_items
                
                extracted.append(ExtractedFieldSchema(
                    field_name=field_name,
                    value=val,
                    confidence=best_cand["confidence"],
                    source_page=best_cand["source_page"],
                    evidence=best_cand["evidence"],
                    source_blocks=best_cand["source_blocks"],
                    source="gem_parent_pdf"
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

        # Derive pbg_required
        pbg_pct_val = 0.0
        pbg_pct_field = next((f for f in extracted if f.field_name == "pbg_percentage"), None)
        if pbg_pct_field and pbg_pct_field.value is not None:
            try:
                clean_pct = re.sub(r"[^\d.]", "", str(pbg_pct_field.value))
                if clean_pct:
                    pbg_pct_val = float(clean_pct)
            except ValueError:
                pass
                
        extracted.append(ExtractedFieldSchema(
            field_name="pbg_required",
            value=pbg_pct_val > 0.0,
            confidence=0.9,
            source_page=1,
            evidence=f"Derived from pbg_percentage: {pbg_pct_val}",
            source_blocks=[],
            source="derived"
        ))

        logger.info(f"Finished GeM field extraction. Total fields: {len(extracted)}")
        return extracted
