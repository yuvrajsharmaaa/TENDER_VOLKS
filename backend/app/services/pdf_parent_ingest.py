import time
from pathlib import Path
from typing import Dict, Any, List
from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid
from backend.app.services.pdf_link_extractor import extract_links_and_mentions
from backend.app.services.field_extractor import extract_tender_fields
from backend.app.services.info_sheet_generator import generate_info_sheet_csv
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


# BUG 3 FIX: Field precedence constants defining field ownership rules
ATC_SOURCED_LABELS = {
    "Processing Fee", "Tender Fee", "EMD Amount", "Payment Terms %", "Payment Terms",
    "Commercial Evaluation Type", "Reverse Auction Applicable", "Delivery Time",
    "PBG Mode", "SD Required", "SD Mode", "SD %", "SD Duration",
    "LD Applicable", "LD Percentage", "LD Max", "Courier Information", "Client Contacts",
    "Processing Fee Amount", "Tender Fee Amount", "EMD Amount / Total", "PBG Percentage",
    "SD Percentage", "LD Percentage per Week", "Max LD Percentage", "Courier Address"
}

MAIN_SOURCED_LABELS = {
    "PBG Required", "PBG Percentage", "PBG Duration", "PBG Duration (Months)",
    "Eligibility Criterion (Years)", "Bid Validity (Days)", "Bid Validity Period",
    "Tender Name / Title", "Reference ID / NIT No", "Estimated Tender Value",
    "Organisation", "Authority Agency"
}

AMBIGUOUS_LABELS = {
    "Installation Inclusive", "Custom Eligibility Criteria", "Custom Rules",
    "delivery_time_installation_inclusive", "custom_eligibility_criteria", "custom_rules"
}


def _resolve_top_level_fields(sections: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Walks info-sheet sections and maps field labels to top-level tender values.
    Uses exact labels as emitted by field_extractor.py.
    Falls back to empty string if a field is not found or has 'missing' status.
    """
    # Map: field_extractor label -> top-level key name
    label_map = {
        "Tender Name / Title": "title",
        "Reference ID / NIT No": "reference_id",
        "Authority Agency": "authorityName",
        "Department": "department",
        "Estimated Tender Value": "tenderValue",
        "EMD Amount": "emdAmount",
        "Tender Fee": "tenderFee",
        "Bid Submission Deadline": "deadline",
        "Technical Bid Opening Date": "bidOpeningDate",
        "Location of Site": "location",
        "Contact Officer": "contactOfficer",
    }

    resolved: Dict[str, str] = {}
    for sec in sections:
        for f in sec.get("fields", []):
            label = f.get("label", "")
            status = f.get("status", "")
            value = f.get("value", "")
            if label in label_map and status != "missing" and value:
                resolved[label_map[label]] = value

    return resolved


def _compute_parse_confidence(page_texts: List[Dict[str, Any]], sections: List[Dict[str, Any]]) -> float:
    """
    Calculates overall parse confidence from two signals:
    1. Average page-level OCR confidence (weight 0.6)
    2. Field extraction hit rate (weight 0.4)
    """
    # Page confidence
    page_confs = [p.get("confidence", 0.0) for p in page_texts if p.get("confidence") is not None]
    avg_page_conf = sum(page_confs) / len(page_confs) if page_confs else 50.0

    # Field hit rate
    total_fields = 0
    extracted_fields = 0
    for sec in sections:
        for f in sec.get("fields", []):
            total_fields += 1
            if f.get("status") == "extracted" and f.get("value"):
                extracted_fields += 1
    field_hit_rate = (extracted_fields / total_fields * 100) if total_fields > 0 else 0.0

    confidence = (avg_page_conf * 0.6) + (field_hit_rate * 0.4)
    return round(min(confidence, 100.0), 1)


def ingest_parent_tender_pdf(
    job_id: str,
    pdf_path: Path,
    original_filename: str
) -> Dict[str, Any]:
    """
    Coordinates the full OCR, hyperlink extraction, and info-sheet generation pipeline.
    Saves outputs in the job directory and returns structured conforming tender details.
    """
    job_dir = pdf_path.parent
    pages_dir = job_dir / "pages"

    # 1. Hybrid text extraction (Native PDF search + PaddleOCR fallback)
    page_texts = extract_pdf_text_hybrid(str(pdf_path), pages_dir)

    # 2. Extract clickable hyperlinks and document mentions
    links, mentions = extract_links_and_mentions(str(pdf_path))

    # 3. Deterministic Field Extraction
    title_raw = original_filename.replace(".pdf", "").replace("_", " ").replace("-", " ")
    
    # Classify document type using page 1 text
    page1_text = page_texts[0].get("text", "") if page_texts else ""
    from ocr.pipeline import classify_document_type
    doc_type = classify_document_type(page1_text)
    
    sections = extract_tender_fields(page_texts, title_raw, document_type=doc_type)

    # 3a. Bridge resolved ATC link URL to sections atc_document_link_present field
    matched_atc_link = None
    for l in links:
        url_str = l.get("url", "")
        name_str = l.get("name", "")
        anchor_str = l.get("anchorText", "")
        if l.get("is_atc_anchor") or any("atc" in s.lower() for s in (url_str, name_str, anchor_str)):
            matched_atc_link = l
            break

    if matched_atc_link and matched_atc_link.get("url"):
        target_url = matched_atc_link["url"]
        anchor_snippet = matched_atc_link.get("anchorText") or "ATC Hyperlink Annotation"
        for sec in sections:
            for f in sec.get("fields", []):
                if f.get("label") == "atc_document_link_present":
                    f["value"] = target_url
                    f["status"] = "extracted"
                    f["sourceSnippet"] = anchor_snippet

    atc_path = None
    for l in links:
        if l.get("local_path") and Path(l["local_path"]).exists():
            url_s = l.get("url", "").lower()
            name_s = l.get("name", "").lower()
            anchor_s = l.get("anchorText", "").lower()
            if l.get("is_atc_anchor") or any("atc" in s for s in (url_s, name_s, anchor_s)):
                atc_path = Path(l["local_path"])
                break

    if not atc_path:
        ext_children_dir = job_dir / "extracted_children"
        if ext_children_dir.exists():
            child_pdfs = [p for p in ext_children_dir.glob("*.pdf") if p.is_file() and p.stat().st_size > 0]
            if child_pdfs:
                atc_path = child_pdfs[0]
                logger.info(f"[ATC_RESOLVER] Discovered extracted child PDF in job directory: '{atc_path}'")

    # --- ATC PRECONDITION GUARD ---
    # If the main tender PDF contained an ATC hyperlink but the downloaded file is
    # unavailable (None path or non-existent file), surface a structured warning so
    # the infosheet clearly signals that ATC-sourced fields may be incomplete.
    atc_link_was_detected = matched_atc_link is not None
    atc_pdf_was_ingested = atc_path is not None
    if atc_link_was_detected and not atc_pdf_was_ingested:
        logger.warning(
            "[ATC_RESOLVER] ATC_NOT_FETCHED: ATC hyperlink detected in tender "
            f"'{original_filename}' but no local ATC PDF is available. "
            "ATC-sourced fields (Payment Terms, LD/PRS, Contacts, Courier) "
            "will remain at main-document values."
        )
        # Inject a visible warning field into the first section
        warning_field = {
            "id": "atc-not-fetched-warning",
            "label": "ATC Not Fetched Warning",
            "value": (
                f"ATC hyperlink detected (URL: {matched_atc_link.get('url', 'unknown')}) "
                "but ATC PDF was not downloaded or supplied. "
                "Payment Terms %, LD/PRS, Client Contacts and Courier Address "
                "may be incomplete — reprocess with ATC PDF attached."
            ),
            "status": "warning",
            "confidence": 0.0,
            "critical": True,
            "source": "derived",
            "sourceSnippet": "ATC_NOT_FETCHED guard: atc_link_detected=True, atc_pdf_ingested=False",
        }
        if sections:
            sections[0].setdefault("fields", []).insert(0, warning_field)
        else:
            sections.append({"id": "sec-warnings", "title": "Pipeline Warnings", "fields": [warning_field]})

    merged_atc_field_count = 0
    if atc_path:
        try:
            logger.info(f"[ATC_RESOLVER] Ingest pipeline parsing downloaded ATC child PDF: '{atc_path}'...")
            atc_pages_dir = job_dir / "atc_pages"
            atc_page_texts = extract_pdf_text_hybrid(str(atc_path), atc_pages_dir)
            atc_sections = extract_tender_fields(atc_page_texts, f"{title_raw} ATC", document_type="generic_nit")
            
            # Upsert standalone resolve_atc_anchor_fields output into atc_sections (Task 2)
            atc_full_text = "\n".join([p.get("text", "") for p in atc_page_texts])
            from backend.app.services.tender_mapper import resolve_atc_anchor_fields
            resolved_atc = resolve_atc_anchor_fields(atc_full_text)
            
            schema_label_map = {
                "ld_percentage_per_week": "LD Percentage per Week",
                "max_ld_percentage": "Max LD Percentage",
                "maf_required": "MAF Required",
                "payment_terms_supply_percent": "Payment Terms %",
                "payment_terms_installation_percent": "Payment Terms Installation (%)",
                "sd_mode": "Security Deposit Mode",
                "sd_required": "Security Deposit Required",
                "sd_percentage": "Security Deposit %",
                "sd_duration": "Security Deposit Duration"
            }
            if atc_sections:
                sec_to_update = atc_sections[0]
                for key, val in resolved_atc.items():
                    lbl = schema_label_map.get(key, key.replace("_", " ").title())
                    sec_to_update.setdefault("fields", []).append({
                        "id": f"f-{key}",
                        "label": lbl,
                        "field_name": key,
                        "value": val,
                        "status": "extracted",
                        "confidence": 85.0,
                        "source": "atc"
                    })
            
            # BUG 4 FIX: Build label -> (section_index, field_index) map to preserve section layout
            label_to_loc = {}
            for sec_idx, sec in enumerate(sections):
                for f_idx, field in enumerate(sec.get("fields", [])):
                    lbl = field.get("label")
                    if lbl and lbl not in label_to_loc:
                        label_to_loc[lbl] = (sec_idx, f_idx)

            atc_new_fields = []
            for atc_sec in atc_sections:
                for f in atc_sec.get("fields", []):
                    lbl = f.get("label")
                    val = f.get("value")
                    # Check if ATC value is valid (non-empty, non-zero, non-stub)
                    is_val_valid = val not in (None, "", "Not Found", "Out of Scope (Stage 1)", 0, 0.0, "0", "0.0", "0.00")
                    if is_val_valid:
                        # BUG 3 FIX: MAIN_SOURCED_LABELS are never overridden by ATC
                        if lbl in MAIN_SOURCED_LABELS:
                            continue

                        f_copy = dict(f)
                        f_copy["source"] = "atc"

                        if lbl in label_to_loc:
                            sec_idx, field_idx = label_to_loc[lbl]
                            existing_field = sections[sec_idx]["fields"][field_idx]
                            old_val = existing_field.get("value")

                            if lbl in AMBIGUOUS_LABELS:
                                old_valid = old_val not in (None, "", "Not Found", "Out of Scope (Stage 1)", 0, 0.0, "0", "0.0", "0.00")
                                if old_valid:
                                    amb_copy = dict(existing_field)
                                    amb_copy["value"] = {"main_tender": old_val, "atc": val}
                                    amb_copy["source"] = "ambiguous_preserved"
                                    amb_copy["status"] = "extracted"
                                    sections[sec_idx]["fields"][field_idx] = amb_copy
                                    merged_atc_field_count += 1
                                    logger.info(
                                        f"[FIELD_MERGE] Field: {lbl} | Old value: {old_val!r} | "
                                        f"New value (atc): {val!r} | Reason: ambiguous-preserved"
                                    )
                                    continue

                            if lbl in ATC_SOURCED_LABELS:
                                # BUG 3 FIX: ATC_SOURCED_LABELS always override main doc
                                sections[sec_idx]["fields"][field_idx] = f_copy
                                merged_atc_field_count += 1
                                logger.info(
                                    f"[FIELD_MERGE] Field: {lbl} | Old value: {old_val!r} | "
                                    f"New value (atc): {val!r} | Reason: atc-authoritative-override"
                                )
                            else:
                                # Unlisted labels use fill-if-missing
                                if existing_field.get("status") == "missing" or not old_val or old_val in ("Not Found", "Out of Scope (Stage 1)"):
                                    sections[sec_idx]["fields"][field_idx] = f_copy
                                    merged_atc_field_count += 1
                                    logger.info(
                                        f"[FIELD_MERGE] Field: {lbl} | Old value: {old_val!r} | "
                                        f"New value (atc): {val!r} | Reason: atc-fill-if-missing"
                                    )
                        else:
                            # BUG 4 FIX: Genuinely new field from ATC -> add to ATC-Sourced Fields section
                            atc_new_fields.append(f_copy)
                            merged_atc_field_count += 1
                            logger.info(
                                f"[FIELD_MERGE] Field: {lbl} | Old value: None | "
                                f"New value (atc): {val!r} | Reason: atc-new-field"
                            )

            # BUG 4 FIX: Append genuinely new ATC fields into a dedicated section instead of flattening
            if atc_new_fields:
                atc_sec_idx = None
                for idx, sec in enumerate(sections):
                    if sec.get("title") == "ATC-Sourced Fields":
                        atc_sec_idx = idx
                        break

                if atc_sec_idx is not None:
                    sections[atc_sec_idx]["fields"].extend(atc_new_fields)
                else:
                    sections.append({
                        "id": "sec-atc-sourced",
                        "title": "ATC-Sourced Fields",
                        "fields": atc_new_fields
                    })

            if merged_atc_field_count > 0:
                logger.info(f"[ATC_RESOLVER] ATC_PARSE_SUCCESS: Merged {merged_atc_field_count} fields from ATC PDF '{atc_path}'.")
            else:
                logger.warning(f"[ATC_RESOLVER] ATC_PARSE_NO_FIELDS: ATC PDF '{atc_path}' parsed successfully but yielded 0 mergeable fields.")
        except Exception as atc_err:
            logger.warning(f"[ATC_RESOLVER] ATC_PARSE_FAILED: Error processing ATC PDF '{atc_path}': {atc_err}. Continuing with main tender parsing only.")

    # 3b. Normalize Financial Exemption status if Financial Criteria is NOT APPLICABLE
    all_text_combined = " ".join([p.get("text", "") for p in page_texts]).lower()
    if "financial criteria" in all_text_combined and "not applicable" in all_text_combined:
        fin_keywords = {"turnover", "solvency", "net worth", "working capital", "financial"}
        for sec in sections:
            is_fin_sec = any(kw in sec.get("title", "").lower() for kw in fin_keywords)
            for f in sec.get("fields", []):
                lbl = (f.get("label") or f.get("id") or "").lower()
                if is_fin_sec or any(kw in lbl for kw in fin_keywords):
                    f["value"] = "Exempt / Not Applicable"
                    f["status"] = "exempt"
                    f["confidence"] = 99.0
                    f["sourceSnippet"] = "Financial Criteria explicitly declared NOT APPLICABLE in Tender BEC (Section-II)"

    # 4. Generate XLSX Spreadsheet Info Sheet
    csv_filename = f"{original_filename.replace('.pdf', '')}_InfoSheet.xlsx"
    csv_path = job_dir / csv_filename
    try:
        from backend.app.services.tender_mapper import build_infosheet_data
        infosheet_data = build_infosheet_data(sections, page_texts, job_id=job_id)
        generate_info_sheet_csv(infosheet_data, str(csv_path))
    except Exception as e:
        logger.error(f"Failed to generate info sheet workbook for job {job_id}: {e}", exc_info=True)
        raise e

    # 5. Resolve top-level fields from extracted sections (NO hardcoded fallbacks)
    resolved = _resolve_top_level_fields(sections)

    tender_title = resolved.get("title", title_raw)
    authority = resolved.get("authorityName", "")
    tender_value = resolved.get("tenderValue", "")
    emd_amount = resolved.get("emdAmount", "")
    tender_fee = resolved.get("tenderFee", "")
    deadline_val = resolved.get("deadline", "")
    location = resolved.get("location", "")

    # 6. Compute confidence from actual OCR data
    parse_confidence = _compute_parse_confidence(page_texts, sections)

    # 7. Build document groups
    source_docs = [
        {
            "id": f"src-{job_id}",
            "name": original_filename,
            "kind": "pdf",
            "origin": "source",
            "url": f"/storage/jobs/{job_id}/{original_filename}",
            "downloadable": True,
            "openable": True,
            "isPrimary": True,
            "uploadedBy": "System"
        }
    ]

    gen_outputs = [
        {
            "id": f"out-{job_id}",
            "name": csv_filename,
            "kind": "xlsx",
            "origin": "generated",
            "url": f"/storage/jobs/{job_id}/{csv_filename}",
            "downloadable": True,
            "openable": True,
            "generator": "ocr",
            "outputKind": "info_sheet"
        }
    ]

    extracted_pdfs = []
    for idx, l in enumerate(links):
        extracted_pdfs.append({
            "id": f"link-{job_id}-{idx+1}",
            "name": l["name"],
            "kind": "pdf",
            "origin": "linked",
            "url": l["url"],
            "downloadable": True,
            "openable": True,
            "extractedFromDocumentId": f"src-{job_id}",
            "sourcePage": l["sourcePage"],
            "anchorText": l["anchorText"],
            "extractionConfidence": l["extractionConfidence"],
            "local_path": l.get("local_path")
        })

    mentioned_docs = []
    for idx, m in enumerate(mentions):
        mentioned_docs.append({
            "id": f"ment-{job_id}-{idx+1}",
            "name": m["name"],
            "kind": "xlsx" if "boq" in m["name"].lower() else "pdf",
            "origin": "mentioned",
            "mentionText": m["mentionText"],
            "sourcePage": m["sourcePage"],
            "resolved": False
        })

    # 8. Count issues: missing critical fields + unresolved mentions + ATC warnings
    issues = 0
    for sec in sections:
        for f in sec.get("fields", []):
            if f.get("critical") and f.get("status") == "missing":
                issues += 1
            elif f.get("critical") and f.get("status") == "warning":
                # ATC_NOT_FETCHED and other pipeline warnings count as actionable issues
                issues += 1
            elif f.get("critical") and f.get("confidence", 100) < 70:
                issues += 1
    issues += len(mentioned_docs)

    # 9. Build conforming detailed tender payload
    payload = {
        "id": job_id,
        "title": tender_title,
        "authorityName": authority,
        "deadline": deadline_val,
        "tenderValue": tender_value,
        "emdAmount": emd_amount,
        "tenderFee": tender_fee,
        "location": location,
        "documents": {
            "sourceDocuments": source_docs,
            "generatedOutputs": gen_outputs,
            "extractedLinkedPdfs": extracted_pdfs,
            "mentionedAttachments": mentioned_docs
        },
        "infoSheetSections": sections,
        "rawTextPages": [
            {"page": p["page"], "text": p["text"]} for p in page_texts
        ],
        "parse_status": "completed",
        "parse_confidence": parse_confidence,
        "review_status": "unreviewed",
        "issues_count": issues
    }

    return payload
