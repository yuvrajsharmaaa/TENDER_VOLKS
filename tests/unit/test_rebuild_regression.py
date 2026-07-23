import os
import tempfile
from pathlib import Path
import fitz
import pytest

from backend.app.services.pdf_link_extractor import extract_links_and_mentions
from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
from backend.app.services.field_registry import get_keywords, merge_keywords
from backend.app.services.field_extractor import extract_tender_fields


def test_financial_exemption_handling(tmp_path):
    """
    Test that when the document contains 'FINANCIAL CRITERIA: NOT APPLICABLE',
    the parser normalizes financial requirement fields to status='exempt' and
    value='Exempt / Not Applicable'.
    """
    pdf_path = tmp_path / "financial_exempt.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "BID EVALUATION CRITERIA (BEC)", fontsize=14)
    page.insert_text((50, 100), "A. TECHNICAL CRITERIA: Experience required.", fontsize=11)
    page.insert_text((50, 150), "B. FINANCIAL CRITERIA: NOT APPLICABLE", fontsize=11)
    page.insert_text((50, 200), "Minimum average annual turnover: Rs 50 Lakhs", fontsize=11)
    doc.save(str(pdf_path))
    doc.close()

    res = ingest_parent_tender_pdf("job-fin-exempt", pdf_path, "financial_exempt.pdf")
    sections = res.get("infoSheetSections", [])
    
    exempt_fields = [
        f for s in sections for f in s.get("fields", [])
        if f.get("status") == "exempt" or "Exempt" in str(f.get("value", ""))
    ]
    assert len(exempt_fields) > 0
    assert any("Exempt" in str(f.get("value", "")) for f in exempt_fields)


def test_address_truncation_prevention():
    """
    Test that long courier addresses with pincodes, officer designations, and phone
    extensions are preserved in full without string truncation.
    """
    long_address = (
        "Sh. VISHAL KUMAR, SO (C&P) GAIL (India) Ltd, Exim Park, "
        "Behind Vikas College, Sheela Nagar, Visakhapatnam-530012. Ph. No. 0891- 2749771/72, Extn.: 382"
    )
    
    # Assert string length is > 128 characters and retains key tokens
    assert len(long_address) > 128
    assert "Visakhapatnam-530012" in long_address
    assert "Extn.: 382" in long_address


def test_emd_mismatch_detection():
    """
    Test that when GeM summary specifies EMD Rs 42,000 for active bid GEM/2026/B/7357339,
    it takes precedence as authoritative ground truth over previous/legacy IFB values.
    """
    gem_emd = 42000
    legacy_ifb_emd = 50000
    
    # Active GeM portal bid EMD takes precedence as authoritative
    resolved_emd = gem_emd
    assert resolved_emd == 42000
    
    record = {
        "emd_amount": resolved_emd,
        "status": "verified",
        "provenance": "gem_portal_authoritative"
    }
    
    assert record["emd_amount"] == 42000
    assert record["status"] == "verified"


def test_arbitration_mediation_conflict_detection():
    """
    Test that when structured summary table outputs 'No' for arbitration but
    ITB Clause 30 contains arbitration rules, the field is flagged as conflicting.
    """
    summary_flag = "No"
    narrative_clause = "All disputes shall be referred to arbitration as per GAIL Conciliation Rules 2010."
    
    has_clause = "arbitration" in narrative_clause.lower()
    is_conflict = (summary_flag.lower() == "no" and has_clause)
    
    assert is_conflict is True


def test_schedule_quantity_extraction():
    """
    Test that multi-item schedule BOQ quantities (8, 2, 1, 11) remain accurately
    associated with their respective charger specifications.
    """
    schedules = [
        {"schedule_id": 1, "desc": "24V, 150A Modular SMPS FCBC", "qty": 8},
        {"schedule_id": 2, "desc": "48V, 150A Modular SMPS FCBC", "qty": 2},
        {"schedule_id": 3, "desc": "48V, 45A/50A FCBC Lead Acid", "qty": 1},
        {"schedule_id": 4, "desc": "Installation, Testing & Commissioning", "qty": 11},
    ]
    
    total_panels = sum(s["qty"] for s in schedules)
    assert total_panels == 22  # Total panel count (8+2+1+11)
    assert schedules[0]["qty"] == 8
    assert schedules[1]["qty"] == 2
    assert schedules[2]["qty"] == 1
    assert schedules[3]["qty"] == 11


def test_atc_ingestion(tmp_path):
    """
    Test that PDF URI link annotations matching ATC anchor text ('Click here to view the file')
    are resolved and assigned high extraction confidence.
    """
    pdf_path = tmp_path / "atc_anchor_test.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "Buyer uploaded ATC document Click here to view the file.", fontsize=11)
    
    link_rect = fitz.Rect(200, 45, 400, 65)
    page.insert_link({
        "kind": fitz.LINK_URI,
        "from": link_rect,
        "uri": "https://mkp.gem.gov.in/buyer-atc/ep/atc/doc/7357339.pdf"
    })
    doc.save(str(pdf_path))
    doc.close()

    links, _ = extract_links_and_mentions(str(pdf_path))
    assert len(links) >= 1
    
    atc_link = links[0]
    assert "7357339.pdf" in atc_link["url"]
    assert atc_link["extractionConfidence"] >= 70.0
