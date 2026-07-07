import os
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from backend.app.core.constants import STORAGE_ROOT

router = APIRouter()

@router.get("/api/jobs")
async def list_jobs():
    from backend.app.repositories.job_store import get_all_jobs
    from backend.app.core.constants import PROJECT_ROOT
    db_jobs = get_all_jobs()
    
    jobs = []
    for job in db_jobs:
        result_path = job.get("result_path")
        page_count = job.get("page_count") or 0
        total_processing_time = 0.0
        total_text_blocks = 0
        total_layout_regions = 0
        
        if result_path:
            p = Path(result_path)
            if not p.exists() and "backend/app/" in result_path:
                relative_part = result_path.split("backend/app/", 1)[1]
                p = PROJECT_ROOT / relative_part
                
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    page_count = data.get("page_count", page_count)
                    total_processing_time = data.get("total_processing_time_seconds", 0.0)
                    total_text_blocks = data.get("summary", {}).get("total_text_blocks", 0)
                    total_layout_regions = data.get("summary", {}).get("total_layout_regions", 0)
                except Exception:
                    pass
                    
        jobs.append({
            "job_id": job["job_id"],
            "original_filename": job["original_filename"],
            "status": job["status"],
            "page_count": page_count,
            "total_processing_time_seconds": total_processing_time,
            "total_text_blocks": total_text_blocks,
            "total_layout_regions": total_layout_regions
        })
    return jobs


@router.get("/visualizer")
@router.get("/")
async def get_visualizer():
    static_file = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "index.html"
    if not static_file.exists():
        raise HTTPException(status_code=404, detail="Visualizer UI file not found")
    return FileResponse(static_file)
