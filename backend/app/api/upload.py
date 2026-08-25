import uuid
import shutil
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from backend.app.schemas.tender_project import (
    TenderUploadResponse,
    TenderProcessRequest,
    TenderProcessResponse
)
from backend.app.repositories.job_repository import (
    create_job,
    get_job,
    update_job_parameters,
    update_status
)
from backend.app.core.constants import STORAGE_ROOT, JobStatus
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
    background_tasks: BackgroundTasks = None  # type: ignore
) -> TenderUploadResponse:
    """
    Unified PDF upload endpoint:
    Validates PDF, saves file to local disk and MinIO, creates database job entry,
    and automatically enqueues Celery background OCR / ingestion processing.
    Returns unified job_id, file_id, and tender_id with status 'queued'.
    """
    logger.info(f"[STEP 1/5][UPLOAD] Received file upload request: filename='{file.filename}', content_type='{file.content_type}'")
    _validate_pdf(file)
    
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        logger.error("[UPLOAD] Uploaded file is 0 bytes")
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
    job_id = str(uuid.uuid4())
    job_dir = STORAGE_ROOT / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Save file under original filename and original.pdf alias
    filename_str = str(file.filename) if file.filename else "original.pdf"
    pdf_path = job_dir / filename_str
    original_alias_path = job_dir / "original.pdf"
    
    logger.info(f"[STEP 2/5][UPLOAD] Saving {len(file_bytes)} bytes to local disk: {pdf_path}")
    with open(pdf_path, "wb") as f:
        f.write(file_bytes)
        
    if pdf_path != original_alias_path:
        with open(original_alias_path, "wb") as f:
            f.write(file_bytes)
            
    # Try uploading to MinIO storage if available
    try:
        logger.info(f"[STEP 3/5][UPLOAD] Uploading to MinIO storage bucket...")
        upload_file_to_minio(file_bytes, file.content_type or "application/pdf", filename_str)
    except StorageError as e:
        logger.warning(f"[UPLOAD] MinIO storage upload skipped/failed: {e}")
        
    # Register job in PostgreSQL store with 'queued' status
    logger.info(f"[STEP 4/5][UPLOAD] Registering job {job_id} in PostgreSQL job store with 'queued' status...")
    create_job(job_id=job_id, filename=filename_str, pdf_path=str(pdf_path), status=JobStatus.QUEUED)

    # Auto-enqueue background Celery task
    logger.info(f"[STEP 5/5][UPLOAD] Enqueueing Celery background extraction & LLM fallback task for job {job_id}...")
    from backend.app.api.routes.tenders import _run_ingest_background
    _run_ingest_background.delay(job_id, str(pdf_path), filename_str)
        
    logger.info(f"[UPLOAD_COMPLETE] Unified tender upload successful: job_id={job_id}, filename={file.filename}")
    
    return TenderUploadResponse(
        job_id=job_id,
        file_id=job_id,
        tender_id=job_id,
        status="queued",
        original_filename=filename_str,
        message="Upload complete and background processing queued."
    )

@router.post("/tenders/process", response_model=TenderProcessResponse)
async def process_tender(
    payload: TenderProcessRequest,
    background_tasks: BackgroundTasks = None  # type: ignore
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
        
    # Re-trigger background Celery pipeline if job is pending, queued or failed
    current_status = job.get("status", "pending") if job else "pending"
    pdf_path_str = str(job.get("pdf_path")) if job and job.get("pdf_path") else str(job_dir / "original.pdf")
    filename_str = str(job.get("original_filename")) if job and job.get("original_filename") else "original.pdf"
    
    if current_status in ("pending", "queued", "failed") and Path(pdf_path_str).exists():
        from backend.app.api.routes.tenders import _run_ingest_background
        update_status(job_id, JobStatus.QUEUED)
        _run_ingest_background.delay(job_id, pdf_path_str, filename_str)
        current_status = "queued"
        
    return TenderProcessResponse(
        job_id=job_id,
        file_id=job_id,
        tender_id=job_id,
        status=current_status,
        message=f"Tender processing state: '{current_status}'."
    )
