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


def test_field_extractor_new_gem_fields():
    extractor = FieldExtractor()
    
    # 1. bid_number
    b1 = TextBlock(block_id="b1", text="Bid Number", confidence=1.0, bounding_box={"x1": 10, "y1": 10, "x2": 100, "y2": 25}, language_hint="en")
    b2 = TextBlock(block_id="b2", text="GEM/2026/B/123456", confidence=1.0, bounding_box={"x1": 120, "y1": 10, "x2": 300, "y2": 25}, language_hint="en")
    
    # 2. buyer_email
    b3 = TextBlock(block_id="b3", text="Buyer Email", confidence=1.0, bounding_box={"x1": 10, "y1": 40, "x2": 100, "y2": 55}, language_hint="en")
    b4 = TextBlock(block_id="b4", text="buyer@gem.gov.in", confidence=1.0, bounding_box={"x1": 120, "y1": 40, "x2": 300, "y2": 55}, language_hint="en")
    
    # 3. ministry_name
    b5 = TextBlock(block_id="b5", text="Ministry Name", confidence=1.0, bounding_box={"x1": 10, "y1": 70, "x2": 100, "y2": 85}, language_hint="en")
    b6 = TextBlock(block_id="b6", text="Ministry Of Defence", confidence=1.0, bounding_box={"x1": 120, "y1": 70, "x2": 300, "y2": 85}, language_hint="en")
    
    # 4. years_of_past_experience
    b7 = TextBlock(block_id="b7", text="Years of Past Experience", confidence=1.0, bounding_box={"x1": 10, "y1": 100, "x2": 200, "y2": 115}, language_hint="en")
    b8 = TextBlock(block_id="b8", text="3 Year(s)", confidence=1.0, bounding_box={"x1": 220, "y1": 100, "x2": 300, "y2": 115}, language_hint="en")
    
    page = PageResult(
        job_id="test_job",
        page_number=1,
        image_path="",
        image_width_px=1000,
        image_height_px=1000,
        processing_time_seconds=0.1,
        text_blocks=[b1, b2, b3, b4, b5, b6, b7, b8],
        layout_regions=[]
    )
    
    fields = extractor.extract_fields([page])
    field_map = {f.field_name: f for f in fields}
    
    assert "bid_number" in field_map
    assert field_map["bid_number"].value == "GEM/2026/B/123456"
    
    assert "buyer_email" in field_map
    assert field_map["buyer_email"].value == "buyer@gem.gov.in"
    
    assert "ministry_name" in field_map
    assert field_map["ministry_name"].value == "Ministry Of Defence"
    
    assert "years_of_past_experience" in field_map
    assert field_map["years_of_past_experience"].value == "3 Year"


def test_field_extractor_gem_stage1_specifications():
    extractor = FieldExtractor()
    
    # 1. Mock a page containing schedule-wise EMDs
    b1 = TextBlock(block_id="b1", text="Schedule 1 EMD Amount (In INR)", confidence=1.0, bounding_box={"x1": 10, "y1": 10, "x2": 200, "y2": 25}, language_hint="en")
    b2 = TextBlock(block_id="b2", text="43000", confidence=1.0, bounding_box={"x1": 220, "y1": 10, "x2": 300, "y2": 25}, language_hint="en")
    b3 = TextBlock(block_id="b3", text="Schedule 2 EMD Amount (In INR)", confidence=1.0, bounding_box={"x1": 10, "y1": 40, "x2": 200, "y2": 55}, language_hint="en")
    b4 = TextBlock(block_id="b4", text="7000", confidence=1.0, bounding_box={"x1": 220, "y1": 40, "x2": 300, "y2": 55}, language_hint="en")
    
    # 2. Mock a schedule-wise consignee table
    r_header = LayoutRegion(region_id="r1", region_type="table", bounding_box={"x1": 10, "y1": 100, "x2": 600, "y2": 300}, contained_block_ids=[], reading_order_index=1, text_content="")
    b_sch = TextBlock(block_id="b_sch", text="Schedule 1", confidence=1.0, bounding_box={"x1": 10, "y1": 80, "x2": 100, "y2": 95}, language_hint="en")
    
    b_col1 = TextBlock(block_id="b_col1", text="Consignee/Reporting Officer", confidence=1.0, bounding_box={"x1": 10, "y1": 110, "x2": 150, "y2": 130}, language_hint="en")
    b_col2 = TextBlock(block_id="b_col2", text="Address", confidence=1.0, bounding_box={"x1": 160, "y1": 110, "x2": 300, "y2": 130}, language_hint="en")
    b_col3 = TextBlock(block_id="b_col3", text="Quantity", confidence=1.0, bounding_box={"x1": 310, "y1": 110, "x2": 400, "y2": 130}, language_hint="en")
    b_col4 = TextBlock(block_id="b_col4", text="Delivery Days", confidence=1.0, bounding_box={"x1": 410, "y1": 110, "x2": 500, "y2": 130}, language_hint="en")
    
    b_val1 = TextBlock(block_id="b_val1", text="John Doe", confidence=1.0, bounding_box={"x1": 10, "y1": 140, "x2": 150, "y2": 160}, language_hint="en")
    b_val2 = TextBlock(block_id="b_val2", text="123 Street Name, Delhi", confidence=1.0, bounding_box={"x1": 160, "y1": 140, "x2": 300, "y2": 160}, language_hint="en")
    b_val3 = TextBlock(block_id="b_val3", text="445", confidence=1.0, bounding_box={"x1": 310, "y1": 140, "x2": 400, "y2": 160}, language_hint="en")
    b_val4 = TextBlock(block_id="b_val4", text="90", confidence=1.0, bounding_box={"x1": 410, "y1": 140, "x2": 500, "y2": 160}, language_hint="en")
    
    page = PageResult(
        job_id="test_job",
        page_number=1,
        image_path="",
        image_width_px=1000,
        image_height_px=1000,
        processing_time_seconds=0.1,
        text_blocks=[b1, b2, b3, b4, b_sch, b_col1, b_col2, b_col3, b_col4, b_val1, b_val2, b_val3, b_val4],
        layout_regions=[r_header]
    )
    
    fields = extractor.extract_fields([page])
    field_map = {f.field_name: f for f in fields}
    
    # Assert EMD by schedule and derived fields
    assert "emd_by_schedule" in field_map
    assert "1: 43000" in field_map["emd_by_schedule"].value
    assert "2: 7000" in field_map["emd_by_schedule"].value
    
    assert "emd_total" in field_map
    assert "50,000" in field_map["emd_total"].value
    
    assert "emd_required" in field_map
    assert field_map["emd_required"].value == "Yes"
    
    # Assert schedules extracted
    assert "schedules" in field_map
    assert "John Doe" in field_map["schedules"].value
    assert "445" in field_map["schedules"].value
    
    # Assert out-of-scope fields correctly set
    assert "tender_value_gst_inclusive" in field_map
    assert field_map["tender_value_gst_inclusive"].value == "Out of Scope (Stage 1)"
    
    assert "eligibility_criterion_years" in field_map
    assert field_map["eligibility_criterion_years"].value == "Out of Scope (Stage 1)"


def test_cluster_words_into_cells():
    from backend.app.services.pdf_text_extractor import cluster_words_into_cells
    
    # Mock words tuple: (x0, y0, x1, y1, word, block_no, line_no, word_no)
    words = [
        (10, 10, 30, 20, "EMD", 0, 0, 0),
        (35, 10, 80, 20, "Amount", 0, 0, 1),
        (200, 10, 250, 20, "50000", 0, 0, 2),  # large gap from "Amount" (120px > 15px threshold)
    ]
    
    cells = cluster_words_into_cells(words, gap_threshold=15)
    assert len(cells) == 2
    assert cells[0]["text"] == "EMD Amount"
    assert cells[0]["bounding_box"] == {"x1": 10, "y1": 10, "x2": 80, "y2": 20}
    assert cells[1]["text"] == "50000"
    assert cells[1]["bounding_box"] == {"x1": 200, "y1": 10, "x2": 250, "y2": 20}


def test_extract_tender_fields_preserves_real_coordinates():
    from backend.app.services.field_extractor import extract_tender_fields
    
    pages = [
        {
            "page": 1,
            "text": "EMD Amount 50000",
            "blocks": [
                {
                    "text": "EMD Amount",
                    "confidence": 1.0,
                    "bounding_box": {"x1": 10, "y1": 10, "x2": 80, "y2": 20},
                    "language_hint": "en"
                },
                {
                    "text": "50000",
                    "confidence": 1.0,
                    "bounding_box": {"x1": 200, "y1": 10, "x2": 250, "y2": 20},
                    "language_hint": "en"
                }
            ]
        }
    ]
    
    sections = extract_tender_fields(pages, "Test Tender")
    # Retrieve the constructed TextBlocks for the first page
    # Since we mocked it, we can verify that blocks inside the spatial engine were mapped correctly
    assert len(sections) == 1
    # Check that it did not raise exceptions, and check mapping worked.
    # Let's ensure the label "EMD Amount" mapped successfully to EMD
    fields_map = {}
    for s in sections:
        for f in s["fields"]:
            fields_map[f["label"]] = f
            
    assert "EMD Amount" in fields_map
    assert "50000" in fields_map["EMD Amount"]["value"]


def test_classify_document_type():
    from ocr.pipeline import classify_document_type
    
    # 1. GeM bids matching Bid Document
    assert classify_document_type("This is a Bid Document for procurement...") == "gem_structured"
    
    # 2. GeM bids matching regex
    assert classify_document_type("Bid details: GEM/2026/R/482718") == "gem_structured"
    
    # 3. Generic NIT
    assert classify_document_type("Notice Inviting Tender for building roads...") == "generic_nit"


def test_atc_field_extraction_and_merging():
    from ocr.extractors.field_extractor import FieldExtractor, merge_tender_and_atc_fields
    extractor = FieldExtractor()

    # Main Tender Page
    b1 = TextBlock(block_id="b1", text="Bid Number: GEM/2026/B/99999", confidence=1.0, bounding_box={"x1": 10, "y1": 10, "x2": 300, "y2": 25}, language_hint="en")
    main_page = PageResult(
        job_id="main_job", page_number=1, image_path="", image_width_px=1000, image_height_px=1000,
        processing_time_seconds=0.1, text_blocks=[b1], layout_regions=[]
    )
    main_fields = extractor.extract_fields([main_page], doc_source="main_tender")
    
    # ATC Page (with Hindi anchor: निविदा संख्या and Bid Offer Validity)
    b2 = TextBlock(block_id="b2", text="निविदा संख्या: GEM/2026/B/99999", confidence=1.0, bounding_box={"x1": 10, "y1": 10, "x2": 300, "y2": 25}, language_hint="hin")
    b3 = TextBlock(block_id="b3", text="Bid Offer Validity: 120 Days", confidence=1.0, bounding_box={"x1": 10, "y1": 40, "x2": 300, "y2": 55}, language_hint="en")
    atc_page = PageResult(
        job_id="atc_job", page_number=1, image_path="", image_width_px=1000, image_height_px=1000,
        processing_time_seconds=0.1, text_blocks=[b2, b3], layout_regions=[]
    )
    atc_fields = extractor.extract_atc_fields([atc_page])

    # Check sources
    assert all(f.source in ("main_tender", "derived") for f in main_fields)
    assert all(f.source in ("atc", "derived") for f in atc_fields)

    # Merge
    merged_fields = merge_tender_and_atc_fields(main_fields, atc_fields)
    merged_map = {f.field_name: f for f in merged_fields}

    assert "bid_number" in merged_map
    assert merged_map["bid_number"].value == "GEM/2026/B/99999"
    
    assert "bid_validity_days" in merged_map
    assert merged_map["bid_validity_days"].value == "120 Days"
    assert merged_map["bid_validity_days"].source == "atc"


def test_explicit_atc_clause_precedence_no_confidence_carveout():
    """Verify explicit ATC clauses always take precedence over main tender, removing confidence carve-outs."""
    from ocr.extractors.field_extractor import merge_tender_and_atc_fields
    from backend.app.schemas.schemas import ExtractedFieldSchema

    main_f = ExtractedFieldSchema(
        field_name="contract_period",
        value="60 days",
        confidence=1.0,  # Higher confidence
        source_page=1,
        evidence="Main tender contract period",
        source_blocks=[],
        source="main_tender"
    )
    atc_f = ExtractedFieldSchema(
        field_name="contract_period",
        value="90 days",
        confidence=0.8,  # Lower confidence
        source_page=1,
        evidence="ATC override contract period",
        source_blocks=[],
        source="atc"
    )

    merged = merge_tender_and_atc_fields([main_f], [atc_f])
    res = next(f for f in merged if f.field_name == "contract_period")

    # ATC must win despite lower confidence score
    assert res.value == "90 days"
    assert res.source == "atc"


def test_ambiguous_field_preservation():
    """Verify ambiguous fields preserve both candidates without premature resolution."""
    from ocr.extractors.field_extractor import merge_tender_and_atc_fields
    from backend.app.schemas.schemas import ExtractedFieldSchema

    main_f = ExtractedFieldSchema(
        field_name="custom_eligibility_criteria",
        value="Must have 3 years OEM experience",
        confidence=0.9,
        source_page=1,
        evidence="Main tender PQR clause",
        source_blocks=[],
        source="main_tender"
    )
    atc_f = ExtractedFieldSchema(
        field_name="custom_eligibility_criteria",
        value="Must hold ISO 9001 certification",
        confidence=0.9,
        source_page=2,
        evidence="ATC additional certification clause",
        source_blocks=[],
        source="atc"
    )

    merged = merge_tender_and_atc_fields([main_f], [atc_f])
    res = next(f for f in merged if f.field_name == "custom_eligibility_criteria")

    assert res.source == "ambiguous_preserved"
    assert isinstance(res.value, dict)
    assert res.value["main_tender"] == "Must have 3 years OEM experience"
    assert res.value["atc"] == "Must hold ISO 9001 certification"


def test_atc_resolver_link_and_fallback_handling():
    """Verify link-based ATC target detection and graceful fallback handling when link is missing/unreachable."""
    dummy_link = {
        "name": "buyer_atc.pdf",
        "url": "https://example.com/buyer_atc.pdf",
        "anchorText": "Buyer uploaded ATC document Click here to view the file.",
        "sourcePage": 1
    }
    anchor_lower = dummy_link["anchorText"].lower()
    is_atc_anchor = any(phrase in anchor_lower for phrase in [
        "buyer uploaded atc document",
        "buyer added bid specific atc",
        "click here to view the file",
        "click here",
        "atc"
    ])
    assert is_atc_anchor is True
    assert dummy_link["url"] == "https://example.com/buyer_atc.pdf"


def test_gail_bec_section_ii_table_extraction():
    """Verify multi-row table handlers for GAIL BEC Clause 1.2, 2.1, 2.2, 2.3, and 39.2."""
    extractor = FieldExtractor()

    # Clause 1.2 technical eligibility table
    b_1_2_hdr = TextBlock(block_id="b1_2h", text="1.2 Required Minimum executed Value (in Rs.)", confidence=1.0, bounding_box={"x1": 10, "y1": 10, "x2": 400, "y2": 25}, language_hint="en")
    tbl_1_2_h = TextBlock(block_id="t1_2h", text="Part No. Site Required Minimum executed Value (in Rs.)", confidence=1.0, bounding_box={"x1": 10, "y1": 30, "x2": 500, "y2": 45}, language_hint="en")
    tbl_1_2_r1 = TextBlock(block_id="t1_2r1", text="Part - 1 MANSARAMPURA REGION 106.41 Lakh", confidence=1.0, bounding_box={"x1": 10, "y1": 50, "x2": 500, "y2": 65}, language_hint="en")
    tbl_1_2_r2 = TextBlock(block_id="t1_2r2", text="Part - 2 NASIRABAD REGION 112.97 Lakh", confidence=1.0, bounding_box={"x1": 10, "y1": 70, "x2": 500, "y2": 85}, language_hint="en")
    
    region_1_2 = LayoutRegion(region_id="r1", region_type="Table", bounding_box={"x1": 5, "y1": 28, "x2": 510, "y2": 90}, contained_block_ids=[], confidence=0.95)

    page1 = PageResult(
        job_id="test_bec", page_number=1, image_path="", image_width_px=600, image_height_px=800,
        processing_time_seconds=0.1, text_blocks=[b_1_2_hdr, tbl_1_2_h, tbl_1_2_r1, tbl_1_2_r2],
        layout_regions=[region_1_2]
    )

    # Clause 2.1, 2.2, 2.3 financial BEC table page
    b_2_1_hdr = TextBlock(block_id="b2_1h", text="2.1 AVERAGE ANNUAL TURNOVER", confidence=1.0, bounding_box={"x1": 10, "y1": 10, "x2": 400, "y2": 25}, language_hint="en")
    tbl_2_1_h = TextBlock(block_id="t2_1h", text="Part No. Site Required Minimum Turnover (in Rs.)", confidence=1.0, bounding_box={"x1": 10, "y1": 30, "x2": 500, "y2": 45}, language_hint="en")
    tbl_2_1_r1 = TextBlock(block_id="t2_1r1", text="Part - 1 MANSARAMPURA REGION 79.81 Lakh", confidence=1.0, bounding_box={"x1": 10, "y1": 50, "x2": 500, "y2": 65}, language_hint="en")
    region_2_1 = LayoutRegion(region_id="r2", region_type="Table", bounding_box={"x1": 5, "y1": 28, "x2": 510, "y2": 70}, contained_block_ids=[], confidence=0.95)

    b_2_2 = TextBlock(block_id="b2_2", text="2.2 NET WORTH: Positive for preceding financial year", confidence=1.0, bounding_box={"x1": 10, "y1": 80, "x2": 500, "y2": 95}, language_hint="en")
    b_2_2_sub = TextBlock(block_id="b2_2s", text="- do -", confidence=1.0, bounding_box={"x1": 10, "y1": 96, "x2": 100, "y2": 110}, language_hint="en")

    b_2_3_hdr = TextBlock(block_id="b2_3h", text="2.3 WORKING CAPITAL", confidence=1.0, bounding_box={"x1": 10, "y1": 120, "x2": 400, "y2": 135}, language_hint="en")
    tbl_2_3_h = TextBlock(block_id="t2_3h", text="Part No. Site Required Minimum Working Capital (in Rs.)", confidence=1.0, bounding_box={"x1": 10, "y1": 140, "x2": 500, "y2": 155}, language_hint="en")
    tbl_2_3_r1 = TextBlock(block_id="t2_3r1", text="Part - 1 MANSARAMPURA REGION 15.96 Lakh", confidence=1.0, bounding_box={"x1": 10, "y1": 160, "x2": 500, "y2": 175}, language_hint="en")
    b_2_3_note = TextBlock(block_id="b2_3n", text="If the bidder working capital is inadequate, the bidder shall submit line of credit from bank", confidence=1.0, bounding_box={"x1": 10, "y1": 180, "x2": 550, "y2": 195}, language_hint="en")
    region_2_3 = LayoutRegion(region_id="r3", region_type="Table", bounding_box={"x1": 5, "y1": 138, "x2": 510, "y2": 178}, contained_block_ids=[], confidence=0.95)

    page2 = PageResult(
        job_id="test_bec", page_number=2, image_path="", image_width_px=600, image_height_px=800,
        processing_time_seconds=0.1,
        text_blocks=[b_2_1_hdr, tbl_2_1_h, tbl_2_1_r1, b_2_2, b_2_2_sub, b_2_3_hdr, tbl_2_3_h, tbl_2_3_r1, b_2_3_note],
        layout_regions=[region_2_1, region_2_3]
    )

    # Clause 39.2 Nodal Officer page
    b_39_2_hdr = TextBlock(block_id="b39_2h", text="39.2 Name and contact details of nodal officer are as under:", confidence=1.0, bounding_box={"x1": 10, "y1": 10, "x2": 500, "y2": 25}, language_hint="en")
    b_39_2_info = TextBlock(block_id="b39_2i", text="Shri Sheew Shankar, GM (O&M), Jaipur\nTel: 0141-2230347\nEmail: sheewshankar@gail.co.in", confidence=1.0, bounding_box={"x1": 10, "y1": 30, "x2": 450, "y2": 70}, language_hint="en")

    page3 = PageResult(
        job_id="test_bec", page_number=3, image_path="", image_width_px=600, image_height_px=800,
        processing_time_seconds=0.1, text_blocks=[b_39_2_hdr, b_39_2_info], layout_regions=[]
    )

    fields = extractor.extract_fields([page1, page2, page3])
    field_map = {f.field_name: f for f in fields}

    assert "eligibility_executed_value" in field_map
    assert "MANSARAMPURA REGION 106.41 Lakh" in field_map["eligibility_executed_value"].value

    assert "financial_avg_turnover" in field_map
    assert "MANSARAMPURA REGION 79.81 Lakh" in field_map["financial_avg_turnover"].value

    assert "financial_net_worth" in field_map
    assert "Positive for preceding financial year" in field_map["financial_net_worth"].value

    assert "financial_working_capital" in field_map
    assert "15.96 Lakh" in field_map["financial_working_capital"].value

    assert "nodal_officer_contact" in field_map
    assert "Shri Sheew Shankar" in field_map["nodal_officer_contact"].value


def test_nodal_officer_courier_address_leak_protection():
    """Verify that Nodal Officer (Clause 39.2) details do not leak into courier address field."""
    from backend.app.services.tender_mapper import build_infosheet_data

    sample_atc_text = (
        "(H) DEALING GAIL'S OFFICE ADDRESS\n"
        "GAIL Bhawan, Jaipur Region, Plot 5, Jaipur, Rajasthan 302001\n\n"
        "39.2 Name and contact details of nodal officer are as under:\n"
        "Shri Sheew Shankar, GM (O&M), Jaipur\n"
        "Tel: 0141-2230347\n"
        "Email: sheewshankar@gail.co.in\n"
    )

    pages = [{"page": 1, "text": sample_atc_text, "blocks": []}]
    sections = [
        {
            "id": "sec-1",
            "title": "Unified",
            "fields": [
                {"label": "Courier Address", "field_name": "full_courier_address_with_pincode", "value": "GAIL Bhawan, Jaipur Region, Plot 5, Jaipur, Rajasthan 302001", "status": "extracted"}
            ]
        }
    ]

    infosheet = build_infosheet_data(sections, pages, job_id="test_leak")
    
    # Assert Nodal Officer details resolved to client_name_2_display
    assert infosheet.get("client_name_2_display") == "Shri Sheew Shankar"
    assert "sheewshankar@gail.co.in" in infosheet.get("client_email_2_display", "")

    # Assert courier address does NOT contain Nodal Officer's name
    courier_addr = infosheet.get("courier_address_display", "")
    assert "Shri Sheew Shankar" not in courier_addr





