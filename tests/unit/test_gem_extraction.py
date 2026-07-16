import re
import pytest
from ocr.pipeline import is_gem_document
from ocr.extractors.gem_field_extractor import GemFieldExtractor
from backend.app.models.models import PageResult, TextBlock, LayoutRegion
from backend.app.schemas.schemas import ExtractedFieldSchema

def test_gem_document_type_detection():
    # GeM sample blocks
    gem_blocks = [
        TextBlock(block_id="1", text="धरोहर राशि/Earnest Money Deposit (EMD)", confidence=1.0, bounding_box={"x1": 10, "y1": 10, "x2": 100, "y2": 30}, language_hint="en"),
        TextBlock(block_id="2", text="बोली क्रमांक/Bid Number: GEM/2026/B/1234567", confidence=1.0, bounding_box={"x1": 110, "y1": 10, "x2": 400, "y2": 30}, language_hint="en")
    ]
    gem_page = PageResult(
        job_id="test", page_number=1, image_path="", image_width_px=1000, image_height_px=1000,
        processing_time_seconds=0.1, text_blocks=gem_blocks, layout_regions=[]
    )
    
    # Generic NIT sample blocks
    nit_blocks = [
        TextBlock(block_id="1", text="Notice Inviting Tender", confidence=1.0, bounding_box={"x1": 10, "y1": 10, "x2": 100, "y2": 30}, language_hint="en"),
        TextBlock(block_id="2", text="NIT No: 12345/PWD/2026", confidence=1.0, bounding_box={"x1": 110, "y1": 10, "x2": 400, "y2": 30}, language_hint="en")
    ]
    nit_page = PageResult(
        job_id="test", page_number=1, image_path="", image_width_px=1000, image_height_px=1000,
        processing_time_seconds=0.1, text_blocks=nit_blocks, layout_regions=[]
    )
    
    # Assert classification
    assert is_gem_document([gem_page]) is True
    assert is_gem_document([nit_page]) is False


def test_gem_extractor_emd_derivation():
    # Page with Schedule EMD amounts
    blocks = [
        # Schedule 1 EMD
        TextBlock(block_id="1", text="अनुसूची 1 ईएमडी राशि / Schedule 1 EMD Amount (In INR)", confidence=1.0, bounding_box={"x1": 100, "y1": 100, "x2": 600, "y2": 120}, language_hint="en"),
        TextBlock(block_id="2", text="43000", confidence=1.0, bounding_box={"x1": 800, "y1": 100, "x2": 900, "y2": 120}, language_hint="en"),
        # Schedule 2 EMD
        TextBlock(block_id="3", text="अनुसूची 2 ईएमडी राशि / Schedule 2 EMD Amount (In INR)", confidence=1.0, bounding_box={"x1": 100, "y1": 200, "x2": 600, "y2": 220}, language_hint="en"),
        TextBlock(block_id="4", text="7000", confidence=1.0, bounding_box={"x1": 800, "y1": 200, "x2": 900, "y2": 220}, language_hint="en")
    ]
    
    page = PageResult(
        job_id="test", page_number=1, image_path="", image_width_px=1600, image_height_px=1000,
        processing_time_seconds=0.1, text_blocks=blocks, layout_regions=[]
    )
    
    extractor = GemFieldExtractor()
    fields = extractor.extract_fields([page])
    field_map = {f.field_name: f for f in fields}
    
    # EMD list extraction
    assert "emd_by_schedule" in field_map
    assert field_map["emd_by_schedule"].value == {1: 43000.0, 2: 7000.0}
    assert field_map["emd_by_schedule"].source == "gem_parent_pdf"
    
    # EMD total derived sum
    assert "emd_total" in field_map
    assert field_map["emd_total"].value == 50000.0
    assert field_map["emd_total"].source == "derived"
    
    # EMD required derived flag
    assert "emd_required" in field_map
    assert field_map["emd_required"].value is True
    assert field_map["emd_required"].source == "derived"


def test_gem_extractor_schedules_specs_and_consignees():
    # Build text blocks representing a multi-schedule tender
    blocks = [
        # Schedule 1 Heading
        TextBlock(block_id="1", text="Schedule 1 / अनुसूची 1", confidence=1.0, bounding_box={"x1": 100, "y1": 50, "x2": 300, "y2": 70}, language_hint="en"),
        # Consignees header
        TextBlock(block_id="2", text="Consignee Reporting/Officer / परेषिती", confidence=1.0, bounding_box={"x1": 100, "y1": 100, "x2": 300, "y2": 120}, language_hint="en"),
        TextBlock(block_id="3", text="Address / पता", confidence=1.0, bounding_box={"x1": 310, "y1": 100, "x2": 500, "y2": 120}, language_hint="en"),
        TextBlock(block_id="4", text="Quantity / मात्रा", confidence=1.0, bounding_box={"x1": 510, "y1": 100, "x2": 600, "y2": 120}, language_hint="en"),
        TextBlock(block_id="5", text="Delivery Days / वितरण के दिन", confidence=1.0, bounding_box={"x1": 610, "y1": 100, "x2": 700, "y2": 120}, language_hint="en"),
        # Consignee Row 1 (Schedule 1)
        TextBlock(block_id="6", text="John Doe", confidence=1.0, bounding_box={"x1": 100, "y1": 140, "x2": 300, "y2": 160}, language_hint="en"),
        TextBlock(block_id="7", text="123 Road, Ranchi", confidence=1.0, bounding_box={"x1": 310, "y1": 140, "x2": 500, "y2": 160}, language_hint="en"),
        TextBlock(block_id="8", text="445", confidence=1.0, bounding_box={"x1": 510, "y1": 140, "x2": 600, "y2": 160}, language_hint="en"),
        TextBlock(block_id="9", text="90", confidence=1.0, bounding_box={"x1": 610, "y1": 140, "x2": 700, "y2": 160}, language_hint="en"),
        # Technical specifications for Schedule 1
        TextBlock(block_id="10", text="Nominal Battery Voltage", confidence=1.0, bounding_box={"x1": 100, "y1": 200, "x2": 400, "y2": 220}, language_hint="en"),
        TextBlock(block_id="11", text="2 V", confidence=1.0, bounding_box={"x1": 500, "y1": 200, "x2": 600, "y2": 220}, language_hint="en"),
        TextBlock(block_id="12", text="Battery Capacity at 10-h Rate [C 10]", confidence=1.0, bounding_box={"x1": 100, "y1": 230, "x2": 400, "y2": 250}, language_hint="en"),
        TextBlock(block_id="13", text="65 Ah", confidence=1.0, bounding_box={"x1": 500, "y1": 230, "x2": 600, "y2": 250}, language_hint="en"),
        
        # Schedule 2 Heading
        TextBlock(block_id="14", text="Schedule 2 / अनुसूची 2", confidence=1.0, bounding_box={"x1": 100, "y1": 300, "x2": 300, "y2": 320}, language_hint="en"),
        # Consignees row (Schedule 2)
        TextBlock(block_id="15", text="Jane Smith", confidence=1.0, bounding_box={"x1": 100, "y1": 340, "x2": 300, "y2": 360}, language_hint="en"),
        TextBlock(block_id="16", text="456 Street, Visakhapatnam", confidence=1.0, bounding_box={"x1": 310, "y1": 340, "x2": 500, "y2": 360}, language_hint="en"),
        TextBlock(block_id="17", text="100", confidence=1.0, bounding_box={"x1": 510, "y1": 340, "x2": 600, "y2": 360}, language_hint="en"),
        TextBlock(block_id="18", text="90", confidence=1.0, bounding_box={"x1": 610, "y1": 340, "x2": 700, "y2": 360}, language_hint="en"),
        # Technical specifications for Schedule 2
        TextBlock(block_id="19", text="Nominal Battery Voltage", confidence=1.0, bounding_box={"x1": 100, "y1": 400, "x2": 400, "y2": 420}, language_hint="en"),
        TextBlock(block_id="20", text="2 V", confidence=1.0, bounding_box={"x1": 500, "y1": 400, "x2": 600, "y2": 420}, language_hint="en"),
        TextBlock(block_id="21", text="Battery Capacity at 10-h Rate [C 10]", confidence=1.0, bounding_box={"x1": 100, "y1": 430, "x2": 400, "y2": 450}, language_hint="en"),
        TextBlock(block_id="22", text="100 Ah", confidence=1.0, bounding_box={"x1": 500, "y1": 430, "x2": 600, "y2": 450}, language_hint="en")
    ]
    
    page = PageResult(
        job_id="test", page_number=1, image_path="", image_width_px=1600, image_height_px=1000,
        processing_time_seconds=0.1, text_blocks=blocks, layout_regions=[]
    )
    
    extractor = GemFieldExtractor()
    fields = extractor.extract_fields([page])
    field_map = {f.field_name: f for f in fields}
    
    assert "schedules" in field_map
    schedules = field_map["schedules"].value
    assert len(schedules) == 2
    
    sch1 = next(s for s in schedules if s["schedule_number"] == 1)
    assert sch1["quantity"] == 445
    assert sch1["consignee_name"] == "John Doe"
    assert sch1["consignee_address"] == "123 Road, Ranchi"
    assert sch1["technical_specs"]["Nominal Battery Voltage"] == "2 V"
    assert sch1["technical_specs"]["Battery Capacity at 10-h Rate [C 10]"] == "65 Ah"
    
    sch2 = next(s for s in schedules if s["schedule_number"] == 2)
    assert sch2["quantity"] == 100
    assert sch2["consignee_name"] == "Jane Smith"
    assert sch2["consignee_address"] == "456 Street, Visakhapatnam"
    assert sch2["technical_specs"]["Nominal Battery Voltage"] == "2 V"
    assert sch2["technical_specs"]["Battery Capacity at 10-h Rate [C 10]"] == "100 Ah"


def test_gem_extractor_required_documents_checklist():
    blocks = [
        TextBlock(block_id="1", text="Document required from seller / बिक्रेता से आवश्यक दस्तावेज़", confidence=1.0, bounding_box={"x1": 100, "y1": 100, "x2": 600, "y2": 120}, language_hint="en"),
        TextBlock(block_id="2", text="Experience Criteria,Certificate (Requested in ATC),Additional Doc 1 (Requested in ATC),Compliance of BoQ specification and supporting document", confidence=1.0, bounding_box={"x1": 800, "y1": 100, "x2": 1500, "y2": 120}, language_hint="en")
    ]
    page = PageResult(
        job_id="test", page_number=1, image_path="", image_width_px=1600, image_height_px=1000,
        processing_time_seconds=0.1, text_blocks=blocks, layout_regions=[]
    )
    
    extractor = GemFieldExtractor()
    fields = extractor.extract_fields([page])
    field_map = {f.field_name: f for f in fields}
    
    assert "required_documents" in field_map
    checklist = field_map["required_documents"].value
    assert len(checklist) == 4
    
    assert checklist[0]["document_name"] == "Experience Criteria"
    assert checklist[0]["needs_stage2"] is False
    
    assert checklist[1]["document_name"] == "Certificate (Requested in ATC)"
    assert checklist[1]["needs_stage2"] is True
    
    assert checklist[2]["document_name"] == "Additional Doc 1 (Requested in ATC)"
    assert checklist[2]["needs_stage2"] is True
    
    assert checklist[3]["document_name"] == "Compliance of BoQ specification and supporting document"
    assert checklist[3]["needs_stage2"] is False


def test_gem_extractor_out_of_scope_stubs():
    # Empty page to trigger fallback extraction
    page = PageResult(
        job_id="test", page_number=1, image_path="", image_width_px=1600, image_height_px=1000,
        processing_time_seconds=0.1, text_blocks=[], layout_regions=[]
    )
    
    extractor = GemFieldExtractor()
    fields = extractor.extract_fields([page])
    field_map = {f.field_name: f for f in fields}
    
    # Verify out of scope fields are stubbed
    out_of_scope_fields = [
        "tender_value_gst_inclusive", "eligibility_criterion_years",
        "annual_avg_turnover_value", "working_capital_value",
        "net_worth_type_value", "solvency_certificate_value",
        "ld_applicable", "ld_percentage_per_week", "max_ld_percentage",
        "payment_terms_supply_percent", "payment_terms_installation_percent",
        "maf_required", "client_contact_person", "full_courier_address_with_pincode",
        "tender_fee_amount", "processing_fee_amount"
    ]
    
    for f_name in out_of_scope_fields:
        assert f_name in field_map
        field = field_map[f_name]
        assert field.value is None
        assert field.source == "not_available_stage1"
        assert field.likely_source is not None


def test_gem_real_pdf_integration_fallback():
    # Standard integration tests that attempt to parse a sample PDF if fitz is functional,
    # otherwise pass gracefully to guarantee clean local build testing.
    fitz_available = False
    try:
        import fitz
        fitz_available = True
    except Exception:
        pass
        
    if not fitz_available:
        pytest.skip("fitz (PyMuPDF) library DLL load is blocked by Windows App Control.")
        
    # Standard check if PyMuPDF works
    import os
    from pathlib import Path
    pdf_path = Path("sample_files/GeM-Bidding-7724454.pdf_1748685463_3605671.pdf")
    if not pdf_path.exists():
        pytest.skip("Sample PDF file does not exist.")
        
    try:
        from ocr.pipeline import process_pdf
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            temp_pdf = Path(td) / pdf_path.name
            with open(pdf_path, "rb") as sf, open(temp_pdf, "wb") as df:
                df.write(sf.read())
            pages = process_pdf("test-job", temp_pdf)
            assert len(pages) > 0
            assert is_gem_document(pages) is True
    except Exception as e:
        if "tesseract" in str(e).lower():
            pytest.skip(f"Tesseract not available: {e}")
        pytest.fail(f"GeM PDF processing failed: {e}")
