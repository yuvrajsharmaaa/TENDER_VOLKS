from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from backend.app.repositories.job_store import get_job
from backend.app.core.constants import STORAGE_ROOT
from pathlib import Path
import json

router = APIRouter()

# ==============================================================================
# Simplified Automated API Routes (New Flow)
# ==============================================================================

@router.get("/jobs/{job_id}")
async def get_job_status_new(job_id: str):
    """
    Checks the status of an automated job task.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/jobs/{job_id}/download")
async def download_job_results_new(job_id: str, format: str = "summary"):
    """
    Downloads generated Layer 1 summary CSV or Layer 2 occurrences evidence CSV.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Job status is {job['status']}")
        
    job_dir = STORAGE_ROOT / "jobs" / job_id
    tender_id = job.get("tender_id", "unknown")
    
    if format == "evidence":
        filepath = job_dir / f"tender_{tender_id}_evidence.csv"
    else:
        filepath = job_dir / f"tender_{tender_id}_export.csv"
        
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Report file not found on disk")
        
    return FileResponse(filepath, media_type="text/csv", filename=filepath.name)

# ==============================================================================
# Legacy API Routes (Keep for Backward Compatibility)
# ==============================================================================

@router.get("/job/{job_id}/status")
async def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/job/{job_id}/result")
async def get_job_result(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job status is {job['status']}")
    
    result_path = job["result_path"]
    try:
        with open(result_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        return {
            "job_id": job_id,
            "status": "completed",
            "page_count": job["page_count"],
            "completed_at": job["completed_at"],
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to read result file")

@router.get("/job/{job_id}/raw-ocr")
async def get_job_raw_ocr(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job status is {job['status']}")
    
    file_path = Path(job["result_path"]).parent / "raw_ocr.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="raw_ocr.json not found")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read raw_ocr.json")

@router.get("/job/{job_id}/layout")
async def get_job_layout(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job status is {job['status']}")
    
    file_path = Path(job["result_path"]).parent / "layout.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="layout.json not found")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read layout.json")

@router.get("/job/{job_id}/extracted-fields")
async def get_job_extracted_fields(job_id: str):
    """
    Returns extracted_fields.json for a completed OCR run.

    Supports both the legacy v1 job flow (SQLite job_store, upload.py) and the
    v2 tender/document flow (backend/app/api/routes/tenders.py), since both
    ultimately write their OCR output to the same
    STORAGE_ROOT/jobs/<id>/extracted_fields.json path — for v1 the id is a
    job_id, for v2 it's a document_id. If the id isn't a known v1 job, fall
    back to reading the file directly under that id.
    """
    job = get_job(job_id)
    if job:
        if job["status"] != "completed":
            raise HTTPException(status_code=409, detail=f"Job status is {job['status']}")
        file_path = Path(job["result_path"]).parent / "extracted_fields.json"
    else:
        file_path = STORAGE_ROOT / "jobs" / job_id / "extracted_fields.json"

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="extracted_fields.json not found")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read extracted_fields.json")
