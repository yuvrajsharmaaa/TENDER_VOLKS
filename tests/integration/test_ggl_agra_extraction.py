import os
import tempfile
import shutil
from pathlib import Path
import pytest
from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
from backend.app.services.tender_mapper import (
    FIELD_STATUS_OK,
    FIELD_STATUS_NOT_APPLICABLE,
    FIELD_STATUS_MISSING
)

def test_ggl_agra_extraction():
    orig_pdf_path = "backend/app/storage/jobs/893c275d-44b5-4092-8833-b4d7c5c0af3b/GGL Agra VRLA.pdf"
    if not os.path.exists(orig_pdf_path):
        pytest.skip(f"GGL Agra PDF not found at {orig_pdf_path}")

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "GGL Agra VRLA.pdf"
        shutil.copy(orig_pdf_path, pdf_path)
        
        res = ingest_parent_tender_pdf(
            job_id="test-ggl-agra-verification",
            pdf_path=pdf_path,
            original_filename="GGL Agra VRLA.pdf"
        )
        
        status_sum = res.get("status_summary", {})
        field_sts = res.get("field_statuses", {})
        missing_fls = res.get("missing_fields", [])
        
        # Verify status summary exists and has all 4 status keys
        assert FIELD_STATUS_OK in status_sum
        assert FIELD_STATUS_NOT_APPLICABLE in status_sum
        assert FIELD_STATUS_MISSING in status_sum
        
        # Bug 1: Verify ATC Document Link points to PDF, not xlsx
        doc_links = res.get("documents", {}).get("extractedLinkedPdfs", [])
        atc_links = [l for l in doc_links if l.get("is_atc_anchor")]
        if atc_links:
            assert atc_links[0]["url"].endswith(".pdf")
            
        # Bug 2: Payment terms supply % should be N/A (no split, full payment within 15 days), not Past Performance 50%
        assert field_sts.get("sd_mode_display") == FIELD_STATUS_NOT_APPLICABLE
        assert field_sts.get("sd_percentage_display") == FIELD_STATUS_NOT_APPLICABLE
        
        # Bug 3: PBG is 5.0%, SD is N/A
        sections = res["infoSheetSections"]
        field_map = {}
        for sec in sections:
            for f in sec.get("fields", []):
                field_map[f.get("label", f.get("field_name"))] = f
                
        assert field_map.get("PBG Percentage", {}).get("value") == 5.0
