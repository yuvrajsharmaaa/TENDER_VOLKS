from fastapi import APIRouter, HTTPException
from app.db.job_store import get_job
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
