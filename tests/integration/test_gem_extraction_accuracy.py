import pytest
from ocr.extractors.gem_field_extractor import GemFieldExtractor
from backend.app.models.models import PageResult, TextBlock

TENDERS_GROUND_TRUTH = {
    "GEM/2026/B/7317018": {
        "emd_by_schedule": {1: 43000.0, 2: 7000.0},
        "emd_total": 50000.0,
        "emd_required": True,
        "reverse_auction_enabled": False,
        "ra_qualification_rule": None,
        "pbg_percentage": 5.0,
        "pbg_duration_months": 28,
        "bid_validity_days": 120,
        "evaluation_method": "Item wise evaluation",
        "rows": [
            ("EMD Detail", None),
            ("Advisory Bank", "State Bank of India"),
            ("Schedule 1 EMD Amount (In INR)", "43000"),
            ("Schedule 2 EMD Amount (In INR)", "7000"),
            ("ePBG Detail", None),
            ("Advisory Bank", "ICICI Bank"),
            ("ePBG Percentage(%)", "5.00"),
            ("Duration of ePBG required (Months)", "28"),
            ("Bid Details", None),
            ("Bid Offer Validity (Days)", "120"),
            ("Bid to RA enabled", "No"),
            ("Evaluation Method", "Item wise evaluation")
        ]
    },
    "GEM/2025/B/6232822": {
        "emd_by_schedule": {},
        "emd_total": 40000.0,
        "emd_required": True,
        "reverse_auction_enabled": True,
        "pbg_percentage": None,
        "pbg_duration_months": None,
        "bid_validity_days": 180,
        "evaluation_method": "Total value wise evaluation",
        "rows": [
            ("EMD Detail", None),
            ("EMD Amount (In INR)", "40000"),
            ("Bid Details", None),
            ("Bid Offer Validity", "180 (Days)"),
            ("Bid to RA enabled", "Yes"),
            ("Evaluation Method", "Total value wise evaluation")
        ]
    },
    "GEM/2025/B/6246461": {
        "emd_by_schedule": {},
        "emd_total": 0.0,
        "emd_required": False,
        "reverse_auction_enabled": False,
        "pbg_percentage": None,
        "pbg_duration_months": None,
        "bid_validity_days": 120,
        "evaluation_method": "Total value wise evaluation",
        "rows": [
            ("EMD Detail", None),
            ("Required", "No"),
            ("Bid Details", None),
            ("Bid Offer Validity", "120"),
            ("Bid to RA enabled", "No"),
            ("Evaluation Method", "Total value wise evaluation")
        ]
    },
    "GEM/2025/B/6263705": {
        "emd_by_schedule": {},
        "emd_total": 101230.0,
        "emd_required": True,
        "reverse_auction_enabled": False,
        "pbg_percentage": None,
        "pbg_duration_months": None,
        "bid_validity_days": 90,
        "evaluation_method": "Total value wise evaluation",
        "rows": [
            ("EMD Detail", None),
            ("EMD Amount", "1,01,230"),
            ("Bid Details", None),
            ("Bid Offer Validity", "90"),
            ("Bid to RA enabled", "No"),
            ("Evaluation Method", "Total value wise evaluation")
        ]
    },
    "GEM/2025/B/6620282": {
        "emd_by_schedule": {},
        "emd_total": 50000.0,
        "emd_required": True,
        "reverse_auction_enabled": False,
        "pbg_percentage": 5.0,
        "pbg_duration_months": 19,
        "bid_validity_days": 120,
        "evaluation_method": "Total value wise evaluation",
        "rows": [
            ("EMD Detail", None),
            ("EMD Amount", "50000"),
            ("ePBG Detail", None),
            ("ePBG Percentage(%)", "5.00"),
            ("Duration of ePBG required (Months)", "19"),
            ("Bid Details", None),
            ("Bid Offer Validity", "120"),
            ("Bid to RA enabled", "No"),
            ("Evaluation Method", "Total value wise evaluation")
        ]
    },
    "GEM/2025/B/6630054": {
        "emd_by_schedule": {},
        "emd_total": 286740.0,
        "emd_required": True,
        "reverse_auction_enabled": False,
        "pbg_percentage": 1.0,
        "pbg_duration_months": 6,
        "bid_validity_days": 30,
        "evaluation_method": "Total value wise evaluation",
        "rows": [
            ("EMD Detail", None),
            ("EMD Amount", "286740"),
            ("ePBG Detail", None),
            ("ePBG Percentage(%)", "1.00"),
            ("Duration of ePBG required (Months)", "6"),
            ("Bid Details", None),
            ("Bid Offer Validity", "30"),
            ("Bid to RA enabled", "No"),
            ("Evaluation Method", "Total value wise evaluation")
        ]
    },
    "GEM/2025/B/6748709": {
        "emd_by_schedule": {},
        "emd_total": 0.0,
        "emd_required": False,
        "reverse_auction_enabled": True,
        "ra_qualification_rule": "50% Lowest Priced Technically Qualified Bidders",
        "pbg_percentage": None,
        "pbg_duration_months": None,
        "bid_validity_days": 120,
        "evaluation_method": "Total value wise evaluation",
        "rows": [
            ("EMD Detail", None),
            ("Required", "No"),
            ("Bid Details", None),
            ("Bid Offer Validity", "120"),
            ("Bid to RA enabled", "Yes"),
            ("RA Qualification Rule", "50% Lowest Priced Technically Qualified Bidders"),
            ("Evaluation Method", "Total value wise evaluation")
        ]
    },
    "GEM/2025/B/6782142": {
        "emd_by_schedule": {},
        "emd_total": 48000.0,
        "emd_required": True,
        "reverse_auction_enabled": True,
        "ra_qualification_rule": "50% Lowest Priced Technically Qualified Bidders",
        "pbg_percentage": 3.0,
        "pbg_duration_months": 26,
        "bid_validity_days": 180,
        "evaluation_method": "Total value wise evaluation",
        "rows": [
            ("EMD Detail", None),
            ("EMD Amount", "48000"),
            ("ePBG Detail", None),
            ("ePBG Percentage(%)", "3.00"),
            ("Duration of ePBG required (Months)", "26"),
            ("Bid Details", None),
            ("Bid Offer Validity", "180"),
            ("Bid to RA enabled", "Yes"),
            ("RA Qualification Rule", "50% Lowest Priced Technically Qualified Bidders"),
            ("Evaluation Method", "Total value wise evaluation")
        ]
    },
    "GEM/2025/B/6902559": {
        "emd_by_schedule": {},
        "emd_total": 0.0,
        "emd_required": False,
        "reverse_auction_enabled": False,
        "pbg_percentage": None,
        "pbg_duration_months": None,
        "bid_validity_days": 180,
        "evaluation_method": "Total value wise evaluation",
        "rows": [
            ("EMD Detail", None),
            ("Required", "No"),
            ("Bid Details", None),
            ("Bid Offer Validity", "180"),
            ("Bid to RA enabled", "No"),
            ("Evaluation Method", "Total value wise evaluation")
        ]
    },
    "GEM/2025/B/6960382": {
        "emd_by_schedule": {},
        "emd_total": 28000.0,
        "emd_required": True,
        "reverse_auction_enabled": True,
        "ra_qualification_rule": "H1-Highest Priced Bid Elimination",
        "pbg_percentage": 3.0,
        "pbg_duration_months": 62,
        "bid_validity_days": 180,
        "evaluation_method": "Total value wise evaluation",
        "rows": [
            ("EMD Detail", None),
            ("EMD Amount", "28000"),
            ("ePBG Detail", None),
            ("ePBG Percentage(%)", "3.00"),
            ("Duration of ePBG required (Months)", "62"),
            ("Bid Details", None),
            ("Bid Offer Validity", "180"),
            ("Bid to RA enabled", "Yes"),
            ("RA Qualification Rule", "H1-Highest Priced Bid Elimination"),
            ("Evaluation Method", "Total value wise evaluation")
        ]
    }
}

def make_mock_blocks(rows):
    blocks = []
    y = 50
    for idx, (label, val) in enumerate(rows):
        if val is None:
            # Section header
            blocks.append(TextBlock(
                block_id=f"lbl_{idx}",
                text=label,
                confidence=0.95,
                bounding_box={"x1": 50, "y1": y, "x2": 250, "y2": y + 20},
                language_hint="en"
            ))
        else:
            # Key-value row
            blocks.append(TextBlock(
                block_id=f"lbl_{idx}",
                text=label,
                confidence=0.95,
                bounding_box={"x1": 50, "y1": y, "x2": 250, "y2": y + 20},
                language_hint="en"
            ))
            blocks.append(TextBlock(
                block_id=f"val_{idx}",
                text=val,
                confidence=0.90,
                bounding_box={"x1": 450, "y1": y, "x2": 650, "y2": y + 20},
                language_hint="en"
            ))
        y += 60
    return blocks

@pytest.mark.parametrize("bid_number, expected", TENDERS_GROUND_TRUTH.items())
def test_gem_extraction_accuracy(bid_number, expected):
    blocks = make_mock_blocks(expected["rows"])
    page = PageResult(
        job_id="test-job",
        page_number=1,
        image_path="",
        image_width_px=800,
        image_height_px=1000,
        processing_time_seconds=0.1,
        text_blocks=blocks,
        layout_regions=[]
    )
    
    extractor = GemFieldExtractor()
    extracted_fields = extractor.extract_fields([page])
    field_map = {f.field_name: f for f in extracted_fields}
    
    # Assert each ground truth value
    assert field_map["emd_required"].value == expected["emd_required"]
    assert field_map["emd_total"].value == expected["emd_total"]
    assert field_map["emd_by_schedule"].value == expected["emd_by_schedule"]
    assert field_map["reverse_auction_enabled"].value == expected["reverse_auction_enabled"]
    
    if "ra_qualification_rule" in expected:
        assert field_map["ra_qualification_rule"].value == expected["ra_qualification_rule"]
        
    if "pbg_percentage" in expected:
        assert field_map["pbg_percentage"].value == expected["pbg_percentage"]
        
    if "pbg_duration_months" in expected:
        assert field_map["pbg_duration_months"].value == expected["pbg_duration_months"]
        
    assert field_map["bid_validity_days"].value == expected["bid_validity_days"]
    assert field_map["evaluation_method"].value == expected["evaluation_method"]
