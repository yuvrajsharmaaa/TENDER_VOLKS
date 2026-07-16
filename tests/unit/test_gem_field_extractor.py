import pytest
from ocr.extractors.gem_field_extractor import (
    detect_column_split,
    merge_into_cells,
    pair_cells_by_row,
    match_field,
    normalize_indian_currency,
    validate_field,
    field_confidence,
    GemFieldExtractor
)
from backend.app.models.models import TextBlock

def test_detect_column_split():
    # Blocks with a distinct gap in the middle
    blocks = [
        TextBlock(block_id="1", text="Label1", confidence=1.0, bounding_box={"x1": 50, "y1": 100, "x2": 150, "y2": 120}, language_hint="en"),
        TextBlock(block_id="2", text="Value1", confidence=1.0, bounding_box={"x1": 350, "y1": 100, "x2": 450, "y2": 120}, language_hint="en"),
        TextBlock(block_id="3", text="Label2", confidence=1.0, bounding_box={"x1": 60, "y1": 150, "x2": 140, "y2": 170}, language_hint="en"),
        TextBlock(block_id="4", text="Value2", confidence=1.0, bounding_box={"x1": 360, "y1": 150, "x2": 440, "y2": 170}, language_hint="en"),
    ]
    # Gaps are between x2 and x1 of successive blocks when sorted.
    # x1 positions sorted: 50, 60, 350, 360.
    # Largest gap is between 60 and 350 (gap size = 290). Midpoint is 60 + 290 // 2 = 205.
    split = detect_column_split(blocks)
    assert 200 < split < 300

def test_merge_into_cells():
    # Blocks in same column with close y coords should merge
    blocks = [
        TextBlock(block_id="1", text="Line One", confidence=0.9, bounding_box={"x1": 50, "y1": 100, "x2": 150, "y2": 120}, language_hint="en"),
        TextBlock(block_id="2", text="Line Two", confidence=0.8, bounding_box={"x1": 50, "y1": 125, "x2": 150, "y2": 145}, language_hint="en"),
        TextBlock(block_id="3", text="Distinct Row", confidence=0.95, bounding_box={"x1": 50, "y1": 200, "x2": 150, "y2": 220}, language_hint="en"),
    ]
    cells = merge_into_cells(blocks, y_gap_tolerance=20)
    assert len(cells) == 2
    assert cells[0]["text"] == "Line One Line Two"
    assert cells[0]["bbox"]["y2"] == 145
    assert cells[1]["text"] == "Distinct Row"

def test_pair_cells_by_row():
    # Overlapping y-ranges should pair
    left_cells = [
        {"text": "Label A", "bbox": {"x1": 50, "y1": 100, "x2": 150, "y2": 140}, "blocks": []},
        {"text": "Label B", "bbox": {"x1": 50, "y1": 200, "x2": 150, "y2": 220}, "blocks": []},
    ]
    right_cells = [
        {"text": "Value B", "bbox": {"x1": 300, "y1": 195, "x2": 450, "y2": 225}, "blocks": []},
        {"text": "Value A", "bbox": {"x1": 300, "y1": 110, "x2": 450, "y2": 135}, "blocks": []},
    ]
    pairs = pair_cells_by_row(left_cells, right_cells)
    assert len(pairs) == 2
    # Check that Label A pairs with Value A (y overlap 110-135)
    p1 = next(p for p in pairs if p[0]["text"] == "Label A")
    assert p1[1]["text"] == "Value A"
    p2 = next(p for p in pairs if p[0]["text"] == "Label B")
    assert p2[1]["text"] == "Value B"

def test_match_field():
    # Advisory Bank is namespaced: EMD vs PBG
    # EMD Detail
    f_emd = match_field("Advisory Bank / सलाहकार बैंक", "EMD Detail")
    assert f_emd == "emd_advisory_bank"
    
    # ePBG Detail
    f_pbg = match_field("Advisory Bank", "ePBG Detail")
    assert f_pbg == "pbg_advisory_bank"

    # Bid Details/none section matches Bid End Date
    f_end = match_field("Bid End Date/Time / बोली समाप्ति दिनांक/समय", None)
    assert f_end == "bid_end_datetime"

    # Reverse Auction
    f_ra = match_field("Bid to RA enabled", None)
    assert f_ra == "reverse_auction_enabled"

def test_normalize_indian_currency():
    assert normalize_indian_currency("15 Lakh (s)") == "1500000"
    assert normalize_indian_currency("381 Lakh (s)") == "38100000"
    assert normalize_indian_currency("2.5 Crore") == "25000000"
    assert normalize_indian_currency("₹ 43,000") == "43000"
    assert normalize_indian_currency(" 50,000/- ") == "50000"

def test_validate_field():
    assert validate_field("emd_amount", "43000") is True
    assert validate_field("emd_amount", "43000.50") is True
    assert validate_field("emd_amount", "43,000") is False # must be post-normalization digits only
    assert validate_field("bid_end_datetime", "16-07-2026 13:00:00") is True
    assert validate_field("pbg_percentage", "5.00%") is True
    assert validate_field("pbg_percentage", "3") is True
    assert validate_field("bid_validity_days", "120 (Days)") is True
    assert validate_field("reverse_auction_enabled", "True") is True

def test_field_confidence():
    l_cell = {"blocks": [TextBlock(block_id="1", text="L", confidence=0.95, bounding_box={}, language_hint="")]}
    r_cell = {"blocks": [TextBlock(block_id="2", text="V", confidence=0.88, bounding_box={}, language_hint="")]}
    conf = field_confidence(l_cell, r_cell, 90)
    # round(0.88 * 0.9, 4) = 0.792
    assert conf == 0.792
