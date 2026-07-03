from fastapi import APIRouter, HTTPException
from backend.app.repositories.job_store import get_job
import json
from pathlib import Path

router = APIRouter()

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
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job status is {job['status']}")
    
    file_path = Path(job["result_path"]).parent / "extracted_fields.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="extracted_fields.json not found")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read extracted_fields.json")
