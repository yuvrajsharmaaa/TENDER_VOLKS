import pytest
import os
from backend.app.services.field_extractor import extract_tender_fields
from backend.app.services.tender_mapper import build_infosheet_data
from backend.app.services.export_service import export_tender_information_csv

def test_unified_extractor_and_regex_fallback():
    # 1. Test case: Tabular layouts should not cause cross-column contamination on fallback regexes
    pages_tabular = [
        {
            "page": 1,
            "text": "Organization    EMD Required    Tender Value\nABC Corp        Yes             500000\nSome other text"
        }
    ]
    sections_tab = extract_tender_fields(pages_tabular, "Test Tender")
    infosheet_tab = build_infosheet_data(sections_tab, pages_tabular)
    
    # organization and emd_required should NOT be cross-matched to adjacent cells by the regex fallbacks
    assert infosheet_tab.get("organization") == "NA" # Ignored by regex fallback (tabular)
    assert infosheet_tab.get("emd_required_display") == "NA" # Ignored by regex fallback (tabular)

    # 2. Test case: Safe fallbacks (same-line colon and strict next-line) should work
    pages_safe = [
        {
            "page": 1,
            "text": "Organization: ABC Corp\n\nEMD Required\nYes\n\nSome other text"
        }
    ]
    sections_safe = extract_tender_fields(pages_safe, "Test Tender")
    infosheet_safe = build_infosheet_data(sections_safe, pages_safe)
    
    assert infosheet_safe.get("organization") == "ABC Corp" # Matched by same-line colon
    assert infosheet_safe.get("emd_required_display") == "Yes" # Matched by strict next-line
    
    # 3. Test case: Inline values without colons (like "Bid Validity (Days) 90 Days") are parsed
    pages_inline = [
        {
            "page": 1,
            "text": "Bid Validity (Days) 90 Days\nEMD Required Yes\nPBG Duration (Months) 6 Months"
        }
    ]
    sections_inline = extract_tender_fields(pages_inline, "Test Tender")
    infosheet_inline = build_infosheet_data(sections_inline, pages_inline)
    
    assert infosheet_inline.get("bid_validity_days_display") == "90 Days"
    assert infosheet_inline.get("emd_required_display") == "Yes"
    assert infosheet_inline.get("pbg_duration_display") == "6 Months"
    
    # 4. Test case: Stringified list values are parsed and formatted cleanly without corruption
    infosheet_safe["tender_value"] = '["Value 1", "Value 2"]'
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        csv_path = export_tender_information_csv(infosheet_safe, output_dir=td)
        assert os.path.exists(csv_path)
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            # It should be joined by pipe and not contain literal brackets
            assert 'Value 1|Value 2' in content
            assert '["Value 1", "Value 2"]' not in content

def test_mappings_priority_bullets_and_metadata():
    # 1. Verify organisation_name, bid_number, and ministry_name map to legacy labels
    # 2. Verify trace metadata (sourcePage, sourceSnippet, confidence, status) is preserved
    pages = [
        {
            "page": 1,
            "text": "Bid Number/बोली क्रमांक: GEM/2025/B/6126307\nOrganisation Name: Indian Air Force\nBid Validity Period 90 Days\nEMD Required No"
        }
    ]
    sections = extract_tender_fields(pages, "Test Aliases")
    
    # Check trace preservation
    org_field = None
    bid_num_field = None
    for sec in sections:
        for f in sec.get("fields", []):
            if f["label"] == "Organisation":
                org_field = f
            elif f["label"] == "Reference ID / NIT No":
                bid_num_field = f
                
    assert org_field is not None
    assert org_field["value"] == "Indian Air Force"
    assert org_field["sourcePage"] == 1
    assert org_field["confidence"] > 0.0
    assert org_field["status"] == "extracted"
    
    assert bid_num_field is not None
    assert bid_num_field["value"] == "GEM/2025/B/6126307"

    # 3. Verify field_lookup priority for validity days
    infosheet = build_infosheet_data(sections, pages)
    # bid_validity_days_display should use the spatial "Bid Validity Period" extraction ("90 Days") 
    # instead of returning "NA" or trying regex on non-existent "Bid Validity (Days)" label
    assert infosheet.get("bid_validity_days_display") == "90 Days"
    assert infosheet.get("organization") == "Indian Air Force"

    # 4. Verify list-bullet currency protection (Tender Value = 9 should be rejected)
    pages_bullet = [
        {
            "page": 1,
            "text": "Tender Value\n9. Reverse Auction would be conducted..."
        }
    ]
    sections_bullet = extract_tender_fields(pages_bullet, "Test Bullet")
    infosheet_bullet = build_infosheet_data(sections_bullet, pages_bullet)
    # The list-bullet "9" has no currency indicators and is < 100, so it must be rejected as currency
    assert infosheet_bullet.get("tender_value_display") == "NA"

if __name__ == "__main__":
    pytest.main([__file__])

