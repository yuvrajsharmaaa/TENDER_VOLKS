import logging
import re
from typing import List, Dict, Any, Optional

from backend.app.models.models import PageResult, TextBlock
from ocr.extractors.field_extractor import FieldExtractor

logger = logging.getLogger(__name__)

def extract_tender_fields(
    pages: List[Dict[str, Any]],
    filename_title: str,
    document_type: Optional[str] = "generic_nit"
) -> List[Dict[str, Any]]:
    """
    Unified extractor entrypoint for the background pipeline.
    Routes raw PyMuPDF text pages through the appropriate extractor based on document type.
    """
    is_gem = document_type and document_type.lower() in ["gem", "ge_m", "government_e_marketplace", "gem_structured"]
    logger.info("Routing %d pages through %s extractor...", len(pages), "GemFieldExtractor" if is_gem else "FieldExtractor")

    # 1. Map raw text to PageResults for the spatial engine
    mock_results = []
    for p in pages:
        lines = p.get("text", "").split('\n')
        blocks = []
        # Use real blocks from page_data if available
        raw_blocks = p.get("blocks", [])
        if raw_blocks and all(isinstance(b, dict) and "bounding_box" in b for b in raw_blocks):
            for b in raw_blocks:
                text = b.get("text", "").strip()
                if not text:
                    continue
                blocks.append(TextBlock(
                    block_id=b.get("block_id", f"native_{len(blocks)}"),
                    text=text,
                    confidence=b.get("confidence", 1.0),
                    language_hint=b.get("language_hint", "en"),
                    bounding_box=b["bounding_box"]
                ))
        else:
            # Fallback synthetic boxes only when no block data
            for i, line in enumerate(lines):
                line_str = line.strip()
                if not line_str:
                    continue
                blocks.append(TextBlock(
                    block_id=f"line_{i}",
                    text=line_str,
                    confidence=1.0,
                    language_hint="en",
                    bounding_box={"x1": 0, "y1": i * 20, "x2": 500, "y2": (i * 20) + 15}
                ))
        # Calculate actual page width from blocks if available, otherwise use default
        image_width_px = 600  # default fallback
        image_height_px = max(800, len(lines) * 20)  # default fallback height

        if raw_blocks and all(isinstance(b, dict) and "bounding_box" in b for b in raw_blocks):
            # Calculate actual width from bounding boxes
            max_x2 = max(b["bounding_box"]["x2"] for b in raw_blocks)
            max_y2 = max(b["bounding_box"]["y2"] for b in raw_blocks)
            min_x1 = min(b["bounding_box"]["x1"] for b in raw_blocks)
            min_y1 = min(b["bounding_box"]["y1"] for b in raw_blocks)

            if max_x2 > min_x1:
                image_width_px = int(max_x2 - min_x1)
            if max_y2 > min_y1:
                image_height_px = int(max_y2 - min_y1)

            # Ensure minimum dimensions
            image_width_px = max(image_width_px, 100)
            image_height_px = max(image_height_px, 100)

        # Sort blocks by reading order (top to bottom, left to right)
        blocks.sort(key=lambda b: (b.bounding_box["y1"], b.bounding_box["x1"]))

        mock_results.append(PageResult(
            job_id="background-ingest",
            page_number=p.get("page", 1),
            image_path="",
            image_width_px=image_width_px,
            image_height_px=image_height_px,
            processing_time_seconds=0.0,
            text_blocks=blocks,
            layout_regions=p.get("layout_regions", [])
        ))

    # 2. Use appropriate extractor based on document type
    if is_gem:
        from ocr.extractors.gem_field_extractor import GemFieldExtractor
        extractor = GemFieldExtractor()
    else:
        extractor = FieldExtractor()
    extracted = extractor.extract_fields(mock_results)

    # 3. Map extracted fields back to legacy sections structure expected by tender_mapper
    label_mapping = {
        "Tender Value": "Estimated Tender Value",
        "tender_value": "Estimated Tender Value",
        "EMD": "EMD Amount",
        "emd_amount": "EMD Amount",
        "emd_total": "EMD Amount",
        "emd_required": "EMD Required",
        "bid_validity_days": "Bid Validity Period",
        "reverse_auction_enabled": "Reverse Auction Applicable",
        "ra_qualification_rule": "RA Qualification Rule",
        "pbg_percentage": "PBG Percentage",
        "pbg_duration_months": "PBG Duration (Months)",
        "evaluation_method": "Commercial Evaluation Type",
        "NIT No": "Reference ID / NIT No",
        "bid_number": "Reference ID / NIT No",
        "tender_id": "Reference ID / NIT No",
        "Bid Submission End Date": "Bid Submission Deadline",
        "bid_end_datetime": "Bid Submission Deadline",
        "Organisation": "Organisation",
        "organisation_name": "Organisation",
        "organization_name": "Organisation",
        "ministry_name": "Organisation",
        "ministry_state_name": "Organisation",
        "department_name": "Organisation",
        "office_name": "Organisation",
        "Tender Fee": "Tender Fee",
        "tender_fee_amount": "Tender Fee"
    }
    
    fields = []

    # Deduplicate fields by label, prioritizing valid values and higher confidence
    label_to_field = {}
    for i, f in enumerate(extracted):
        label = label_mapping.get(f.field_name, f.field_name)
        status = "missing" if (f.value is None or f.value == "Not Found") else "extracted"
        field_dict = {
            "id": f"f-{i}",
            "label": label,
            "value": f.value,
            "confidence": f.confidence,
            "critical": getattr(f, "critical", False),
            "sourcePage": getattr(f, "page", getattr(f, "source_page", 1)),
            "sourceSnippet": getattr(f, "source_snippet", getattr(f, "evidence", "")),
            "status": status
        }
        existing = label_to_field.get(label)
        if not existing:
            label_to_field[label] = field_dict
        else:
            if field_dict["status"] == "extracted" and existing["status"] == "missing":
                label_to_field[label] = field_dict
            elif field_dict["status"] == existing["status"]:
                if field_dict["confidence"] > existing["confidence"]:
                    label_to_field[label] = field_dict

    for label, field_dict in label_to_field.items():
        fields.append(field_dict)
        
    # 4. Handle products
    products = extractor.extract_products(mock_results)
    for idx, p in enumerate(products):
        fields.append({
            "id": f"prod-{idx}",
            "label": f"Requirement: {p.get('category', '').upper()}",
            "value": f"Name: {p.get('product_name', '')} | Qty: {p.get('qty', '')} {p.get('unit', '')} | OEM: {p.get('brand', '')}",
            "confidence": 90.0,
            "critical": False,
            "sourcePage": p.get("page_number", 1),
            "sourceSnippet": p.get("evidence", ""),
            "status": "extracted"
        })

    return [{"id": "sec-unified", "title": "Unified Extraction", "fields": fields}]
