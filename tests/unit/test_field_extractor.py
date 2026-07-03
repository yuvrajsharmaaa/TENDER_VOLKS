import pytest
from ocr.extractors.field_extractor import FieldExtractor, group_blocks_into_rows, is_contained
from backend.app.models.models import PageResult, TextBlock, LayoutRegion

def test_is_contained():
    box_block = {"x1": 10, "y1": 10, "x2": 50, "y2": 30}
    box_region_in = {"x1": 0, "y1": 0, "x2": 100, "y2": 100}
    box_region_out = {"x1": 60, "y1": 60, "x2": 100, "y2": 100}
    
    assert is_contained(box_block, box_region_in) is True
    assert is_contained(box_block, box_region_out) is False

def test_group_blocks_into_rows():
    b1 = TextBlock(block_id="1", text="Col1", confidence=1.0, bounding_box={"x1": 10, "y1": 10, "x2": 30, "y2": 25}, language_hint="en")
    b2 = TextBlock(block_id="2", text="Col2", confidence=1.0, bounding_box={"x1": 50, "y1": 12, "x2": 80, "y2": 26}, language_hint="en")
    b3 = TextBlock(block_id="3", text="Col1Row2", confidence=1.0, bounding_box={"x1": 10, "y1": 40, "x2": 30, "y2": 55}, language_hint="en")
    
    rows = group_blocks_into_rows([b1, b2, b3])
    assert len(rows) == 2
    assert len(rows[0]) == 2
    assert len(rows[1]) == 1
    assert rows[0][0].block_id == "1"
    assert rows[0][1].block_id == "2"

def test_field_extractor_emd_and_fee():
    extractor = FieldExtractor()
    
    # Mock PageResult
    # 1. EMD
    b1 = TextBlock(block_id="b1", text="Earnest Money Deposit (EMD)", confidence=1.0, bounding_box={"x1": 10, "y1": 10, "x2": 200, "y2": 25}, language_hint="en")
    b2 = TextBlock(block_id="b2", text="Rs. 50,000/-", confidence=1.0, bounding_box={"x1": 220, "y1": 10, "x2": 300, "y2": 25}, language_hint="en")
    # 2. Tender Fee (Exempted)
    b3 = TextBlock(block_id="b3", text="Tender Fee", confidence=1.0, bounding_box={"x1": 10, "y1": 40, "x2": 100, "y2": 55}, language_hint="en")
    b4 = TextBlock(block_id="b4", text="Nil", confidence=1.0, bounding_box={"x1": 120, "y1": 40, "x2": 150, "y2": 55}, language_hint="en")
    # 3. NIT Number
    b5 = TextBlock(block_id="b5", text="NIT No: GEM/2025/B/6053925", confidence=1.0, bounding_box={"x1": 10, "y1": 70, "x2": 300, "y2": 85}, language_hint="en")
    
    page = PageResult(
        job_id="test_job",
        page_number=1,
        image_path="",
        image_width_px=1000,
        image_height_px=1000,
        processing_time_seconds=0.1,
        text_blocks=[b1, b2, b3, b4, b5],
        layout_regions=[]
    )
    
    fields = extractor.extract_fields([page])
    field_map = {f.field_name: f for f in fields}
    
    # EMD Assertion
    assert "EMD" in field_map
    assert "50,000" in field_map["EMD"].value
    assert field_map["EMD"].confidence > 0.5
    
    # Tender Fee Assertion
    assert "Tender Fee" in field_map
    assert field_map["Tender Fee"].value == "Nil / Exempted"
    
    # NIT No Assertion
    assert "NIT No" in field_map
    assert field_map["NIT No"].value == "GEM/2025/B/6053925"
    assert field_map["NIT No"].confidence >= 0.8
