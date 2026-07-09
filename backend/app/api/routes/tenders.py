import uuid
import logging
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Form, BackgroundTasks
from sqlalchemy.orm import Session

from backend.app.services.storage import upload_file_to_minio, download_file_from_minio, StorageError
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.db.session import get_db
from backend.app.models.tender_project import TenderProject
from backend.app.models.document import Document
from backend.app.models.tender_information import TenderInformation
from backend.app.services.mapping import map_extracted_fields_to_tender_info
from backend.app.services.export import export_tender_info_to_csv, CSV_COLUMNS
from backend.app.services.email_service import send_tender_csv_email
from backend.app.core.constants import STORAGE_ROOT
from backend.app.schemas.tender_project import (
    TenderProjectCreate,
    TenderProjectResponse,
    TenderProjectDetailResponse,
    DocumentResponse
)
from backend.app.core.minio import minio_client

logger = get_logger(__name__)

router = APIRouter(prefix="/tenders", tags=["tenders"])

# Max file size constant (20 MB)
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024

@router.post("/upload")
async def upload_tender(file: UploadFile = File(None)):
    """
    Day 3 endpoint: Validates an uploaded PDF file, saves it to MinIO storage,
    and returns its generated file ID and original filename.
    """
    # Step 1 — Validate file presence and content type
    if file is None or not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_file", "message": "A PDF file is required"}
        )
        
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_type",
                "message": "Only PDF files are accepted",
                "received": file.content_type
            }
        )
        
    # Step 2 — Read file bytes
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=400,
            detail={"error": "empty_file", "message": "Uploaded file is empty"}
        )
        
    logger.debug(
        "Read uploaded file bytes",
        extra={
            "custom_fields": {
                "original_filename": file.filename,
                "content_type": file.content_type,
                "size_bytes": len(file_bytes)
            }
        }
    )
    
    # Step 3 — Upload to MinIO
    try:
        file_id = upload_file_to_minio(file_bytes, file.content_type, file.filename)
    except StorageError as e:
        logger.error(
            f"Storage failure during upload of {file.filename}: {e}",
            exc_info=True,
            extra={
                "custom_fields": {
                    "original_filename": file.filename
                }
            }
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "storage_failure",
                "message": "Failed to store file. Please try again."
            }
        )
        
    # Step 5 — Log the successful upload (logged prior to response return)
    bucket_name = settings.MINIO_BUCKET
    logger.info(
        "tender_upload_success",
        extra={
            "custom_fields": {
                "event": "tender_upload_success",
                "file_id": file_id,
                "original_filename": file.filename,
                "size_bytes": len(file_bytes),
                "bucket": bucket_name
            }
        }
    )
    
    # Step 4 — Return success
    return {
        "file_id": file_id,
        "original_filename": file.filename
    }


@router.post("", response_model=TenderProjectResponse)
async def create_tender(
    payload: TenderProjectCreate,
    db: Session = Depends(get_db)
):
    """
    Creates a new Tender Project record.
    """
    from datetime import datetime, timezone
    db_project = TenderProject(
        id=str(uuid.uuid4()),
        project_id=payload.project_id,
        tender_name=payload.tender_name,
        source_label=payload.source_label,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db.add(db_project)
    try:
        db.commit()
        db.refresh(db_project)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create tender project: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "database_error", "message": "Failed to create tender project"}
        )
        
    logger.info(
        "tender_created",
        extra={
            "custom_fields": {
                "event": "tender_created",
                "tender_project_id": db_project.id,
                "project_id": db_project.project_id
            }
        }
    )
    
    return TenderProjectResponse(
        tender_project_id=db_project.id,
        project_id=db_project.project_id,
        tender_name=db_project.tender_name,
        source_label=db_project.source_label,
        created_at=db_project.created_at,
        updated_at=db_project.updated_at
    )


@router.post("/{tender_id}/documents")
async def upload_tender_documents(
    tender_id: str,
    files: List[UploadFile] = File(...),
    document_type: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Accepts one or more files linked to a Tender, validates types and sizes,
    uploads to MinIO, persists metadata, and returns status lists.
    """
    # Verify tender project exists
    project = db.query(TenderProject).filter(TenderProject.id == tender_id).first()
    if not project:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"Tender Project with ID {tender_id} not found"
            }
        )
        
    if not files:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_files",
                "message": "At least one file is required for upload"
            }
        )
        
    allowed_types = {"application/pdf", "image/png", "image/jpeg"}
    uploaded_docs = []
    failed_docs = []
    
    for file in files:
        filename = file.filename or "unnamed_file"
        
        # 1. Validate content type
        if file.content_type not in allowed_types:
            logger.info(
                "document_upload_failure",
                extra={
                    "custom_fields": {
                        "event": "document_upload_failure",
                        "tender_project_id": tender_id,
                        "filename": filename,
                        "reason": f"invalid content type: {file.content_type}"
                    }
                }
            )
            failed_docs.append({
                "filename": filename,
                "error": "invalid_type",
                "message": "Only PDF, PNG, and JPEG files are accepted"
            })
            continue
            
        # 2. Read bytes and validate size
        try:
            file_bytes = await file.read()
        except Exception as read_err:
            logger.info(
                "document_upload_failure",
                extra={
                    "custom_fields": {
                        "event": "document_upload_failure",
                        "tender_project_id": tender_id,
                        "filename": filename,
                        "reason": f"read error: {read_err}"
                    }
                }
            )
            failed_docs.append({
                "filename": filename,
                "error": "read_error",
                "message": "Failed to read file contents"
            })
            continue
            
        file_size = len(file_bytes)
        if file_size == 0:
            logger.info(
                "document_upload_failure",
                extra={
                    "custom_fields": {
                        "event": "document_upload_failure",
                        "tender_project_id": tender_id,
                        "filename": filename,
                        "reason": "empty file"
                    }
                }
            )
            failed_docs.append({
                "filename": filename,
                "error": "empty_file",
                "message": "Uploaded file is empty"
            })
            continue
            
        if file_size > MAX_FILE_SIZE_BYTES:
            logger.info(
                "document_upload_failure",
                extra={
                    "custom_fields": {
                        "event": "document_upload_failure",
                        "tender_project_id": tender_id,
                        "filename": filename,
                        "reason": f"file size {file_size} exceeds max 20MB limit"
                    }
                }
            )
            failed_docs.append({
                "filename": filename,
                "error": "file_too_large",
                "message": "File exceeds the maximum size limit of 20MB"
            })
            continue
            
        # 3. Generate key and upload to MinIO
        document_id = str(uuid.uuid4())
        custom_key = f"project/{project.project_id}/tender/{project.id}/documents/{document_id}/{filename}"
        
        logger.info(
            "document_upload_started",
            extra={
                "custom_fields": {
                    "event": "document_upload_started",
                    "tender_project_id": project.id,
                    "document_id": document_id,
                    "filename": filename,
                    "size_bytes": file_size
                }
            }
        )
        
        try:
            upload_file_to_minio(
                file_bytes=file_bytes,
                content_type=file.content_type,
                original_filename=filename,
                custom_key=custom_key
            )
        except Exception as upload_err:
            logger.error(
                f"MinIO storage upload failed for {filename}: {upload_err}",
                exc_info=True,
                extra={
                    "custom_fields": {
                        "event": "document_upload_failure",
                        "tender_project_id": project.id,
                        "filename": filename,
                        "reason": "storage_upload_error"
                    }
                }
            )
            failed_docs.append({
                "filename": filename,
                "error": "storage_failure",
                "message": "Failed to upload file to MinIO"
            })
            continue
            
        # 4. Save to Database
        db_doc = Document(
            id=document_id,
            tender_project_id=project.id,
            original_filename=filename,
            storage_bucket=settings.MINIO_BUCKET,
            storage_key=custom_key,
            mime_type=file.content_type,
            size_bytes=file_size,
            upload_status="uploaded",
            processing_status="pending",
            document_type=document_type
        )
        db.add(db_doc)
        
        try:
            db.commit()
            db.refresh(db_doc)
            
            logger.info(
                "document_upload_success",
                extra={
                    "custom_fields": {
                        "event": "document_upload_success",
                        "tender_project_id": project.id,
                        "document_id": document_id,
                        "storage_bucket": db_doc.storage_bucket,
                        "storage_key": db_doc.storage_key
                    }
                }
            )
            uploaded_docs.append(db_doc)
        except Exception as db_err:
            db.rollback()
            logger.error(
                f"Database metadata persistence failed for {filename}: {db_err}",
                exc_info=True,
                extra={
                    "custom_fields": {
                        "event": "document_upload_failure",
                        "tender_project_id": project.id,
                        "filename": filename,
                        "reason": "database_error"
                    }
                }
            )
            # Remove file from storage to avoid orphaning
            try:
                minio_client.remove_object(settings.MINIO_BUCKET, custom_key)
            except Exception:
                pass
            failed_docs.append({
                "filename": filename,
                "error": "database_error",
                "message": "Failed to persist document metadata in the database"
            })
            
    return {
        "tender_project_id": project.id,
        "documents": [
            {
                "document_id": doc.id,
                "original_filename": doc.original_filename,
                "mime_type": doc.mime_type,
                "size_bytes": doc.size_bytes,
                "upload_status": doc.upload_status,
                "processing_status": doc.processing_status,
                "document_type": doc.document_type
            } for doc in uploaded_docs
        ],
        "failed": failed_docs
    }


@router.get("/{tender_id}", response_model=TenderProjectDetailResponse)
async def get_tender_details(
    tender_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieves tender metadata along with all linked documents' metadata.
    """
    project = db.query(TenderProject).filter(TenderProject.id == tender_id).first()
    if not project:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"Tender Project with ID {tender_id} not found"
            }
        )
        
    return TenderProjectDetailResponse(
        tender_project_id=project.id,
        project_id=project.project_id,
        tender_name=project.tender_name,
        source_label=project.source_label,
        created_at=project.created_at,
        updated_at=project.updated_at,
        documents=[
            DocumentResponse(
                document_id=doc.id,
                original_filename=doc.original_filename,
                mime_type=doc.mime_type,
                size_bytes=doc.size_bytes,
                upload_status=doc.upload_status,
                processing_status=doc.processing_status,
                document_type=doc.document_type
            ) for doc in project.documents
        ]
    )


def background_ocr_worker(document_id: str, run_layoutlm: bool):
    """
    Background worker task to download a file from MinIO, structure its directory,
    and process it using the OCR pipeline.
    """
    import os
    import shutil
    from pathlib import Path
    from backend.app.db.session import SessionLocal
    from backend.app.core.constants import STORAGE_ROOT
    
    db = SessionLocal()
    try:
        # 1. Fetch document from database
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"Background worker document not found: {document_id}")
            return
            
        logger.info(f"Starting background OCR processing for Document {document_id}")
        
        # 2. Download file from MinIO
        try:
            temp_path = download_file_from_minio(document_id)
        except Exception as e:
            logger.error(f"Failed to download document {document_id} from MinIO: {e}", exc_info=True)
            doc.processing_status = "failed"
            db.commit()
            return
            
        # 3. Setup job directory
        job_dir = STORAGE_ROOT / "jobs" / document_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        ext = Path(temp_path).suffix or ".pdf"
        local_pdf_path = job_dir / f"original{ext}"
        
        try:
            shutil.copy2(temp_path, local_pdf_path)
            # Remove temporary download file
            try:
                os.remove(temp_path)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Failed to move file to job directory for document {document_id}: {e}", exc_info=True)
            doc.processing_status = "failed"
            db.commit()
            return
            
        # 4. Run PDF Ingestion pipeline (hybrid OCR + link extraction)
        from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
        try:
            ingest_parent_tender_pdf(job_id=document_id, pdf_path=local_pdf_path, original_filename=doc.original_filename)
            doc.processing_status = "completed"
            db.commit()
            logger.info(f"Background Ingestion processing completed successfully for Document {document_id}")
        except Exception as e:
            logger.error(f"Ingestion processing pipeline failed for Document {document_id}: {e}", exc_info=True)
            doc.processing_status = "failed"
            db.commit()
            
    except Exception as e:
        logger.critical(f"Critical error in background OCR worker for document {document_id}: {e}", exc_info=True)
    finally:
        db.close()


@router.post("/{tender_id}/documents/{document_id}/process")
async def process_tender_document(
    tender_id: str,
    document_id: str,
    background_tasks: BackgroundTasks,
    run_layoutlm: bool = False,
    db: Session = Depends(get_db)
):
    """
    Triggers the background OCR processing pipeline for a specific document
    associated with a Tender Project.
    """
    # 1. Validate tender project exists
    project = db.query(TenderProject).filter(TenderProject.id == tender_id).first()
    if not project:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"Tender Project with ID {tender_id} not found"
            }
        )
        
    # 2. Validate document exists and belongs to project
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.tender_project_id == tender_id
    ).first()
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"Document with ID {document_id} not found for Tender Project {tender_id}"
            }
        )
        
    # 3. Validate current status
    if doc.processing_status == "processing":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "already_processing",
                "message": "Document is already currently being processed"
            }
        )
    elif doc.processing_status == "completed":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "already_completed",
                "message": "Document has already been successfully processed"
            }
        )
        
    # 4. Set status to processing and commit
    doc.processing_status = "processing"
    try:
        db.commit()
        db.refresh(doc)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update document status to processing: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "database_error",
                "message": "Failed to trigger processing in database"
            }
        )
        
    # 5. Enqueue background task
    background_tasks.add_task(background_ocr_worker, doc.id, run_layoutlm)
    
    logger.info(
        "document_processing_triggered",
        extra={
            "custom_fields": {
                "event": "document_processing_triggered",
                "tender_project_id": tender_id,
                "document_id": document_id,
                "run_layoutlm": run_layoutlm
            }
        }
    )
    
    return {
        "document_id": doc.id,
        "processing_status": "processing",
        "message": "OCR processing task has been started in the background"
    }


class ProcessCompleteRequest(BaseModel):
    tender_id: str
    file_id: str
    email: Optional[str] = None


@router.post("/process-complete")
async def process_complete(
    payload: ProcessCompleteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Day 4 MVP endpoint: Loads OCR results, maps to tender_information schema,
    persists in PostgreSQL, exports to CSV, and sends CSV via email background task.
    """
    import json
    from datetime import datetime, timezone
    
    # 1. Validate project and document presence
    project = db.query(TenderProject).filter(TenderProject.id == payload.tender_id).first()
    if not project:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"Tender Project with ID {payload.tender_id} not found"
            }
        )
        
    doc = db.query(Document).filter(
        Document.id == payload.file_id,
        Document.tender_project_id == payload.tender_id
    ).first()
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"Document with ID {payload.file_id} not found for Tender Project {payload.tender_id}"
            }
        )
        
    # 2. Check for extracted_fields.json existence
    extracted_fields_path = STORAGE_ROOT / "jobs" / payload.file_id / "extracted_fields.json"
    if not extracted_fields_path.exists():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "ocr_not_completed",
                "message": "OCR extraction results not found. Please trigger document processing first."
            }
        )
        
    try:
        with open(extracted_fields_path, "r", encoding="utf-8") as f:
            extracted_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read extracted fields file for document {payload.file_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "read_error",
                "message": "Failed to read OCR extraction output"
            }
        )
        
    # 3. Map fields to TenderInformation shape
    mapped_info = map_extracted_fields_to_tender_info(
        tender_project_id=payload.tender_id,
        document_id=payload.file_id,
        extracted_data=extracted_data,
        tender_name=project.tender_name
    )
    
    # 4. Upsert row in PostgreSQL (TenderInformation table)
    db_info = db.query(TenderInformation).filter(
        TenderInformation.tender_project_id == payload.tender_id,
        TenderInformation.document_id == payload.file_id
    ).first()
    
    if db_info:
        for col in CSV_COLUMNS:
            setattr(db_info, col, getattr(mapped_info, col))
        db_info.updated_at = datetime.now(timezone.utc)
        final_info = db_info
    else:
        db.add(mapped_info)
        final_info = mapped_info
        
    try:
        db.commit()
        db.refresh(final_info)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to persist tender information: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "database_error",
                "message": "Failed to persist tender information mapping results"
            }
        )
        
    # 5. Export saved row to CSV
    csv_filename = "tender_information.csv"
    csv_path = STORAGE_ROOT / "jobs" / payload.file_id / csv_filename
    try:
        export_tender_info_to_csv(final_info, csv_path)
    except Exception as e:
        logger.error(f"Failed to export tender information to CSV: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "export_error",
                "message": "Failed to export tender information to CSV"
            }
        )
        
    # 6. Send email automatically in BackgroundTasks (only if a recipient was given)
    if payload.email:
        background_tasks.add_task(send_tender_csv_email, payload.email, csv_path, payload.tender_id)
    
    logger.info(
        "tender_processing_completed",
        extra={
            "custom_fields": {
                "event": "tender_processing_completed",
                "tender_project_id": payload.tender_id,
                "document_id": payload.file_id,
                "tender_information_id": final_info.id,
                "recipient_email": payload.email,
                "csv_path": str(csv_path)
            }
        }
    )
    
    # 7. Return success response
    return {
        "tender_information_id": final_info.id,
        "tender_project_id": final_info.tender_project_id,
        "document_id": final_info.document_id,
        "csv_filename": csv_filename,
        "csv_url": f"/storage/jobs/{payload.file_id}/{csv_filename}",
        "message": (
            "Tender mapping results successfully persisted, exported to CSV, and queued for email delivery."
            if payload.email
            else "Tender mapping results successfully persisted and exported to CSV."
        )
    }


class ProcessRequest(BaseModel):
    tender_id: int
    file_id: str
    email: str


@router.post("/process")
async def process_tender(
    payload: ProcessRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Day 4/5 MVP endpoint: Connects OCR output, maps to tender_information structure,
    saves in PostgreSQL, exports to CSV, and emails via background task.
    """
    import json
    
    # 1. Load raw extraction JSON using file_id
    extracted_fields_path = STORAGE_ROOT / "jobs" / payload.file_id / "extracted_fields.json"
    if not extracted_fields_path.exists():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "ocr_not_completed",
                "message": f"OCR results not found for file_id: {payload.file_id}. Please run OCR first."
            }
        )
        
    try:
        with open(extracted_fields_path, "r", encoding="utf-8") as f:
            raw_extraction = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read OCR result: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to read raw OCR extraction output"
        )
        
    # 2. Map extraction data
    from backend.app.services.tender_mapper import map_extraction_to_tender_information
    mapped_payload = map_extraction_to_tender_information(raw_extraction, payload.tender_id)
    
    # 3. Save payload to PostgreSQL using raw SQL connection
    from backend.app.services.tender_repository import save_tender_information
    try:
        saved_row = save_tender_information(db, mapped_payload)
        db.commit()
    except Exception as e:
        logger.error(f"Repository save failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Database save operation failed: {str(e)}"
        )
        
    # 4. Export CSV
    from backend.app.services.export_service import export_tender_information_csv
    try:
        job_dir = STORAGE_ROOT / "jobs" / payload.file_id
        csv_filepath = export_tender_information_csv(saved_row, str(job_dir))
    except Exception as e:
        logger.error(f"CSV export failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="CSV generation failed"
        )
        
    # 5. Enqueue background email dispatch task
    from backend.app.services.email_service import send_email_with_attachment
    subject = f"MVP Mapped Tender Sheet - ID: {payload.tender_id}"
    body = f"Hello,\n\nPlease find attached the exported CSV for Tender ID: {payload.tender_id}.\n"
    background_tasks.add_task(
        send_email_with_attachment,
        payload.email,
        subject,
        body,
        csv_filepath
    )
    
    # 6. Return success response
    return {
        "status": "success",
        "tender_information_id": saved_row.get("id"),
        "tender_id": payload.tender_id,
        "csv_file": f"/storage/jobs/{payload.file_id}/tender_{payload.tender_id}_export.csv",
        "email_queued": True
    }


# ==============================================================================
# WORKSPACE API ENDPOINTS — Frontend-facing unified tender detail flow
# ==============================================================================

import json as _json
import shutil as _shutil

def _run_ingest_background(job_id: str, pdf_path: str, original_filename: str):
    """
    Background task: runs the parent tender ingest pipeline and persists
    the conforming tender detail JSON to disk.
    """
    from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
    from backend.app.repositories.job_store import update_status
    from backend.app.core.constants import JobStatus
    from backend.app.db.session import SessionLocal
    from backend.app.models.tender_project import TenderProject
    from backend.app.models.document import Document
    import os
    import mimetypes
    from pathlib import Path

    try:
        update_status(job_id, JobStatus.PROCESSING)
        result = ingest_parent_tender_pdf(
            job_id=job_id,
            pdf_path=Path(pdf_path),
            original_filename=original_filename
        )

        # Store child files and parent document in PostgreSQL
        db = SessionLocal()
        try:
            # 1. Ensure TenderProject exists in PostgreSQL
            project = db.query(TenderProject).filter(TenderProject.id == job_id).first()
            if not project:
                project = TenderProject(
                    id=job_id,
                    project_id=job_id,
                    tender_name=result.get("title") or original_filename.replace(".pdf", ""),
                    source_label="Workspace Ingest"
                )
                db.add(project)
                db.commit()
                db.refresh(project)

            # 2. Insert parent document metadata into PostgreSQL if not exists
            parent_doc = db.query(Document).filter(
                Document.tender_project_id == job_id,
                Document.document_type == "parent"
            ).first()
            if not parent_doc:
                parent_doc = Document(
                    id=str(uuid.uuid4()),
                    tender_project_id=job_id,
                    original_filename=original_filename,
                    storage_bucket="local-disk",
                    storage_key=pdf_path,
                    mime_type="application/pdf",
                    size_bytes=os.path.getsize(pdf_path),
                    upload_status="uploaded",
                    processing_status="completed",
                    document_type="parent"
                )
                db.add(parent_doc)
                db.commit()

            # 3. Iterate over the extracted Linked PDFs and register them
            for l in result.get("documents", {}).get("extractedLinkedPdfs", []):
                local_path = l.get("local_path")
                if local_path and os.path.exists(local_path):
                    # Generate a unique document UUID
                    doc_uuid = str(uuid.uuid4())
                    
                    # Guess MIME type
                    mime_type, _ = mimetypes.guess_type(local_path)
                    mime_type = mime_type or "application/pdf"
                    
                    db_doc = Document(
                        id=doc_uuid,
                        tender_project_id=job_id,
                        original_filename=l["name"],
                        storage_bucket="local-disk",
                        storage_key=local_path,
                        mime_type=mime_type,
                        size_bytes=os.path.getsize(local_path),
                        upload_status="uploaded",
                        processing_status="pending",
                        document_type="child_document"
                    )
                    db.add(db_doc)
                    db.commit()
                    
                    # Update API payload so the frontend accesses this document directly
                    l["id"] = doc_uuid
                    l["url"] = f"/tenders/documents/{doc_uuid}/download"

        except Exception as db_err:
            db.rollback()
            logger.error(f"[ERROR] Postgres database storage mapping failed: {db_err}", exc_info=True)
        finally:
            db.close()

        # Persist the conforming payload as JSON so GET can serve it
        result_path = Path(pdf_path).parent / "tender_detail.json"
        with open(result_path, "w", encoding="utf-8") as f:
            _json.dump(result, f, ensure_ascii=False, indent=2)

        update_status(
            job_id,
            JobStatus.COMPLETED,
            result_path=str(result_path),
            page_count=len(result.get("rawTextPages", []))
        )
        logger.info(f"Workspace ingest completed for job {job_id}")
    except Exception as e:
        logger.error(f"Workspace ingest failed for job {job_id}: {e}", exc_info=True)
        update_status(job_id, JobStatus.FAILED, error_message=str(e))


@router.post("/workspace/ingest", status_code=201)
async def workspace_ingest(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Single-call endpoint: uploads a parent tender PDF and immediately
    enqueues background processing via the parent ingest pipeline.
    Returns a job_id the frontend can poll.
    """
    # Validate
    if not file.filename:
        raise HTTPException(status_code=400, detail="A PDF file is required")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Create job directory and save file
    job_id = str(uuid.uuid4())
    job_dir = STORAGE_ROOT / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = job_dir / file.filename
    with open(pdf_path, "wb") as f:
        f.write(file_bytes)

    # Register job in SQLite store
    from backend.app.repositories.job_store import create_job
    create_job(job_id=job_id, filename=file.filename, pdf_path=str(pdf_path))

    # Enqueue background processing
    background_tasks.add_task(
        _run_ingest_background, job_id, str(pdf_path), file.filename
    )

    logger.info(f"Workspace ingest queued for job {job_id}, file: {file.filename}")

    return {
        "job_id": job_id,
        "status": "pending",
        "original_filename": file.filename
    }


@router.get("/workspace/list")
async def workspace_list_tenders():
    """
    Returns all completed tender detail payloads as an array.
    For pending/processing/failed jobs, returns skeleton entries.
    """
    from backend.app.repositories.job_store import get_all_jobs

    all_jobs = get_all_jobs()
    results = []

    for job in all_jobs:
        job_id = job["job_id"]
        job_dir = STORAGE_ROOT / "jobs" / job_id
        detail_path = job_dir / "tender_detail.json"

        if job["status"] == "completed" and detail_path.exists():
            try:
                with open(detail_path, "r", encoding="utf-8") as f:
                    payload = _json.load(f)
                # Ensure frontend-required fields have defaults
                payload.setdefault("reviewer_name", None)
                payload.setdefault("location_city", "")
                payload.setdefault("location_state", "")
                payload.setdefault("sector", "Infrastructure")
                payload.setdefault("snippet", "")
                payload.setdefault("updated_at", job.get("completed_at", ""))
                payload.setdefault("department", "")
                # Derive snippet from raw text if empty
                if not payload["snippet"] and payload.get("rawTextPages"):
                    first_text = payload["rawTextPages"][0].get("text", "")
                    payload["snippet"] = first_text[:200].replace("\n", " ").strip()
                # Derive location components
                loc = payload.get("location", "")
                if loc and not payload["location_city"]:
                    parts = [p.strip() for p in loc.split(",")]
                    payload["location_city"] = parts[0] if parts else ""
                    payload["location_state"] = parts[1] if len(parts) > 1 else ""

                results.append(payload)
            except Exception as e:
                logger.error(f"Failed to read tender_detail.json for job {job_id}: {e}")
        else:
            # Return skeleton for pending/processing/failed jobs
            filename = job.get("original_filename", "Unknown")
            title = filename.replace(".pdf", "").replace("_", " ").replace("-", " ")
            results.append({
                "id": job_id,
                "title": title,
                "authorityName": "",
                "deadline": "",
                "tenderValue": "",
                "emdAmount": "",
                "tenderFee": "",
                "location": "",
                "documents": {
                    "sourceDocuments": [{
                        "id": f"src-{job_id}",
                        "name": filename,
                        "kind": "pdf",
                        "origin": "source",
                        "url": f"/storage/jobs/{job_id}/{filename}",
                        "downloadable": True,
                        "openable": True,
                        "isPrimary": True,
                        "uploadedBy": "System"
                    }],
                    "generatedOutputs": [],
                    "extractedLinkedPdfs": [],
                    "mentionedAttachments": []
                },
                "infoSheetSections": [],
                "rawTextPages": [],
                "parse_status": job["status"],  # pending / processing / failed
                "parse_confidence": 0,
                "review_status": "unreviewed",
                "issues_count": 0,
                "reviewer_name": None,
                "location_city": "",
                "location_state": "",
                "sector": "Infrastructure",
                "snippet": f"File uploaded: {filename}. Pipeline status: {job['status']}.",
                "updated_at": job.get("created_at", ""),
                "department": ""
            })

    return results


@router.get("/workspace/{job_id}")
async def workspace_get_tender(job_id: str):
    """
    Returns the full conforming tender detail for a single job.
    """
    from backend.app.repositories.job_store import get_job

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_dir = STORAGE_ROOT / "jobs" / job_id
    detail_path = job_dir / "tender_detail.json"

    if job["status"] == "completed" and detail_path.exists():
        try:
            with open(detail_path, "r", encoding="utf-8") as f:
                payload = _json.load(f)
            payload.setdefault("reviewer_name", None)
            payload.setdefault("location_city", "")
            payload.setdefault("location_state", "")
            payload.setdefault("sector", "Infrastructure")
            payload.setdefault("snippet", "")
            payload.setdefault("updated_at", job.get("completed_at", ""))
            payload.setdefault("department", "")
            return payload
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read result: {e}")

    # Return skeleton for non-completed jobs
    filename = job.get("original_filename", "Unknown")
    title = filename.replace(".pdf", "").replace("_", " ").replace("-", " ")
    return {
        "id": job_id,
        "title": title,
        "authorityName": "",
        "deadline": "",
        "tenderValue": "",
        "emdAmount": "",
        "tenderFee": "",
        "location": "",
        "documents": {
            "sourceDocuments": [{
                "id": f"src-{job_id}",
                "name": filename,
                "kind": "pdf",
                "origin": "source",
                "url": f"/storage/jobs/{job_id}/{filename}",
                "downloadable": True,
                "openable": True,
                "isPrimary": True,
                "uploadedBy": "System"
            }],
            "generatedOutputs": [],
            "extractedLinkedPdfs": [],
            "mentionedAttachments": []
        },
        "infoSheetSections": [],
        "rawTextPages": [],
        "parse_status": job["status"],
        "parse_confidence": 0,
        "review_status": "unreviewed",
        "issues_count": 0,
        "reviewer_name": None,
        "location_city": "",
        "location_state": "",
        "sector": "Infrastructure",
        "snippet": f"File uploaded: {filename}. Pipeline status: {job['status']}.",
        "updated_at": job.get("created_at", ""),
        "department": ""
    }


from fastapi.responses import FileResponse

@router.get("/documents/{document_id}/download")
async def download_extracted_document(document_id: str, db: Session = Depends(get_db)):
    """
    Downloads an extracted child document (or parent document) from local disk
    by checking its path in the database.
    """
    from backend.app.models.document import Document
    import os
    
    db_doc = db.query(Document).filter(Document.id == document_id).first()
    if not db_doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    local_path = db_doc.storage_key
    if not local_path or not os.path.exists(local_path):
        raise HTTPException(status_code=404, detail="File not found on local disk")
        
    return FileResponse(
        path=local_path,
        media_type=db_doc.mime_type,
        filename=db_doc.original_filename
    )

