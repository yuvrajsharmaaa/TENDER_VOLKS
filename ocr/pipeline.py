from pathlib import Path
from ocr.pdf_converter import convert_pdf_to_images
from ocr.ocr_engine import OcrEngine
from ocr.layout_detector import LayoutDetector
from ocr.layoutlm_stage import LayoutLmStage
from ocr.result_writer import write_page_json, write_aggregate_json
from shared.models import PageResult
from PIL import Image
import time

def process_pdf(job_id: str, pdf_path: Path, run_layoutlm: bool = False) -> list[PageResult]:
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
        
    write_aggregate_json(job_id, page_results, job_dir, pdf_path.name)
    return page_results
