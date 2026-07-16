from PIL.Image import logger
import time
from pathlib import Path
from PIL import Image

from ocr.pdf_converter import convert_pdf_to_images
from ocr.ocr_engine import OcrEngine
from ocr.layout.layout_detector import LayoutDetector
from ocr.layout.layoutlm_stage import LayoutLmStage
from ocr.extractors.field_extractor import FieldExtractor, is_contained
from ocr.result_writer import write_page_json, write_aggregate_json
import re
from ocr.extractors.gem_field_extractor import GemFieldExtractor

from backend.app.models.models import PageResult, TextBlock, LayoutRegion
from backend.app.schemas.schemas import (
    RawOCRResponse, OCRBlockSchema, BoundingBox,
    LayoutResponse, LayoutRegionSchema,
    ExtractedFieldsResponse, ProductItemSchema
)

def sort_blocks_by_reading_order(blocks: list[TextBlock], y_tolerance: int = 12) -> list[TextBlock]:
    """
    Groups text blocks into lines based on vertical overlap/proximity,
    then sorts columns from left-to-right (x1) within each line.
    This preserves the reading order in tables and multi-column layouts.
    """
    if not blocks:
        return []
    
    # Sort blocks primarily by top-y coordinate
    sorted_by_y = sorted(blocks, key=lambda b: b.bounding_box["y1"])
    
    lines = []
    current_line = [sorted_by_y[0]]
    
    for block in sorted_by_y[1:]:
        avg_y1 = sum(b.bounding_box["y1"] for b in current_line) / len(current_line)
        if abs(block.bounding_box["y1"] - avg_y1) <= y_tolerance:
            current_line.append(block)
        else:
            lines.append(sorted(current_line, key=lambda b: b.bounding_box["x1"]))
            current_line = [block]
    lines.append(sorted(current_line, key=lambda b: b.bounding_box["x1"]))
    
    flattened = []
    for line in lines:
        flattened.extend(line)
    return flattened

def classify_document_type(page1: str | list[TextBlock]) -> str:
    if isinstance(page1, str):
        full_text = page1
    else:
        full_text = " ".join(b.text for b in page1)
    if re.search(r'GEM/20\d{2}/[A-Z]/\d+', full_text, re.IGNORECASE) or "Bid Document" in full_text:
        return "gem_structured"
    return "generic_nit"

def serialize_page_result_to_xml(pr: PageResult) -> str:
    """
    Serializes a PageResult into structured XML showing layout tags,
    bounding boxes, confidence scores, and reading-order text.
    """
    lines = [f'<page number="{pr.page_number}" width="{pr.image_width_px}" height="{pr.image_height_px}">']
    
    # Sort layout regions by vertical position (reading order)
    sorted_regions = sorted(pr.layout_regions, key=lambda r: (r.bounding_box["y1"], r.bounding_box["x1"]))
    
    for r in sorted_regions:
        bbox_str = f"{r.bounding_box['x1']},{r.bounding_box['y1']},{r.bounding_box['x2']},{r.bounding_box['y2']}"
        conf = f"{r.confidence:.2f}" if r.confidence is not None else "1.00"
        tag = r.region_type.lower()  # 'table' or 'paragraph'
        
        lines.append(f'  <{tag} bbox="[{bbox_str}]" confidence="{conf}">')
        
        content = r.text_content or ""
        for line in content.split("\n"):
            if line.strip():
                lines.append(f"    {line.strip()}")
                
        lines.append(f"  </{tag}>")
        
    lines.append("</page>")
    return "\n".join(lines)

def is_gem_document(page_results: list[PageResult]) -> bool:
    if not page_results:
        return False
    for block in page_results[0].text_blocks:
        text = block.text.lower()
        if "bid document" in text or "bid details" in text or "government e-marketplace" in text:
            return True
        if re.search(r'gem/20\d{2}/[a-z]/\d+', text):
            return True
    return False

def process_pdf(job_id: str, pdf_path: Path, run_layoutlm: bool = False) -> list[PageResult]:
    start_pipeline_time = time.time()
    job_dir = pdf_path.parent
    pages_dir = job_dir / "pages"
    
    # 1. Convert PDF to images
    image_paths = convert_pdf_to_images(pdf_path, pages_dir)
    
    # 2. Init models
    ocr = OcrEngine()
    layout = LayoutDetector()
    layoutlm = LayoutLmStage() if run_layoutlm else None
    
    page_results = []
    
    # 3. Process each page
    for i, img_path in enumerate(image_paths):
        start_time = time.time()
        
        # Apply unified image preprocessing for OCR
        from backend.app.services.pdf_text_extractor import preprocess_image_for_ocr
        preprocessed_path = preprocess_image_for_ocr(img_path)
        
        text_blocks = ocr.run(preprocessed_path)
        layout_regions = layout.detect(preprocessed_path)
        
        # Clean up temp preprocessed file
        if preprocessed_path != img_path:
            try:
                preprocessed_path.unlink()
            except Exception:
                pass
        
        # Spatial containment and reading order mapping
        for idx, region in enumerate(layout_regions):
            region.reading_order_index = idx + 1
            # Find contained text blocks
            contained_blocks = [tb for tb in text_blocks if is_contained(tb.bounding_box, region.bounding_box)]
            # Sort contained blocks in layout-aware reading order
            sorted_contained = sort_blocks_by_reading_order(contained_blocks)
            
            region.contained_block_ids = [b.block_id for b in sorted_contained]
            region.text_content = "\n".join([b.text for b in sorted_contained])
        
        # Get actual image dimensions
        with Image.open(img_path) as img:
            width, height = img.size
            
        # Run LayoutLM stage if enabled
        layoutlm_results = None
        if run_layoutlm and layoutlm:
            try:
                layoutlm_results = layoutlm.run(text_blocks, width, height)
            except Exception as e:
                import traceback
                traceback.print_exc()
                layoutlm_results = {
                    "layoutlm_inputs_preview": {"words": [], "boxes": []},
                    "entities": [],
                    "error": f"LayoutLM inference failed: {str(e)}"
                }
        
        pr = PageResult(
            job_id=job_id,
            page_number=i+1,
            image_path=str(img_path),
            image_width_px=width,
            image_height_px=height,
            processing_time_seconds=time.time() - start_time,
            text_blocks=text_blocks,
            layout_regions=layout_regions,
            layoutlm_results=layoutlm_results
        )
        page_results.append(pr)
        write_page_json(pr, pages_dir)
        
    # Write aggregate json for existing visualizer compatibility
    write_aggregate_json(job_id, page_results, job_dir, pdf_path.name)
    
    # Generate structured layout-aware XML file for downstream LLM extraction
    llm_xml_lines = []
    for pr in page_results:
        llm_xml_lines.append(serialize_page_result_to_xml(pr))
        
    with open(job_dir / "llm_layout_text.txt", "w", encoding="utf-8") as f:
        f.write("\n\n".join(llm_xml_lines))

    
    # 4. Deterministic Field Extraction + Product/Item extraction
    page1_blocks = page_results[0].text_blocks if page_results else []
    doc_type = classify_document_type(page1_blocks)
    
    import json
    logger.info(json.dumps({
        "event": "doc_type_classified",
        "job_id": job_id,
        "type": doc_type
    }))
    
    is_gem = (doc_type == "gem_structured")
    if is_gem:
        extractor = GemFieldExtractor()
    else:
        extractor = FieldExtractor()
        
    extracted_fields = extractor.extract_fields(page_results)
    extracted_products = extractor.extract_products(page_results)

    # 5. Build and serialize Pydantic response models
    # raw_ocr.json
    raw_ocr_pages = {}
    for pr in page_results:
        raw_ocr_pages[str(pr.page_number)] = [
            OCRBlockSchema(
                block_id=tb.block_id,
                text=tb.text,
                confidence=tb.confidence,
                bounding_box=BoundingBox(**tb.bounding_box),
                page_number=pr.page_number
            ) for tb in pr.text_blocks
        ]
    raw_ocr_resp = RawOCRResponse(
        job_id=job_id,
        original_filename=pdf_path.name,
        page_count=len(page_results),
        processing_time_seconds=time.time() - start_pipeline_time,
        pages=raw_ocr_pages
    )
    
    # layout.json
    layout_pages = {}
    for pr in page_results:
        layout_pages[str(pr.page_number)] = [
            LayoutRegionSchema(
                region_id=lr.region_id,
                region_type=lr.region_type,
                bounding_box=BoundingBox(**lr.bounding_box),
                page_number=pr.page_number,
                contained_block_ids=lr.contained_block_ids,
                reading_order_index=lr.reading_order_index,
                text_content=lr.text_content,
                confidence=lr.confidence,
                table_structure=lr.table_structure
            ) for lr in pr.layout_regions
        ]
    layout_resp = LayoutResponse(
        job_id=job_id,
        original_filename=pdf_path.name,
        page_count=len(page_results),
        processing_time_seconds=time.time() - start_pipeline_time,
        pages=layout_pages
    )
    
    needs_stage2 = False
    if is_gem:
        for f in extracted_fields:
            if f.field_name == "required_documents" and isinstance(f.value, list):
                needs_stage2 = any(item.get("needs_stage2") for item in f.value if isinstance(item, dict))

    # extracted_fields.json
    extracted_fields_resp = ExtractedFieldsResponse(
        job_id=job_id,
        original_filename=pdf_path.name,
        page_count=len(page_results),
        extracted_fields=extracted_fields,
        extracted_products=[
            ProductItemSchema(**p) for p in extracted_products
        ],
        needs_stage2_atc_parse=needs_stage2,
        document_type=doc_type
    )

    # Save files to disk
    with open(job_dir / "raw_ocr.json", "w", encoding="utf-8") as f:
        f.write(raw_ocr_resp.model_dump_json(indent=2))

    with open(job_dir / "layout.json", "w", encoding="utf-8") as f:
        f.write(layout_resp.model_dump_json(indent=2))

    with open(job_dir / "extracted_fields.json", "w", encoding="utf-8") as f:
        f.write(extracted_fields_resp.model_dump_json(indent=2))

    return page_results
