import uuid
import shutil
import logging
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from backend.app.schemas.tender_project import (
    TenderUploadResponse,
    TenderProcessRequest,
    TenderProcessResponse
)
from backend.app.repositories.job_store import create_job, get_job, update_job_parameters
from backend.app.core.constants import STORAGE_ROOT
from backend.app.services.storage import upload_file_to_minio, StorageError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tenders"])

def _validate_pdf(file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="A PDF file is required")
    if not file.filename.lower().endswith(".pdf") and file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

@router.post("/tenders/upload", status_code=201, response_model=TenderUploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
) -> TenderUploadResponse:
    """
    Unified PDF upload endpoint:
    Validates PDF, saves file to local disk and MinIO, creates SQLite job entry,
    and automatically enqueues background OCR / ingestion processing.
    Returns unified job_id, file_id, and tender_id.
    """
    _validate_pdf(file)
    
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
    job_id = str(uuid.uuid4())
    job_dir = STORAGE_ROOT / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Save file under original filename and original.pdf alias
    pdf_path = job_dir / file.filename
    original_alias_path = job_dir / "original.pdf"
    
    with open(pdf_path, "wb") as f:
        f.write(file_bytes)
        
    if pdf_path != original_alias_path:
        with open(original_alias_path, "wb") as f:
            f.write(file_bytes)
            
    # Try uploading to MinIO storage if available
    try:
        upload_file_to_minio(file_bytes, file.content_type or "application/pdf", file.filename)
    except StorageError as e:
        logger.warning(f"MinIO storage upload skipped/failed during tender upload: {e}")
        
    # Register job in SQLite store
    create_job(job_id=job_id, filename=file.filename, pdf_path=str(pdf_path))
    
    # Auto-enqueue background ingest pipeline if background_tasks is present
    if background_tasks:
        from backend.app.api.routes.tenders import _run_ingest_background
        background_tasks.add_task(
            _run_ingest_background, job_id, str(pdf_path), file.filename
        )
        
    logger.info(f"Unified tender upload successful: job_id={job_id}, filename={file.filename}")
    
    return TenderUploadResponse(
        job_id=job_id,
        file_id=job_id,
        tender_id=job_id,
        status="pending",
        original_filename=file.filename,
        message="Upload complete and background processing queued."
    )

@router.post("/tenders/process", response_model=TenderProcessResponse)
async def process_tender(
    payload: TenderProcessRequest,
    background_tasks: BackgroundTasks
) -> TenderProcessResponse:
    """
    Unified process trigger endpoint:
    Accepts job_id, file_id, or tender_id, retrieves job status, and triggers
    or reports processing pipeline state.
    """
    job_id = payload.resolved_job_id()
    if not job_id:
        raise HTTPException(
            status_code=400,
            detail="One of 'job_id', 'file_id', or 'tender_id' must be provided in payload"
        )
        
    job = get_job(job_id)
    job_dir = STORAGE_ROOT / "jobs" / job_id
    
    if not job and not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found")
        
    email = payload.resolved_email()
    if email and job:
        update_job_parameters(job_id, email, job_id)
        
    # Re-trigger background pipeline if job is pending or failed
    current_status = job.get("status", "pending") if job else "pending"
    pdf_path = job.get("pdf_path") if job else str(job_dir / "original.pdf")
    filename = job.get("original_filename") if job else "original.pdf"
    
    if current_status in ("pending", "failed") and Path(pdf_path).exists():
        from backend.app.api.routes.tenders import _run_ingest_background
        background_tasks.add_task(
            _run_ingest_background, job_id, pdf_path, filename
        )
        current_status = "processing"
        
    return TenderProcessResponse(
        job_id=job_id,
        file_id=job_id,
        tender_id=job_id,
        status=current_status,
        message=f"Tender processing state: '{current_status}'."
    )
