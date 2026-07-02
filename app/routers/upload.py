from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from app.db.job_store import create_job
from app.tasks.ocr_task import run_ocr_job
from shared.constants import STORAGE_ROOT
import uuid
import shutil
from pathlib import Path

router = APIRouter()

def _validate_pdf(file: UploadFile):
    if not file.filename.endswith(".pdf") or file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

@router.post("/upload", status_code=201)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    _validate_pdf(file)
    job_id = str(uuid.uuid4())
    job_dir = STORAGE_ROOT / "jobs" / job_id
    pdf_path = job_dir / "original.pdf"
    
    create_job(job_id=job_id, filename=file.filename, pdf_path=str(pdf_path))
    
    job_dir.mkdir(parents=True, exist_ok=True)
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
        
    background_tasks.add_task(run_ocr_job, job_id, pdf_path)
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Job created. Poll /job/{job_id}/status for updates."
    }
