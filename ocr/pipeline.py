import time
from pathlib import Path
from PIL import Image

from ocr.pdf_converter import convert_pdf_to_images
from ocr.ocr_engine import OcrEngine
from ocr.layout.layout_detector import LayoutDetector
from ocr.layout.layoutlm_stage import LayoutLmStage
from ocr.extractors.field_extractor import FieldExtractor, is_contained
from ocr.result_writer import write_page_json, write_aggregate_json

from backend.app.models.models import PageResult
from backend.app.schemas.schemas import (
    RawOCRResponse, OCRBlockSchema, BoundingBox,
    LayoutResponse, LayoutRegionSchema,
    ExtractedFieldsResponse, ProductItemSchema
)

def process_pdf(job_id: str, pdf_path: Path, run_layoutlm: bool = False) -> list[PageResult]:
    start_pipeline_time = time.time()
    job_dir = pdf_path.parent
    pages_dir = job_dir / "pages"
    
    # 1. Convert PDF to images
    image_paths = convert_pdf_to_images(pdf_path, pages_dir)
    
    # 2. Init models (lazy loading can be improved)
    ocr = OcrEngine()
    layout = LayoutDetector()
    layoutlm = LayoutLmStage() if run_layoutlm else None
    
    page_results = []
    
    # 3. Process each page
    for i, img_path in enumerate(image_paths):
        start_time = time.time()
        
        text_blocks = ocr.run(img_path)
        layout_regions = layout.detect(img_path)
        
        # Spatial containment and reading order mapping
        for idx, region in enumerate(layout_regions):
            region.reading_order_index = idx + 1
            # Find contained text blocks
            contained_blocks = [tb for tb in text_blocks if is_contained(tb.bounding_box, region.bounding_box)]
            # Sort contained blocks in reading order (y1, then x1)
            sorted_contained = sorted(contained_blocks, key=lambda b: (b.bounding_box["y1"], b.bounding_box["x1"]))
            
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
                # Log error but don't crash the pipeline, save error under warnings
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
    
    # 4. Deterministic Field Extraction + Product/Item extraction
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
    
    # extracted_fields.json
    extracted_fields_resp = ExtractedFieldsResponse(
        job_id=job_id,
        original_filename=pdf_path.name,
        page_count=len(page_results),
        extracted_fields=extracted_fields,
        extracted_products=[
            ProductItemSchema(**p) for p in extracted_products
        ]
    )

    # Save files to disk
    with open(job_dir / "raw_ocr.json", "w", encoding="utf-8") as f:
        f.write(raw_ocr_resp.model_dump_json(indent=2))

    with open(job_dir / "layout.json", "w", encoding="utf-8") as f:
        f.write(layout_resp.model_dump_json(indent=2))

    with open(job_dir / "extracted_fields.json", "w", encoding="utf-8") as f:
        f.write(extracted_fields_resp.model_dump_json(indent=2))

    return page_results
