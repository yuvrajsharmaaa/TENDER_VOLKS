from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from pydantic import BaseModel
from backend.app.repositories.job_store import create_job, get_job, update_job_parameters
from backend.app.workers.ocr_task import run_automated_tender_pipeline
from backend.app.core.constants import STORAGE_ROOT
import uuid
import shutil

router = APIRouter()

class ProcessRequest(BaseModel):
    job_id: str
    email_recipient: str
    tender_id: int

def _validate_pdf(file: UploadFile):
    if not file.filename.endswith(".pdf") and file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

@router.post("/tenders/upload", status_code=201)
async def upload_pdf(file: UploadFile = File(...)):
    _validate_pdf(file)
    job_id = str(uuid.uuid4())
    job_dir = STORAGE_ROOT / "jobs" / job_id
    pdf_path = job_dir / "original.pdf"
    
    job_dir.mkdir(parents=True, exist_ok=True)
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
        
    create_job(job_id=job_id, filename=file.filename, pdf_path=str(pdf_path))
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Upload complete. Trigger processing via POST /tenders/process."
    }

@router.post("/tenders/process")
async def process_tender(
    payload: ProcessRequest,
    background_tasks: BackgroundTasks
):
    job = get_job(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    update_job_parameters(payload.job_id, payload.email_recipient, payload.tender_id)
    
    background_tasks.add_task(
        run_automated_tender_pipeline,
        payload.job_id,
        payload.tender_id,
        payload.email_recipient
    )
    
    return {
        "job_id": payload.job_id,
        "status": "processing"
    }
