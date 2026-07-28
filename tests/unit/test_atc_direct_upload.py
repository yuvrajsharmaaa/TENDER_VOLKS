"""
Unit test verifying direct / standalone ATC document ingestion and parsing
"""

import pytest
from pathlib import Path
from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf

def test_direct_atc_document_ingestion():
    sample_atc = Path("sample_files/extracted_children/page6_177Tender_22ca0964-3fdd-4183-bbb81772690505617_buyer1.gil.rj.pdf")
    if not sample_atc.exists():
        pytest.skip("Sample ATC PDF not present")

    res = ingest_parent_tender_pdf("test-job-atc-direct", sample_atc, sample_atc.name)

    sections = res.get("infoSheetSections") or res.get("sections", [])
    atc_sourced_fields = []
    for sec in sections:
        for f in sec.get("fields", []):
            if f.get("source") == "atc":
                atc_sourced_fields.append(f)

    assert len(atc_sourced_fields) > 0, f"Expected ATC-sourced fields to be merged into output, got {len(atc_sourced_fields)}"
    atc_labels = [f.get("label") for f in atc_sourced_fields]
    assert "Payment Terms" in atc_labels or "Price Reduction Schedule (PRS)" in atc_labels
