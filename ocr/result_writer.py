import json
from pathlib import Path
from backend.app.models.models import PageResult
from typing import List

def write_page_json(page_result: PageResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"page_{page_result.page_number:04d}.json"
    
    # Simple dataclass dict conversion for now
    data = {
        "job_id": page_result.job_id,
        "page_number": page_result.page_number,
        "image_path": page_result.image_path,
        "image_width_px": page_result.image_width_px,
        "image_height_px": page_result.image_height_px,
        "processing_time_seconds": page_result.processing_time_seconds,
        "text_blocks": [vars(tb) for tb in page_result.text_blocks],
        "layout_regions": [vars(lr) for lr in page_result.layout_regions],
        "warnings": page_result.warnings
    }
    
    if page_result.layoutlm_results is not None:
        data["layoutlm_results"] = page_result.layoutlm_results
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path

def write_aggregate_json(job_id: str, pages: List[PageResult], output_dir: Path, filename: str) -> Path:
    out_path = output_dir / "ocr_result.json"
    
    total_blocks = sum(len(p.text_blocks) for p in pages)
    total_regions = sum(len(p.layout_regions) for p in pages)
    processing_time = sum(p.processing_time_seconds for p in pages)
    
    data = {
        "job_id": job_id,
        "original_filename": filename,
        "status": "completed",
        "page_count": len(pages),
        "total_processing_time_seconds": processing_time,
        "pages": [
            {
                "page_number": p.page_number,
                "text_block_count": len(p.text_blocks),
                "layout_region_count": len(p.layout_regions),
                "layoutlm_results": p.layoutlm_results
            } for p in pages
        ],
        "summary": {
            "total_text_blocks": total_blocks,
            "total_layout_regions": total_regions
        }
    }
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path
