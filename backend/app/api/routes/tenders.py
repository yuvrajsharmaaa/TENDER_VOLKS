import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Form, BackgroundTasks
from sqlalchemy.orm import Session

from backend.app.services.storage import upload_file_to_minio, download_file_from_minio, StorageError
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.db.session import get_db
from backend.app.models.tender_project import TenderProject
from backend.app.models.document import Document
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
    from ocr.pipeline import process_pdf
    
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
            
        # 4. Run PDF OCR processor
        try:
            process_pdf(job_id=document_id, pdf_path=local_pdf_path, run_layoutlm=run_layoutlm)
            doc.processing_status = "completed"
            db.commit()
            logger.info(f"Background OCR processing completed successfully for Document {document_id}")
        except Exception as e:
            logger.error(f"OCR processing pipeline failed for Document {document_id}: {e}", exc_info=True)
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



