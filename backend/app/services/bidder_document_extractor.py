import json
import re
from pathlib import Path
from typing import Any, Dict, List


def _load_ocr_blocks(raw_ocr_path: Path) -> List[Dict[str, Any]]:
    with open(raw_ocr_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    blocks = []

    for page_number, page_blocks in data.get("pages", {}).items():
        for block in page_blocks or []:
            blocks.append({
                "page": int(page_number),
                "text": str(block.get("text", "")).strip(),
                "confidence": float(block.get("confidence", 0.0)),
                "block_id": block.get("block_id"),
            })

    return blocks


def _field(
    value: Any,
    confidence: float,
    page: int,
    block_id: Any,
    evidence: str,
) -> Dict[str, Any]:
    return {
        "value": value,
        "confidence": round(confidence, 4),
        "source_page": page,
        "source_block": block_id,
        "evidence": evidence,
    }


def _find_label_value(
    blocks: List[Dict[str, Any]],
    labels: List[str],
) -> Dict[str, Any] | None:
    for block in blocks:
        text = block["text"]

        for label in labels:
            match = re.search(
                rf"{re.escape(label)}\s*:\s*(.+)$",
                text,
                re.IGNORECASE,
            )

            if match:
                return _field(
                    match.group(1).strip(),
                    block["confidence"],
                    block["page"],
                    block["block_id"],
                    text,
                )

    return None


def _extract_gst(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}

    gst_pattern = re.compile(
        r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\dZ[A-Z0-9]\b",
        re.IGNORECASE,
    )

    for block in blocks:
        match = gst_pattern.search(block["text"].upper())
        if match:
            fields["gstin"] = _field(
                match.group(0).upper(),
                block["confidence"],
                block["page"],
                block["block_id"],
                block["text"],
            )
            break

    legal_name = _find_label_value(
        blocks,
        ["Legal Name", "Legal Name of Business", "Trade Name"],
    )
    if legal_name:
        fields["legal_name"] = legal_name

    state = _find_label_value(
        blocks,
        ["State", "State Name"],
    )
    if state:
        fields["state"] = state

    status = _find_label_value(
        blocks,
        ["Status", "GST Status", "Registration Status"],
    )
    if status:
        fields["registration_status"] = status

    return fields


def _extract_pan(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}

    pan_pattern = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")

    for block in blocks:
        match = pan_pattern.search(block["text"].upper())
        if match:
            fields["pan"] = _field(
                match.group(0).upper(),
                block["confidence"],
                block["page"],
                block["block_id"],
                block["text"],
            )
            break

    legal_name = _find_label_value(
        blocks,
        ["Name", "Name of Assessee", "Legal Name"],
    )
    if legal_name:
        fields["legal_name"] = legal_name

    return fields


def _extract_udyam(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}

    udyam_pattern = re.compile(
        r"\bUDYAM-[A-Z]{2}-\d{2}-\d{7,8}\b",
        re.IGNORECASE,
    )

    for block in blocks:
        match = udyam_pattern.search(block["text"].upper())
        if match:
            fields["udyam_number"] = _field(
                match.group(0).upper(),
                block["confidence"],
                block["page"],
                block["block_id"],
                block["text"],
            )
            break

    name = _find_label_value(
        blocks,
        ["Enterprise Name", "Name of Enterprise", "Legal Name"],
    )
    if name:
        fields["legal_name"] = name

    return fields


def _extract_cin(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}

    cin_pattern = re.compile(
        r"\b[ULF]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b",
        re.IGNORECASE,
    )

    for block in blocks:
        match = cin_pattern.search(block["text"].upper())
        if match:
            fields["cin"] = _field(
                match.group(0).upper(),
                block["confidence"],
                block["page"],
                block["block_id"],
                block["text"],
            )
            break

    name = _find_label_value(
        blocks,
        ["Company Name", "Company", "Legal Name"],
    )
    if name:
        fields["legal_name"] = name

    return fields


def extract_bidder_fields(
    document_type: str,
    raw_ocr_path: Path,
) -> Dict[str, Any]:

    blocks = _load_ocr_blocks(raw_ocr_path)

    document_type = document_type.upper()

    if document_type == "GST_CERTIFICATE":
        fields = _extract_gst(blocks)
    elif document_type in {"PAN_CARD", "PAN_CERTIFICATE"}:
        fields = _extract_pan(blocks)
    elif document_type in {"UDYAM_CERTIFICATE", "MSME_CERTIFICATE"}:
        fields = _extract_udyam(blocks)
    elif document_type in {"CIN_CERTIFICATE", "MCA_CERTIFICATE"}:
        fields = _extract_cin(blocks)
    else:
        fields = {}

    confidences = [
        float(v.get("confidence", 0.0))
        for v in fields.values()
        if isinstance(v, dict)
    ]

    document_confidence = (
        sum(confidences) / len(confidences)
        if confidences
        else 0.0
    )

    return {
        "document_type": document_type,
        "fields": fields,
        "document_confidence": round(document_confidence, 4),
        "field_count": len(fields),
        "is_valid": bool(fields),
        "extraction_engine": "bidder_document_extractor",
        "source": "raw_ocr",
    }
