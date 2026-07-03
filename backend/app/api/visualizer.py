import os
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from backend.app.core.constants import STORAGE_ROOT

router = APIRouter()

@router.get("/api/jobs")
async def list_jobs():
    jobs_dir = STORAGE_ROOT / "jobs"
    if not jobs_dir.exists():
        return []
        
    jobs = []
    for entry in jobs_dir.iterdir():
        if entry.is_dir():
            result_file = entry / "ocr_result.json"
            if result_file.exists():
                try:
                    with open(result_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    jobs.append({
                        "job_id": entry.name,
                        "original_filename": data.get("original_filename", "unknown"),
                        "status": data.get("status", "completed"),
                        "page_count": data.get("page_count", 0),
                        "total_processing_time_seconds": data.get("total_processing_time_seconds", 0),
                        "total_text_blocks": data.get("summary", {}).get("total_text_blocks", 0),
                        "total_layout_regions": data.get("summary", {}).get("total_layout_regions", 0)
                    })
                except Exception as e:
                    # Skip malformed JSON files
                    pass
    return jobs

@router.get("/visualizer")
@router.get("/")
async def get_visualizer():
    static_file = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "index.html"
    if not static_file.exists():
        raise HTTPException(status_code=404, detail="Visualizer UI file not found")
    return FileResponse(static_file)
