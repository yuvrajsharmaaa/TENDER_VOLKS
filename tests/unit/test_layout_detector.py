import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from ocr.layout.layout_detector import LayoutDetector
from ocr.ocr_engine import OcrEngine

def test_layout_detector_table_heuristics():
    # Mock data representing a typical two-column table (Label, Value)
    # block_num, par_num, line_num, left, top, width, height, text
    mock_tesseract_data = {
        "text": ["EMD", "Amount", "Rs.", "10,000/-", "Tender", "Fee", "Nil", "", "Some", "general", "sentence", "paragraph."],
        "block_num": [1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2],
        "par_num": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        "line_num": [1, 1, 1, 1, 2, 2, 2, 2, 1, 1, 1, 1],
        # Coordinates: words on same line separated by a gap
        # Line 1: "EMD Amount" (left=10, width=50) vs "Rs. 10,000/-" (left=200, width=80)
        "left": [10, 45, 200, 230, 10, 50, 200, 220, 10, 40, 70, 120],
        "top": [10, 10, 10, 10, 30, 30, 30, 30, 100, 100, 100, 100],
        "width": [30, 30, 25, 45, 30, 20, 15, 10, 25, 25, 40, 50],
        "height": [12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12]
    }
    
    detector = LayoutDetector()
    OcrEngine._cache["dummy_path.png"] = mock_tesseract_data
    
    regions = detector.detect(Path("dummy_path.png"))
    
    # We should have 2 regions: block 1 par 1 (the table), block 2 par 1 (the paragraph)
    assert len(regions) == 2
    
    # Region 1 (block 1, par 1) has multi-column lines (Line 1: EMD Amount vs Rs 10000; Line 2: Tender Fee vs Nil)
    # It should be detected as a table
    assert regions[0].region_type == "table"
    
    # Region 2 (block 2, par 1) has a single line of consecutive text without large gaps
    # It should be detected as a paragraph
    assert regions[1].region_type == "paragraph"

def test_layout_detector_caching():
    detector = LayoutDetector()
    OcrEngine._cache.clear()
    
    mock_data = {
        "text": ["Hello", "World"],
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
        "left": [10, 50],
        "top": [10, 10],
        "width": [30, 30],
        "height": [12, 12]
    }
    
    OcrEngine._cache["cached_image.png"] = mock_data
    
    with patch("pytesseract.image_to_data") as mock_tess:
        regions = detector.detect(Path("cached_image.png"))
        # Should NOT call pytesseract.image_to_data because it is in cache
        mock_tess.assert_not_called()
        assert len(regions) == 1

def test_sort_blocks_by_reading_order():
    from ocr.pipeline import sort_blocks_by_reading_order
    from backend.app.models.models import TextBlock
    
    # 2 text blocks slightly vertically misaligned but forming a horizontal row
    # Block A: left=10, top=100 (label)
    # Block B: left=200, top=98 (value)
    # Strict Y-sorting would put Block B before Block A.
    # Vertical tolerance sorting should keep Block A before Block B (left to right).
    tb_a = TextBlock(block_id="A", text="Label:", confidence=1.0, bounding_box={"x1": 10, "y1": 100, "x2": 80, "y2": 115}, language_hint="en")
    tb_b = TextBlock(block_id="B", text="Value", confidence=1.0, bounding_box={"x1": 200, "y1": 98, "x2": 250, "y2": 113}, language_hint="en")
    
    sorted_blocks = sort_blocks_by_reading_order([tb_a, tb_b])
    
    assert sorted_blocks[0].block_id == "A"
    assert sorted_blocks[1].block_id == "B"

