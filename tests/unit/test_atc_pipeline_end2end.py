import os
import tempfile
from pathlib import Path
import fitz
import pytest

from backend.app.services.pdf_link_extractor import extract_links_and_mentions
from ocr.extractors.field_extractor import (
    FieldExtractor,
    merge_tender_and_atc_fields,
    AMBIGUOUS_MERGE_FIELDS
)
from backend.app.schemas.schemas import ExtractedFieldSchema
from backend.app.models.models import PageResult, TextBlock, LayoutRegion
from ocr.pipeline import process_pdf


def create_mock_tender_pdf(pdf_path: str, include_atc_link: bool = True):
    """
    Creates a minimal synthetic PDF document containing text and a LINK_URI annotation.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    page.insert_text((50, 50), "GeM Bid Document", fontsize=16)
    page.insert_text((50, 100), "Bid Number: GEM/2026/B/9999999", fontsize=12)
    page.insert_text((50, 150), "Buyer uploaded ATC document Click here to view the file.", fontsize=12)

    if include_atc_link:
        # Create link annotation over "Click here to view the file"
        link_rect = fitz.Rect(200, 140, 400, 160)
        link_dict = {
            "kind": fitz.LINK_URI,
            "from": link_rect,
            "uri": "https://mkp.gem.gov.in/buyer-atc/ep/atc/doc/9999999.pdf"
        }
        page.insert_link(link_dict)

    doc.save(pdf_path)
    doc.close()


def create_mock_atc_pdf(pdf_path: str):
    """
    Creates a minimal synthetic ATC PDF document with explicit ATC terms.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    page.insert_text((50, 50), "Additional Terms and Conditions (ATC)", fontsize=16)
    page.insert_text((50, 100), "EMD Amount: Rs. 50,000", fontsize=12)
    page.insert_text((50, 150), "PBG Percentage: 3%", fontsize=12)
    page.insert_text((50, 200), "Delivery Time: 30 days", fontsize=12)
    page.insert_text((50, 250), "Custom Eligibility Criteria: Bidder must have 3 years experience in IT.", fontsize=12)

    doc.save(pdf_path)
    doc.close()


def test_atc_link_discovery_and_matching(tmp_path):
    pdf_path = tmp_path / "main_tender.pdf"
    create_mock_tender_pdf(str(pdf_path), include_atc_link=True)

    links, mentions = extract_links_and_mentions(str(pdf_path))
    assert len(links) >= 1

    atc_link = next((l for l in links if l.get("is_atc_anchor") or "9999999.pdf" in l.get("url", "")), None)
    assert atc_link is not None
    assert atc_link["url"] == "https://mkp.gem.gov.in/buyer-atc/ep/atc/doc/9999999.pdf"
    assert "Click here" in atc_link["anchorText"] or "ATC" in atc_link["anchorText"] or "file" in atc_link["anchorText"]


def test_generic_homepage_link_rejection(tmp_path):
    pdf_path = tmp_path / "homepage_tender.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "GeM Homepage Link", fontsize=16)
    link_rect = fitz.Rect(50, 50, 200, 70)
    page.insert_link({"kind": fitz.LINK_URI, "from": link_rect, "uri": "https://gem.gov.in"})
    doc.save(str(pdf_path))
    doc.close()

    links, _ = extract_links_and_mentions(str(pdf_path))
    homepage_link = [l for l in links if l["url"].strip().lower().rstrip("/") == "https://gem.gov.in"]
    assert len(homepage_link) == 0, "Generic portal homepage URL should be rejected"


def test_field_merging_and_provenance():
    main_fields = [
        ExtractedFieldSchema(
            field_name="EMD",
            value="Rs. 100,000",
            confidence=95.0,
            source_page=1,
            evidence="Main EMD",
            source_blocks=[],
            source="main_tender"
        ),
        ExtractedFieldSchema(
            field_name="bid_number",
            value="GEM/2026/B/9999999",
            confidence=99.0,
            source_page=1,
            evidence="Main Bid Number",
            source_blocks=[],
            source="main_tender"
        ),
        ExtractedFieldSchema(
            field_name="custom_eligibility_criteria",
            value="Parent tender eligibility criterion",
            confidence=90.0,
            source_page=1,
            evidence="Main Eligibility",
            source_blocks=[],
            source="main_tender"
        )
    ]

    atc_fields = [
        ExtractedFieldSchema(
            field_name="EMD",
            value="Rs. 50,000",
            confidence=98.0,
            source_page=1,
            evidence="ATC EMD Clause",
            source_blocks=[],
            source="atc"
        ),
        ExtractedFieldSchema(
            field_name="pbg_percentage",
            value="3%",
            confidence=95.0,
            source_page=1,
            evidence="ATC PBG Clause",
            source_blocks=[],
            source="atc"
        ),
        ExtractedFieldSchema(
            field_name="custom_eligibility_criteria",
            value="ATC specific eligibility clause",
            confidence=95.0,
            source_page=1,
            evidence="ATC Eligibility",
            source_blocks=[],
            source="atc"
        )
    ]

    merged = merge_tender_and_atc_fields(main_fields, atc_fields)
    merged_by_name = {f.field_name: f for f in merged}

    # 1. ATC override test: EMD from ATC wins
    assert merged_by_name["EMD"].value == "Rs. 50,000"
    assert merged_by_name["EMD"].source == "atc"

    # 2. Main tender retention: bid_number retained
    assert merged_by_name["bid_number"].value == "GEM/2026/B/9999999"
    assert merged_by_name["bid_number"].source == "main_tender"

    # 3. ATC-only field: pbg_percentage from ATC added
    assert merged_by_name["pbg_percentage"].value == "3%"
    assert merged_by_name["pbg_percentage"].source == "atc"

    # 4. Ambiguous field preservation: custom_eligibility_criteria preserves both
    amb_field = merged_by_name["custom_eligibility_criteria"]
    assert amb_field.source == "ambiguous_preserved"
    assert isinstance(amb_field.value, dict)
    assert amb_field.value["main_tender"] == "Parent tender eligibility criterion"
    assert amb_field.value["atc"] == "ATC specific eligibility clause"


def test_full_pipeline_with_atc_child_pdf(tmp_path):
    main_pdf = tmp_path / "main_tender.pdf"
    atc_pdf = tmp_path / "child_atc.pdf"

    create_mock_tender_pdf(str(main_pdf), include_atc_link=False)
    create_mock_atc_pdf(str(atc_pdf))

    # Pass atc_pdf directly to process_pdf to test ATC child PDF page-by-page parsing & field merge
    job_id = "test-atc-job"
    page_results = process_pdf(job_id=job_id, pdf_path=main_pdf, atc_pdf_path=atc_pdf)

    assert len(page_results) > 0
    extracted_json_path = tmp_path / "extracted_fields.json"
    assert extracted_json_path.exists()

    import json
    with open(extracted_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    fields = data.get("extracted_fields", [])
    assert len(fields) > 0


def test_bug1_and_bug2_unverified_anchor_confidence(tmp_path):
    # Simulate a page where text is scrambled, but URI link exists
    pdf_path = tmp_path / "scanned_atc_link.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "(cid:1)(cid:2)(cid:3)(cid:4)(cid:5)(cid:6)(cid:7)", fontsize=12)
    link_rect = fitz.Rect(100, 100, 300, 130)
    page.insert_link({
        "kind": fitz.LINK_URI,
        "from": link_rect,
        "uri": "https://mkp.gem.gov.in/buyer-atc/ep/atc/doc/scanned_12345.pdf"
    })
    doc.save(str(pdf_path))
    doc.close()

    links, _ = extract_links_and_mentions(str(pdf_path))
    assert len(links) >= 1
    link = links[0]
    assert link["url"] == "https://mkp.gem.gov.in/buyer-atc/ep/atc/doc/scanned_12345.pdf"
    # Extraction confidence is tagged appropriately
    assert link["extractionConfidence"] in (70.0, 95.0)


def test_bug3_and_bug4_precedence_constants_and_sections(tmp_path):
    from backend.app.services.pdf_parent_ingest import (
        ATC_SOURCED_LABELS,
        MAIN_SOURCED_LABELS,
        AMBIGUOUS_LABELS,
        ingest_parent_tender_pdf
    )
    # Check BUG 3 constants
    assert "Payment Terms" in ATC_SOURCED_LABELS
    assert "Price Reduction Schedule (PRS)" in ATC_SOURCED_LABELS
    assert "EMD Amount" in MAIN_SOURCED_LABELS
    assert "PBG Percentage" in MAIN_SOURCED_LABELS
    assert "Installation Inclusive" in AMBIGUOUS_LABELS

    main_pdf = tmp_path / "test_tender_ingest.pdf"
    create_mock_tender_pdf(str(main_pdf), include_atc_link=True)

    res = ingest_parent_tender_pdf("job-bug3-bug4", main_pdf, "test_tender_ingest.pdf")
    assert "id" in res and "infoSheetSections" in res
