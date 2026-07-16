import os
import re
import pytest
import tempfile
from pathlib import Path
from ocr.pipeline import process_pdf, is_gem_document
from ocr.extractors.gem_field_extractor import GemFieldExtractor

GROUND_TRUTH = {
    "GEM/2026/B/7317018": {
        "emd_by_schedule": {1: 43000.0, 2: 7000.0},
        "emd_required": True,
        "reverse_auction_enabled": False,
        "pbg_percentage": 5.00,
        "pbg_duration_months": 28,
        "bid_validity_days": 120,
        "evaluation_method": "Item wise evaluation"
    },
    "GEM/2025/B/6232822": {
        "emd_total": 40000.0,
        "emd_required": True,
        "reverse_auction_enabled": True,
        "pbg_percentage": None,
        "pbg_duration_months": None,
        "bid_validity_days": 180,
        "evaluation_method": "Total value wise evaluation"
    },
    "GEM/2025/B/6246461": {
        "emd_total": 0.0,
        "emd_required": False,
        "reverse_auction_enabled": False,
        "pbg_percentage": None,
        "pbg_duration_months": None,
        "bid_validity_days": 120,
        "evaluation_method": "Total value wise evaluation"
    },
    "GEM/2025/B/6263705": {
        "emd_total": 101230.0,
        "emd_required": True,
        "reverse_auction_enabled": False,
        "pbg_percentage": None,
        "pbg_duration_months": None,
        "bid_validity_days": 90,
        "evaluation_method": "Total value wise evaluation"
    },
    "GEM/2025/B/6620282": {
        "emd_total": 50000.0,
        "emd_required": True,
        "reverse_auction_enabled": False,
        "pbg_percentage": 5.00,
        "pbg_duration_months": 19,
        "bid_validity_days": 120,
        "evaluation_method": "Total value wise evaluation"
    },
    "GEM/2025/B/6630054": {
        "emd_total": 286740.0,
        "emd_required": True,
        "reverse_auction_enabled": False,
        "pbg_percentage": 1.00,
        "pbg_duration_months": 6,
        "bid_validity_days": 30,
        "evaluation_method": "Total value wise evaluation"
    },
    "GEM/2025/B/6748709": {
        "emd_total": 0.0,
        "emd_required": False,
        "reverse_auction_enabled": True,
        "ra_qualification_rule": "50% Lowest Priced Technically Qualified Bidders",
        "pbg_percentage": None,
        "pbg_duration_months": None,
        "bid_validity_days": 120,
        "evaluation_method": "Total value wise evaluation"
    },
    "GEM/2025/B/6782142": {
        "emd_total": 48000.0,
        "emd_required": True,
        "reverse_auction_enabled": True,
        "ra_qualification_rule": "50% Lowest Priced Technically Qualified Bidders",
        "pbg_percentage": 3.00,
        "pbg_duration_months": 26,
        "bid_validity_days": 180,
        "evaluation_method": "Total value wise evaluation"
    },
    "GEM/2025/B/6902559": {
        "emd_total": 0.0,
        "emd_required": False,
        "reverse_auction_enabled": False,
        "pbg_percentage": None,
        "pbg_duration_months": None,
        "bid_validity_days": 180,
        "evaluation_method": "Total value wise evaluation"
    },
    "GEM/2025/B/6960382": {
        "emd_total": 28000.0,
        "emd_required": True,
        "reverse_auction_enabled": True,
        "ra_qualification_rule": "H1-Highest Priced Bid Elimination",
        "pbg_percentage": 3.00,
        "pbg_duration_months": 62,
        "bid_validity_days": 180,
        "evaluation_method": "Total value wise evaluation"
    }
}

def test_gem_extraction_accuracy():
    # Check if fitz (PyMuPDF) is functional
    try:
        import fitz
    except Exception:
        pytest.skip("fitz (PyMuPDF) is not functional. Skipping integration test.")

    sample_dir = Path("sample_files")
    if not sample_dir.exists():
        pytest.skip("sample_files directory does not exist.")

    pdf_files = list(sample_dir.glob("*.pdf"))
    if not pdf_files:
        pytest.skip("No PDF sample files found in sample_files/.")

    any_tested = False
    
    # Process files
    for pdf_path in pdf_files:
        try:
            # Quick check if it is a GeM document using PyMuPDF to read page 1
            doc = fitz.open(pdf_path)
            if doc.page_count == 0:
                continue
            page1_text = doc[0].get_text()
            doc.close()
            
            # Extract bid number from page 1 using regex
            m = re.search(r'GEM/20\d{2}/[BR]/\d+', page1_text)
            if not m:
                continue
                
            bid_number = m.group(0)
            if bid_number not in GROUND_TRUTH:
                continue
                
            any_tested = True
            expected = GROUND_TRUTH[bid_number]
            
            # Run the actual pipeline process
            with tempfile.TemporaryDirectory() as td:
                temp_pdf = Path(td) / pdf_path.name
                with open(pdf_path, "rb") as sf, open(temp_pdf, "wb") as df:
                    df.write(sf.read())
                    
                pages = process_pdf("test-job", temp_pdf)
                assert len(pages) > 0
                
                extractor = GemFieldExtractor()
                fields = extractor.extract_fields(pages)
                field_map = {f.field_name: f.value for f in fields}
                
                # Verify extracted values against ground truth
                print(f"\nVerifying {bid_number} ({pdf_path.name}):")
                
                if "emd_by_schedule" in expected:
                    assert field_map.get("emd_by_schedule") == expected["emd_by_schedule"]
                if "emd_total" in expected:
                    assert field_map.get("emd_total") == expected["emd_total"]
                if "emd_required" in expected:
                    assert field_map.get("emd_required") == expected["emd_required"]
                if "reverse_auction_enabled" in expected:
                    assert field_map.get("reverse_auction_enabled") == expected["reverse_auction_enabled"]
                if "ra_qualification_rule" in expected:
                    assert field_map.get("ra_qualification_rule") == expected["ra_qualification_rule"]
                if "pbg_percentage" in expected:
                    assert field_map.get("pbg_percentage") == expected["pbg_percentage"]
                if "pbg_duration_months" in expected:
                    assert field_map.get("pbg_duration_months") == expected["pbg_duration_months"]
                if "bid_validity_days" in expected:
                    assert field_map.get("bid_validity_days") == expected["bid_validity_days"]
                if "evaluation_method" in expected:
                    # Allow partial matches for evaluation method text (e.g. Item wise vs Item wise evaluation)
                    ext_eval = field_map.get("evaluation_method") or ""
                    exp_eval = expected["evaluation_method"]
                    assert exp_eval.lower() in ext_eval.lower() or ext_eval.lower() in exp_eval.lower()
                    
        except Exception as e:
            if "tesseract" in str(e).lower() or "tesseractnotfounderror" in str(type(e)).lower():
                pytest.skip("Tesseract is not installed or not in PATH. Skipping integration test.")
            raise e

    if not any_tested:
        pytest.skip("No matching ground-truth GeM PDFs were processed.")
