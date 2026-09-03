import uuid
import logging
from pathlib import Path
from typing import List, Optional, Any, Dict, cast
from pydantic import BaseModel
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Form, BackgroundTasks
from fastapi.responses import FileResponse
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
from backend.app.schemas.pqc_recommendation import resolve_tender_title

logger = get_logger(__name__)

router = APIRouter(prefix="/tenders", tags=["tenders"])

# Max file size constant (20 MB)
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024


def _get_primary_pdf_filename(payload: dict) -> str:
    source_docs = payload.get("documents", {}).get("sourceDocuments", [])
    if source_docs:
        primary_doc = next((d for d in source_docs if d.get("isPrimary")), source_docs[0])
        return primary_doc.get("name", "original.pdf")
    return "original.pdf"


def _infosheet_filename(payload: dict) -> str:
    original_filename = _get_primary_pdf_filename(payload)
    if original_filename.lower().endswith(".pdf"):
        original_filename = original_filename[:-4]
    return f"{original_filename}_InfoSheet.xlsx"


def _refresh_infosheet_output_links(payload: dict, job_id: str) -> None:
    for output in payload.get("documents", {}).get("generatedOutputs", []):
        if output.get("outputKind") == "info_sheet":
            output["url"] = f"/tenders/workspace/{job_id}/infosheet/download"
            output["downloadable"] = True
            output["openable"] = True


def _regenerate_infosheet_workbook(job_id: str, payload: dict) -> Path:
    from backend.app.services.tender_mapper import build_infosheet_data
    from backend.app.services.info_sheet_generator import generate_info_sheet_csv

    job_dir = STORAGE_ROOT / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = job_dir / _infosheet_filename(payload)
    infosheet_data = build_infosheet_data(
        payload.get("infoSheetSections", []),
        payload.get("rawTextPages", []),
        job_id=job_id,
    )
    infosheet_data["_info_sheet_sections"] = payload.get("infoSheetSections", [])
    generate_info_sheet_csv(infosheet_data, str(xlsx_path))
    return xlsx_path

from backend.app.schemas.tender_project import (
    TenderProjectCreate,
    TenderProjectResponse,
    TenderProjectDetailResponse,
    DocumentResponse,
    TenderUploadResponse,
    TenderProcessRequest,
    TenderProcessResponse
)

@router.post("/upload", status_code=201, response_model=TenderUploadResponse)
async def upload_tender(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None  # type: ignore
):
    """
    Validates an uploaded PDF file, saves it, creates job records,
    and returns unified job_id, file_id, and tender_id.
    """
    from backend.app.api.upload import upload_pdf
    return await upload_pdf(file=file, background_tasks=background_tasks)



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
        tender_project_id=str(db_project.id),
        project_id=str(db_project.project_id),
        tender_name=str(db_project.tender_name) if db_project.tender_name is not None else None,
        source_label=str(db_project.source_label) if db_project.source_label is not None else None,
        created_at=cast(Any, db_project.created_at),
        updated_at=cast(Any, db_project.updated_at)
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
        tender_project_id=str(project.id),
        project_id=str(project.project_id),
        tender_name=str(project.tender_name) if project.tender_name is not None else None,
        source_label=str(project.source_label) if project.source_label is not None else None,
        created_at=cast(Any, project.created_at),
        updated_at=cast(Any, project.updated_at),
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
            setattr(doc, "processing_status", "failed")
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
            setattr(doc, "processing_status", "failed")
            db.commit()
            return
            
        # 4. Run PDF OCR processor
        try:
            process_pdf(job_id=document_id, pdf_path=local_pdf_path, run_layoutlm=run_layoutlm)
            setattr(doc, "processing_status", "completed")
            db.commit()
            logger.info(f"Background OCR processing completed successfully for Document {document_id}")
        except Exception as e:
            logger.error(f"OCR processing pipeline failed for Document {document_id}: {e}", exc_info=True)
            setattr(doc, "processing_status", "failed")
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
    force_reprocess: bool = False,
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
    if str(doc.processing_status) == "processing":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "already_processing",
                "message": "Document is already currently being processed"
            }
        )
    elif str(doc.processing_status) == "completed" and not force_reprocess:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "already_completed",
                "message": "Document has already been successfully processed"
            }
        )
        
    # 4. Set status to processing and commit
    setattr(doc, "processing_status", "processing")
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
    background_tasks.add_task(background_ocr_worker, str(doc.id), run_layoutlm)
    
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
        tender_name=str(project.tender_name) if project.tender_name is not None else None
    )
    
    # 4. Upsert row in PostgreSQL (TenderInformation table)
    db_info = db.query(TenderInformation).filter(
        TenderInformation.tender_project_id == payload.tender_id,
        TenderInformation.document_id == payload.file_id
    ).first()
    
    if db_info:
        for col in CSV_COLUMNS:
            setattr(db_info, col, getattr(mapped_info, col))
        setattr(db_info, "updated_at", datetime.now(timezone.utc))
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
import json as _json
import shutil as _shutil
from backend.app.celery_app import celery_app

@celery_app.task(name="backend.app.api.routes.tenders._run_ingest_background")
def _run_ingest_background(job_id: str, pdf_path: Optional[str] = None, original_filename: Optional[str] = None):
    """
    Background task: runs the parent tender ingest pipeline and persists
    the conforming tender detail JSON to disk.
    """
    from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
    from backend.app.repositories.job_repository import update_status, get_job
    from backend.app.core.constants import JobStatus
    from backend.app.db.session import SessionLocal
    from backend.app.models.tender_project import TenderProject
    from backend.app.models.document import Document
    import os
    import mimetypes
    from pathlib import Path

    if not pdf_path or not original_filename:
        job_record = get_job(job_id)
        if job_record:
            pdf_path = pdf_path or job_record.get("pdf_path")
            original_filename = original_filename or job_record.get("original_filename")
        if not pdf_path:
            pdf_path = str(STORAGE_ROOT / "jobs" / job_id / "original.pdf")
        if not original_filename:
            original_filename = "original.pdf"

    logger.info(f"[BACKGROUND_TASK][Job {job_id}] Ingest background task started for '{original_filename}' at path '{pdf_path}'")
    try:
        logger.info(f"[OBSERVABILITY] status changed to processing for job {job_id}")
        update_status(job_id, JobStatus.PROCESSING)
        
        result = ingest_parent_tender_pdf(
            job_id=job_id,
            pdf_path=Path(pdf_path),
            original_filename=original_filename
        )
        logger.info(f"[OBSERVABILITY] info sheet generated for job {job_id}")

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
                    size_bytes=os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0,
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
                    doc_uuid = str(uuid.uuid4())
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
                    
                    l["id"] = doc_uuid
                    l["url"] = f"/tenders/documents/{doc_uuid}/download"
            
            logger.info(f"[OBSERVABILITY] child docs extracted for job {job_id}")

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
        logger.info(f"[OBSERVABILITY] final completion written for job {job_id}")
    except Exception as e:
        logger.error(f"[BACKGROUND_TASK_FAILED] Workspace ingest background task failed for job {job_id}: {e}", exc_info=True)
        try:
            update_status(job_id, JobStatus.FAILED, error_message=str(e))
            logger.info(f"[OBSERVABILITY] failure written with error message for job {job_id}: {e}")
        except Exception as write_err:
            logger.error(f"Failed to write FAILED state to database for job {job_id}: {write_err}", exc_info=True)


@router.post("/workspace/ingest", status_code=201, response_model=TenderUploadResponse)
async def workspace_ingest(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None  # type: ignore
):
    """
    Single-call workspace ingest endpoint: uploads PDF and immediately
    enqueues background OCR / ingestion processing.
    """
    from backend.app.api.upload import upload_pdf
    return await upload_pdf(file=file, background_tasks=background_tasks)



@router.get("/workspace/list")
async def workspace_list_tenders():
    """
    Returns all completed tender detail payloads as an array.
    For pending/processing/failed jobs, returns skeleton entries.
    """
    from backend.app.repositories.job_repository import get_all_jobs

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

                _refresh_infosheet_output_links(payload, job_id)
                payload["title"] = resolve_tender_title(payload.get("title"), payload.get("id"))
                results.append(payload)
            except Exception as e:
                logger.error(f"Failed to read tender_detail.json for job {job_id}: {e}")
        else:
            # Return skeleton for pending/processing/failed jobs
            filename = job.get("original_filename", "Unknown")
            raw_title = filename.replace(".pdf", "").replace("_", " ").replace("-", " ")
            title = resolve_tender_title(raw_title, job_id)
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
    from backend.app.repositories.job_repository import get_job

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
            _refresh_infosheet_output_links(payload, job_id)
            payload["title"] = resolve_tender_title(payload.get("title"), payload.get("id"))
            return payload
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read result: {e}")

    # Return skeleton for non-completed jobs
    filename = job.get("original_filename", "Unknown")
    raw_title = filename.replace(".pdf", "").replace("_", " ").replace("-", " ")
    title = resolve_tender_title(raw_title, job_id)
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


@router.get("/workspace/{job_id}/infosheet/download")
async def download_workspace_infosheet(job_id: str):
    """
    Regenerates the InfoSheet workbook from the reviewed frontend artifact
    before download, so Excel matches the values currently shown in preview.
    """
    job_dir = STORAGE_ROOT / "jobs" / job_id
    detail_path = job_dir / "tender_detail.json"
    if not detail_path.exists():
        raise HTTPException(status_code=404, detail="Tender detail not found")

    try:
        with open(detail_path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        xlsx_path = _regenerate_infosheet_workbook(job_id, data)
    except Exception as e:
        logger.error(f"Failed to regenerate info sheet workbook for job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate InfoSheet workbook")

    return FileResponse(
        path=str(xlsx_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=xlsx_path.name,
    )


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
        
    local_path = str(db_doc.storage_key) if db_doc.storage_key else None
    if not local_path or not os.path.exists(local_path):
        raise HTTPException(status_code=404, detail="File not found on local disk")
        
    return FileResponse(
        path=local_path,
        media_type=str(db_doc.mime_type) if db_doc.mime_type else None,
        filename=str(db_doc.original_filename) if db_doc.original_filename else None
    )


@router.delete("/workspace/{job_id}", status_code=200)
async def workspace_delete_tender(job_id: str, db: Session = Depends(get_db)):
    """
    Deletes a tender, including its job record in SQLite, its project and document
    records in PostgreSQL, and its files on disk.
    """
    import shutil
    from backend.app.repositories.job_repository import get_job, delete_job
    from backend.app.models.tender_project import TenderProject
    
    # 1. Check if job exists in SQLite
    job = get_job(job_id)
    if not job:
        # Check if the TenderProject exists in Postgres anyway, in case SQLite job is missing
        project = db.query(TenderProject).filter(TenderProject.id == job_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Tender not found")
        else:
            # Delete from Postgres
            db.delete(project)
            db.commit()
            return {"status": "success", "message": "Tender project deleted from Postgres"}

    # 2. Delete job directory from disk
    job_dir = STORAGE_ROOT / "jobs" / job_id
    if job_dir.exists():
        try:
            shutil.rmtree(job_dir)
        except Exception as e:
            logger.error(f"Failed to delete job directory {job_dir}: {e}", exc_info=True)

    # 3. Delete from SQLite
    try:
        delete_job(job_id)
    except Exception as e:
        logger.error(f"Failed to delete job {job_id} from SQLite: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete job from SQLite")

    # 4. Delete from PostgreSQL (TenderProject and cascaded Documents)
    project = db.query(TenderProject).filter(TenderProject.id == job_id).first()
    if project:
        try:
            db.delete(project)
            db.commit()
        except Exception as db_err:
            db.rollback()
            logger.error(f"Failed to delete project {job_id} from PostgreSQL: {db_err}", exc_info=True)
    
    logger.info(f"Workspace delete completed for job {job_id}")
    return {"status": "success", "message": "Tender deleted successfully"}


class FieldUpdateRequest(BaseModel):
    value: str


@router.put("/workspace/{job_id}/fields/{field_id}")
async def update_workspace_field(job_id: str, field_id: str, payload: FieldUpdateRequest):
    job_dir = STORAGE_ROOT / "jobs" / job_id
    detail_path = job_dir / "tender_detail.json"
    if not detail_path.exists():
        raise HTTPException(status_code=404, detail="Tender detail not found")
        
    try:
        with open(detail_path, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read tender details: {e}")
        
    # Find and update the field
    found = False
    for sec in data.get("infoSheetSections", []):
        for f in sec.get("fields", []):
            if f.get("id") == field_id:
                f["value"] = payload.value
                f["status"] = "edited"
                found = True
                # Record user correction into few-shot memory store for continuous learning
                try:
                    from backend.app.services.llm_field_resolver import record_correction
                    target_key = f.get("field_name") or f.get("label")
                    anchor_ctx = f.get("sourceSnippet") or str(payload.value)
                    if target_key:
                        record_correction(target_key, payload.value, anchor_ctx)
                except Exception as mem_err:
                    logger.warning(f"Could not log user field correction to memory: {mem_err}")
                break
        if found:
            break
            
    if not found:
        raise HTTPException(status_code=404, detail=f"Field with ID {field_id} not found")
        
    # Recalculate issues_count
    issues = 0
    for sec in data.get("infoSheetSections", []):
        for f in sec.get("fields", []):
            if f.get("critical") and f.get("status") == "missing":
                issues += 1
            elif f.get("status") == "extracted" and f.get("confidence", 100) < 70:
                issues += 1
                
    unresolved_mentions = 0
    mentioned = data.get("documents", {}).get("mentionedAttachments", [])
    for m in mentioned:
        if not m.get("resolved", False):
            unresolved_mentions += 1
    issues += unresolved_mentions
    data["issues_count"] = issues
    
    # Save tender_detail.json
    try:
        with open(detail_path, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save tender details: {e}")
        
    # Regenerate workbook
    try:
        _regenerate_infosheet_workbook(job_id, data)
        _refresh_infosheet_output_links(data, job_id)
    except Exception as e:
        logger.error(f"Failed to regenerate info sheet workbook for job {job_id}: {e}", exc_info=True)
        
    return data


@router.post("/workspace/{job_id}/fields/{field_id}/verify")
async def verify_workspace_field(job_id: str, field_id: str):
    job_dir = STORAGE_ROOT / "jobs" / job_id
    detail_path = job_dir / "tender_detail.json"
    if not detail_path.exists():
        raise HTTPException(status_code=404, detail="Tender detail not found")
        
    try:
        with open(detail_path, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read tender details: {e}")
        
    # Find and verify the field
    found = False
    for sec in data.get("infoSheetSections", []):
        for f in sec.get("fields", []):
            if f.get("id") == field_id:
                f["status"] = "verified"
                found = True
                break
        if found:
            break
            
    if not found:
        raise HTTPException(status_code=404, detail=f"Field with ID {field_id} not found")
        
    # Recalculate issues_count
    issues = 0
    for sec in data.get("infoSheetSections", []):
        for f in sec.get("fields", []):
            if f.get("critical") and f.get("status") == "missing":
                issues += 1
            elif f.get("status") == "extracted" and f.get("confidence", 100) < 70:
                issues += 1
                
    unresolved_mentions = 0
    mentioned = data.get("documents", {}).get("mentionedAttachments", [])
    for m in mentioned:
        if not m.get("resolved", False):
            unresolved_mentions += 1
    issues += unresolved_mentions
    data["issues_count"] = issues
    
    # Save tender_detail.json
    try:
        with open(detail_path, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save tender details: {e}")
        
    # Regenerate workbook
    try:
        _regenerate_infosheet_workbook(job_id, data)
        _refresh_infosheet_output_links(data, job_id)
    except Exception as e:
        logger.error(f"Failed to regenerate info sheet workbook for job {job_id}: {e}", exc_info=True)
        
    return data


class ReviewCompleteRequest(BaseModel):
    reviewer_name: str


@router.post("/workspace/{job_id}/review")
async def review_workspace_tender(job_id: str, payload: ReviewCompleteRequest):
    job_dir = STORAGE_ROOT / "jobs" / job_id
    detail_path = job_dir / "tender_detail.json"
    if not detail_path.exists():
        raise HTTPException(status_code=404, detail="Tender detail not found")
        
    try:
        with open(detail_path, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read tender details: {e}")
        
    # Mark review completed
    data["review_status"] = "completed"
    data["reviewer_name"] = payload.reviewer_name
    
    # Mark all fields as verified
    for sec in data.get("infoSheetSections", []):
        for f in sec.get("fields", []):
            if f.get("status") in ("extracted", "edited"):
                f["status"] = "verified"
                
    # Recalculate issues_count
    issues = 0
    for sec in data.get("infoSheetSections", []):
        for f in sec.get("fields", []):
            if f.get("critical") and f.get("status") == "missing":
                issues += 1
            elif f.get("status") == "extracted" and f.get("confidence", 100) < 70:
                issues += 1
                
    unresolved_mentions = 0
    mentioned = data.get("documents", {}).get("mentionedAttachments", [])
    for m in mentioned:
        if not m.get("resolved", False):
            unresolved_mentions += 1
    issues += unresolved_mentions
    data["issues_count"] = issues
    
    # Save tender_detail.json
    try:
        with open(detail_path, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save tender details: {e}")
        
    # Regenerate workbook
    try:
        _regenerate_infosheet_workbook(job_id, data)
        _refresh_infosheet_output_links(data, job_id)
    except Exception as e:
        logger.error(f"Failed to regenerate info sheet workbook for job {job_id}: {e}", exc_info=True)
        
    return data


# ─────────────────────────────────────────────────────────────────────────────
# PQC Recommendation & Multi-Signal Composite Ranking Endpoint
# ─────────────────────────────────────────────────────────────────────────────
from backend.app.schemas.pqc_recommendation import (
    PQCRecommendationRequest,
    PQCRecommendationResponse,
    resolve_tender_title
)
from backend.app.services.pqc_recommendation_service import PQCRecommendationService
import pandas as pd


@router.post("/pqc/recommend", response_model=PQCRecommendationResponse)
def recommend_pqc_tenders(
    payload: Optional[PQCRecommendationRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Synchronous PQC Tender Recommendation and Ranking Endpoint.
    Combines:
      - Signal 1 (0.35): Deterministic Statutory Compliance (F_hard)
      - Signal 2 (0.15): LightGBM 16-feature win probability
      - Signal 3 (0.35): Qdrant Top-5 historical neighbor track record
      - Signal 4 (0.15): Groq LLM (llama-3.1-8b-instant) strategic fit
    """
    req = payload or PQCRecommendationRequest()
    service = PQCRecommendationService()
    
    tenders_data = []

    # 1. Fetch from active DB if requested
    if req.source == "db":
        try:
            db_tenders = db.query(TenderInformation).all()
            for t in db_tenders:
                t_val = float(t.tender_value) if t.tender_value is not None else 0.0
                t_emd = float(t.emd_amount) if t.emd_amount is not None else 0.0
                t_pbg = float(t.pbg_percentage) if t.pbg_percentage is not None else 0.0
                t_dur = float(t.pbg_duration) if t.pbg_duration is not None else 0.0
                t_ld = float(t.max_ld_percentage) if t.max_ld_percentage is not None else 0.0
                t_del = float(t.delivery_time_supply) if t.delivery_time_supply is not None else 0.0
                t_bv = float(t.bid_validity_days) if t.bid_validity_days is not None else 90.0
                t_to = float(t.avg_annual_turnover_value) if t.avg_annual_turnover_value is not None else 0.0
                t_age = int(t.technical_eligibility_age) if t.technical_eligibility_age is not None else 0

                t_no = str(t.nit_number).strip() if t.nit_number and str(t.nit_number).strip().lower() not in ("nan", "none", "") else f"TENDER_{t.id}"
                t_name = resolve_tender_title(t.tender_name, t_no)
                t_org = str(t.organization or t.client or t.department or "Unknown Authority").strip()
                if t_org.lower() in ("nan", "none", ""):
                    t_org = "Unknown Authority"

                tenders_data.append({
                    "tender_no": t_no,
                    "tender_name": t_name,
                    "organization": t_org,
                    "department": t.department,
                    "client": t.client,
                    "tender_value": t_val,
                    "emd_amount": t_emd,
                    "pbg_percentage": t_pbg,
                    "pbg_duration": t_dur,
                    "max_ld_percentage": t_ld,
                    "delivery_time_supply": t_del,
                    "bid_validity_days": t_bv,
                    "avg_annual_turnover_value": t_to,
                    "technical_eligibility_age": t_age,
                    "mse_purchase_preference": t.mse_purchase_preference,
                    "mii_purchase_preference": t.mii_purchase_preference,
                    "maf_required": t.maf_required,
                    "reverse_auction_applicable": t.reverse_auction_applicable,
                })
        except Exception as e:
            logger.warning(f"Could not load tenders from Postgres: {e}")

    # 2. Fallback to dataset if DB had no rows or req.source == "dataset"
    if not tenders_data:
        csv_path = STORAGE_ROOT.parent / "artifacts" / "training_set_win_loss.csv"
        if not csv_path.exists():
            csv_path = Path("artifacts/training_set_win_loss.csv")
        if csv_path.exists():
            df_csv = pd.read_csv(csv_path)
            # Replace NaN floats with None before dictionary serialization to prevent NaN leakage
            df_csv = df_csv.where(pd.notna(df_csv), None)
            tenders_data = df_csv.to_dict(orient="records")

    if not tenders_data:
        raise HTTPException(status_code=404, detail="No tender records available for recommendation scoring.")

    # 3. Score and Rank
    result = service.rank_tenders(
        tenders=tenders_data,
        top_k=req.top_k,
        include_groq=req.include_groq
    )

    return result


# =========================================================================
# PQC PAST-PERFORMANCE CREDENTIAL MATCHER ENDPOINT (READ-ONLY)
# =========================================================================
from datetime import date, datetime
from backend.app.models.pqr_credential import PQRCredential
from backend.app.services.pqr_credential_matcher import (
    match_credentials,
    PqcMatchResult,
    CandidateCredential,
    compute_thresholds
)
from backend.app.services.normalizer import parse_money
from backend.app.schemas.pqc_recommendation import (
    MatchedCredentialSchema,
    PQCCredentialRecommendationResponse,
)


_CLASSIFIED_TENDERS_MAP: Optional[Dict[str, str]] = None
_TENDER_ID_TO_NO_MAP: Optional[Dict[str, str]] = None


def _resolve_real_tender_title(tender_id: str, nit_number: Optional[str] = None) -> Optional[str]:
    """
    Resolves human-descriptive tender titles (e.g. 'NHPC NiCd Leh (1)', 'IOCL Precision Chandigarh')
    from classified-tenders.xlsx and training_set_win_loss.csv when database records omit them.
    Cached in memory for sub-millisecond lookup.
    """
    global _CLASSIFIED_TENDERS_MAP, _TENDER_ID_TO_NO_MAP
    if _CLASSIFIED_TENDERS_MAP is None:
        try:
            excel_path = Path("classified-tenders.xlsx")
            if not excel_path.exists():
                excel_path = STORAGE_ROOT.parent / "classified-tenders.xlsx"
            if excel_path.exists():
                df_ex = pd.read_excel(excel_path, usecols=["tender_no", "tender_name"])
                _CLASSIFIED_TENDERS_MAP = dict(zip(
                    df_ex["tender_no"].astype(str).str.strip(),
                    df_ex["tender_name"].astype(str).str.strip()
                ))
            else:
                _CLASSIFIED_TENDERS_MAP = {}
        except Exception:
            _CLASSIFIED_TENDERS_MAP = {}

    if _TENDER_ID_TO_NO_MAP is None:
        try:
            csv_path = Path("artifacts/training_set_win_loss.csv")
            if not csv_path.exists():
                csv_path = STORAGE_ROOT.parent / "artifacts" / "training_set_win_loss.csv"
            if csv_path.exists():
                df_csv = pd.read_csv(csv_path, usecols=["tender_id", "tender_no"])
                _TENDER_ID_TO_NO_MAP = dict(zip(
                    df_csv["tender_id"].astype(str).str.strip(),
                    df_csv["tender_no"].astype(str).str.strip()
                ))
            else:
                _TENDER_ID_TO_NO_MAP = {}
        except Exception:
            _TENDER_ID_TO_NO_MAP = {}

    clean_id = str(tender_id).strip()
    if clean_id in _CLASSIFIED_TENDERS_MAP:
        return _CLASSIFIED_TENDERS_MAP[clean_id]
    if nit_number and str(nit_number).strip() in _CLASSIFIED_TENDERS_MAP:
        return _CLASSIFIED_TENDERS_MAP[str(nit_number).strip()]

    t_no = _TENDER_ID_TO_NO_MAP.get(clean_id)
    if t_no and t_no in _CLASSIFIED_TENDERS_MAP:
        return _CLASSIFIED_TENDERS_MAP[t_no]

    return None


def _fetch_tender_pqc_input(tender_id: str, db: Session) -> dict:
    """
    Fetches tender's estimated value, scope of work, submission deadline,
    and MSME relaxation flag from existing tender data sources with multi-source fallback:
      1. PostgreSQL public.tender_information table (by numeric tender_id, id, or nit_number)
      2. PostgreSQL tender_projects table
      3. Local Workspace storage (STORAGE_ROOT / jobs / {job_id} / tender_detail.json)
      4. Historical training dataset (artifacts/training_set_win_loss.csv)

    Tracks value_is_estimated: True when value had to be inferred via secondary heuristics (e.g. 2% EMD),
    False when directly extracted from the tender's published value fields.
    """
    clean_id = str(tender_id).strip()

    # 1. Check PostgreSQL TenderInformation
    try:
        if clean_id.isdigit():
            int_id = int(clean_id)
            ti = db.query(TenderInformation).filter(
                (TenderInformation.tender_id == int_id) | (TenderInformation.id == int_id)
            ).first()
            if ti:
                t_val = parse_money(ti.tender_value) or parse_money(ti.estimated_cost) or 0.0
                value_is_estimated = False
                if t_val <= 1.0 and ti.emd_amount and float(ti.emd_amount) > 0:
                    t_val = round(float(ti.emd_amount) * 50.0, 2)
                    value_is_estimated = True

                real_title = _resolve_real_tender_title(clean_id, ti.nit_number)
                t_name = real_title or ti.tender_name or f"Tender #{ti.tender_id}"
                t_scope = (
                    real_title
                    or ti.technical_specifications_summary
                    or ti.technical_experience
                    or ti.tender_name
                    or ti.organization
                    or ti.client
                    or "General Procurement"
                )
                t_msme = str(ti.mse_purchase_preference or "").strip().lower() in ("yes", "true", "applicable", "1")
                return {
                    "tender_id": clean_id,
                    "tender_name": t_name,
                    "estimated_value": float(t_val),
                    "value_is_estimated": value_is_estimated,
                    "scope_of_work": str(t_scope).strip(),
                    "submission_deadline": str(ti.bid_submission_end_date) if ti.bid_submission_end_date else None,
                    "msme_relaxation_applicable": t_msme,
                    "data_source": "postgres_tender_information"
                }

        # Query TenderInformation by nit_number string if not a UUID format
        if not ("-" in clean_id and len(clean_id) > 30):
            ti = db.query(TenderInformation).filter(TenderInformation.nit_number == clean_id).first()
            if ti:
                t_val = parse_money(ti.tender_value) or parse_money(ti.estimated_cost) or 0.0
                value_is_estimated = False
                if t_val <= 1.0 and ti.emd_amount and float(ti.emd_amount) > 0:
                    t_val = round(float(ti.emd_amount) * 50.0, 2)
                    value_is_estimated = True

                real_title = _resolve_real_tender_title(clean_id, ti.nit_number)
                t_name = real_title or ti.tender_name or ti.nit_number
                t_scope = (
                    real_title
                    or ti.technical_specifications_summary
                    or ti.technical_experience
                    or ti.tender_name
                    or ti.organization
                    or ti.client
                    or "General Procurement"
                )
                t_msme = str(ti.mse_purchase_preference or "").strip().lower() in ("yes", "true", "applicable", "1")
                return {
                    "tender_id": clean_id,
                    "tender_name": t_name,
                    "estimated_value": float(t_val),
                    "value_is_estimated": value_is_estimated,
                    "scope_of_work": str(t_scope).strip(),
                    "submission_deadline": str(ti.bid_submission_end_date) if ti.bid_submission_end_date else None,
                    "msme_relaxation_applicable": t_msme,
                    "data_source": "postgres_tender_information"
                }
    except Exception as ti_err:
        db.rollback()
        logger.warning(f"Could not query TenderInformation for {clean_id}: {ti_err}")

    # 2. Check PostgreSQL TenderProject
    try:
        proj = db.query(TenderProject).filter(
            (TenderProject.id == clean_id) | (TenderProject.project_id == clean_id)
        ).first()
        if proj:
            ti_proj = db.query(TenderInformation).filter(
                (TenderInformation.tender_name == proj.tender_name)
            ).first()
            if ti_proj:
                t_val = parse_money(ti_proj.tender_value) or parse_money(ti_proj.estimated_cost) or 0.0
                value_is_estimated = False
                if t_val <= 1.0 and ti_proj.emd_amount and float(ti_proj.emd_amount) > 0:
                    t_val = round(float(ti_proj.emd_amount) * 50.0, 2)
                    value_is_estimated = True

                t_scope = (
                    ti_proj.technical_specifications_summary
                    or ti_proj.technical_experience
                    or ti_proj.tender_name
                    or proj.tender_name
                    or "General Procurement"
                )
                t_msme = str(ti_proj.mse_purchase_preference or "").strip().lower() in ("yes", "true", "applicable", "1")
                return {
                    "tender_id": clean_id,
                    "tender_name": proj.tender_name or ti_proj.tender_name,
                    "estimated_value": float(t_val),
                    "value_is_estimated": value_is_estimated,
                    "scope_of_work": str(t_scope).strip(),
                    "submission_deadline": str(ti_proj.bid_submission_end_date) if ti_proj.bid_submission_end_date else None,
                    "msme_relaxation_applicable": t_msme,
                    "data_source": "postgres_tender_project"
                }
    except Exception as proj_err:
        db.rollback()
        logger.warning(f"Could not query TenderProject for {clean_id}: {proj_err}")


    # 3. Check Workspace Jobs (STORAGE_ROOT / jobs / {job_id} / tender_detail.json)
    jobs_dir = STORAGE_ROOT / "jobs"
    target_job_dir = jobs_dir / clean_id
    if not (target_job_dir.exists() and (target_job_dir / "tender_detail.json").exists()):
        matches = [
            p for p in jobs_dir.iterdir()
            if p.is_dir() and p.name.lower().startswith(clean_id.lower()) and (p / "tender_detail.json").exists()
        ]
        if matches:
            target_job_dir = matches[0]

    if target_job_dir.exists() and (target_job_dir / "tender_detail.json").exists():
        try:
            with open(target_job_dir / "tender_detail.json", "r", encoding="utf-8") as f:
                payload = _json.load(f)

            fields = {}
            for sec in payload.get("infoSheetSections", []):
                for fld in sec.get("fields", []):
                    lbl = fld.get("label") or fld.get("id") or ""
                    key = fld.get("key") or ""
                    val = fld.get("value")
                    if lbl:
                        fields[str(lbl)] = val
                    if key:
                        fields[str(key)] = val

            # Direct extraction from published tender value fields
            raw_val = (
                payload.get("tenderValue")
                or fields.get("tender_value_gst_inclusive")
                or fields.get("estimated_cost")
                or fields.get("tender_value")
            )
            val = parse_money(raw_val) or 0.0
            value_is_estimated = False

            # Non-circular secondary derivation:
            # If buyer omitted total estimated value (common on GeM portals), derive via standard 2% EMD heuristic
            # Note: Circular 'order_value_1 / 0.8' is strictly removed to prevent re-deriving input criteria.
            if val == 0.0 and payload.get("emdAmount"):
                emd_f = parse_money(payload.get("emdAmount"))
                if emd_f and emd_f > 0:
                    val = round(emd_f * 50.0, 2)  # Standard 2% EMD multiplier in GeM
                    value_is_estimated = True

            # Derive scope of work
            scope = (
                fields.get("item_category")
                or fields.get("technical_specifications_summary")
                or payload.get("title")
                or fields.get("item")
                or payload.get("sector")
                or "General Procurement"
            )

            deadline = payload.get("deadline") or fields.get("bid_submission_end_date")

            # Derive MSME relaxation flag
            mse_rel = fields.get("mse_relaxation_experience_turnover")
            mse_pref = fields.get("mse_purchase_preference")
            msme_applicable = (
                mse_rel is True
                or str(mse_rel).strip().lower() in ("yes", "true", "applicable", "1", "yes | complete")
                or mse_pref is True
                or str(mse_pref).strip().lower() in ("yes", "true", "applicable", "1")
            )

            return {
                "tender_id": clean_id,
                "tender_name": payload.get("title") or target_job_dir.name,
                "estimated_value": float(val),
                "value_is_estimated": value_is_estimated,
                "scope_of_work": str(scope).strip(),
                "submission_deadline": str(deadline) if deadline else None,
                "msme_relaxation_applicable": bool(msme_applicable),
                "data_source": "workspace_job"
            }
        except Exception as e:
            logger.warning(f"Error reading tender_detail.json for job {clean_id}: {e}")

    # 4. Check historical training set / backtest dataset
    csv_path = STORAGE_ROOT.parent / "artifacts" / "training_set_win_loss.csv"
    if not csv_path.exists():
        csv_path = Path("artifacts/training_set_win_loss.csv")
    if csv_path.exists():
        try:
            df_csv = pd.read_csv(csv_path)
            num_id = int(clean_id) if clean_id.isdigit() else -999999
            matched_rows = df_csv[
                (df_csv["tender_no"].astype(str).str.strip() == clean_id)
                | (df_csv["tender_id"] == num_id)
            ]
            if not matched_rows.empty:
                row = matched_rows.iloc[0]
                val = float(row.get("clean_tender_value") or row.get("tender_value") or 0.0)
                t_name = str(row.get("tender_name") or row.get("tender_no") or clean_id)
                deadline = str(row.get("bid_submission_end_date") or "")
                msme_applicable = str(row.get("mse_purchase_preference") or "").strip().lower() in ("yes", "true", "1")
                is_imputed = bool(row.get("tender_value_imputed", False))
                return {
                    "tender_id": clean_id,
                    "tender_name": resolve_tender_title(t_name, clean_id),
                    "estimated_value": val,
                    "value_is_estimated": is_imputed,
                    "scope_of_work": resolve_tender_title(t_name, clean_id),
                    "submission_deadline": deadline if deadline and deadline.lower() not in ("nan", "nat", "none") else None,
                    "msme_relaxation_applicable": msme_applicable,
                    "data_source": "training_set_archive"
                }
        except Exception as csv_err:
            logger.warning(f"Error searching training_set_win_loss.csv for tender {clean_id}: {csv_err}")

    # If not found in any source
    raise HTTPException(
        status_code=404,
        detail=f"Tender '{clean_id}' not found in database records, workspace jobs, or historical dataset."
    )


@router.get(
    "/{tender_id}/pqc-credentials",
    response_model=PQCCredentialRecommendationResponse,
    summary="Get PQC Past-Performance Credential Recommendation (Read-Only)",
    tags=["pqc", "tenders"]
)
@router.get(
    "/{tender_id}/credentials/recommend",
    response_model=PQCCredentialRecommendationResponse,
    include_in_schema=False
)
def get_pqc_credential_recommendation(
    tender_id: str,
    override_value: Optional[float] = None,
    override_scope: Optional[str] = None,
    override_deadline: Optional[str] = None,
    is_msme: bool = True,
    msme_relaxation: Optional[bool] = None,
    db: Session = Depends(get_db)
) -> PQCCredentialRecommendationResponse:
    """
    Read-only PQC Past-Performance Credential Recommendation Endpoint.

    Fetches that tender's estimated value, scope of work, submission deadline,
    and MSME relaxation flag from existing tender data, loads all candidate records
    from the pqr_credentials table, runs the credential matcher function from Phase 2
    against them, and returns the full structured result as JSON:
      - Qualification status ('QUALIFIED' / 'DISQUALIFIED')
      - Strategy used ('1x80%', '2x50%', '3x40%', 'MSME_RELAXED', 'NO_MATCH')
      - Matched credentials with project name, value, item, category, and document paths
      - Computed thresholds (80%, 50%, 40%, MSME floor)
      - Detailed human-readable rationale text
      - Transparency indicators ('value_is_estimated', 'data_source', 'read_only')

    STRICTLY READ-ONLY: Does not write or mutate any database records or tender fields.
    """
    # 1. Fetch tender input data from existing records
    tender_info = _fetch_tender_pqc_input(tender_id=tender_id, db=db)

    # 2. Allow optional query overrides for human reviewer what-if evaluation
    if override_value is not None:
        estimated_value = float(override_value)
        value_is_estimated = False  # User explicitly specified the value
    else:
        estimated_value = float(tender_info["estimated_value"])
        value_is_estimated = bool(tender_info.get("value_is_estimated", False))

    scope_of_work = str(override_scope).strip() if override_scope is not None else str(tender_info["scope_of_work"])
    submission_deadline = str(override_deadline).strip() if override_deadline is not None else tender_info["submission_deadline"]
    msme_relaxation_applicable = bool(msme_relaxation) if msme_relaxation is not None else bool(tender_info["msme_relaxation_applicable"])

    # 3. Guard against missing or non-positive estimated tender value
    import math
    if estimated_value is None or estimated_value <= 0 or (isinstance(estimated_value, float) and math.isnan(estimated_value)):
        zero_thresholds = compute_thresholds(0.0)
        from backend.app.services.pqr_credential_matcher import normalize_scope
        return PQCCredentialRecommendationResponse(
            tender_id=str(tender_id),
            tender_name=tender_info.get("tender_name"),
            estimated_value=0.0,
            value_is_estimated=False,
            scope_of_work=scope_of_work,
            submission_deadline=str(submission_deadline) if submission_deadline else None,
            msme_relaxation_applicable=msme_relaxation_applicable,
            is_msme_vendor=is_msme,
            qualification_status="CANNOT_EVALUATE",
            qualifies=False,
            strategy_used="VALUE_UNKNOWN",
            matched_credentials=[],
            closest_candidates=[],
            computed_thresholds=zero_thresholds,
            thresholds_required=zero_thresholds,
            rationale=(
                "Tender estimated value could not be determined from published tender documents or EMD heuristics "
                "(estimated value is ₹0.00 or unstated). Statutory past-performance thresholds (1x80%, 2x50%, 3x40%) "
                "cannot be calculated, so PQC qualification cannot be evaluated."
            ),
            target_scope=normalize_scope(scope_of_work),
            eligible_count=0,
            total_candidates_evaluated=0,
            data_source=tender_info.get("data_source", "unknown"),
            read_only=True
        )

    # 4. Load all candidate records from pqr_credentials table
    candidates = db.query(PQRCredential).all()

    # 5. Run pure in-memory credential matcher from Phase 2
    match_result: PqcMatchResult = match_credentials(
        tender_value=estimated_value,
        tender_scope_text=scope_of_work,
        tender_deadline=submission_deadline or date.today(),
        candidates=candidates,
        is_msme=is_msme,
        msme_relaxation_applicable=msme_relaxation_applicable,
    )

    # 6. Map matched and closest credentials to response schema
    matched_schemas: List[MatchedCredentialSchema] = [
        MatchedCredentialSchema(
            id=c.id,
            project_name=c.project_name,
            value=float(c.value),
            item=str(c.item or ""),
            item_category=str(c.item_category or ""),
            completion_date=c.completion_date.isoformat() if c.completion_date else None,
            document_paths=c.document_paths or {}
        )
        for c in (match_result.matched_credentials if match_result.qualifies else [])
    ]

    closest_schemas: List[MatchedCredentialSchema] = [
        MatchedCredentialSchema(
            id=c.id,
            project_name=c.project_name,
            value=float(c.value),
            item=str(c.item or ""),
            item_category=str(c.item_category or ""),
            completion_date=c.completion_date.isoformat() if c.completion_date else None,
            document_paths=c.document_paths or {}
        )
        for c in match_result.closest_candidates
    ]

    # Determine qualification status string
    if match_result.strategy == "VALUE_UNKNOWN":
        qual_status = "CANNOT_EVALUATE"
    else:
        qual_status = "QUALIFIED" if match_result.qualifies else "DISQUALIFIED"

    # 7. Construct and return full structured JSON response
    return PQCCredentialRecommendationResponse(
        tender_id=str(tender_id),
        tender_name=tender_info.get("tender_name"),
        estimated_value=round(estimated_value, 2),
        value_is_estimated=value_is_estimated,
        scope_of_work=scope_of_work,
        submission_deadline=str(submission_deadline) if submission_deadline else None,
        msme_relaxation_applicable=msme_relaxation_applicable,
        is_msme_vendor=is_msme,
        qualification_status=qual_status,
        qualifies=match_result.qualifies,
        strategy_used=match_result.strategy,
        matched_credentials=matched_schemas,
        closest_candidates=closest_schemas,
        computed_thresholds=match_result.thresholds_required,
        thresholds_required=match_result.thresholds_required,
        rationale=match_result.rationale,
        target_scope=match_result.target_scope,
        eligible_count=match_result.eligible_count,
        total_candidates_evaluated=len(candidates),
        data_source=tender_info.get("data_source", "unknown"),
        read_only=True
    )



# =========================================================================
# PQC CREDENTIAL DOCUMENT VIEWER ENDPOINT (READ-ONLY)
# =========================================================================
_ROOT_DIR = Path(".").resolve()
_ALLOWED_PQC_DIRS = [
    (_ROOT_DIR / "pqr-po").resolve(),
    (_ROOT_DIR / "pqr-sap-gem-po").resolve(),
    (_ROOT_DIR / "pqr-completion").resolve(),
    (_ROOT_DIR / "pqr-performance-certificate").resolve(),
    (_ROOT_DIR / "pqr_matched_files" / "pqr-po").resolve(),
    (_ROOT_DIR / "pqr_matched_files" / "pqr-sap-gem-po").resolve(),
    (_ROOT_DIR / "pqr_matched_files" / "pqr-completion").resolve(),
    (_ROOT_DIR / "pqr_matched_files" / "pqr-performance-certificate").resolve(),
]


@router.get(
    "/pqc-documents/view",
    summary="View PQC Credential PDF Document",
    tags=["pqc", "tenders"]
)
def view_pqc_document(path: str):
    """
    Safely serves a PQC credential PDF document given its relative path.
    Enforces boundary containment first against ALLOWED_PQC_DIRS to prevent directory traversal
    and avoid information disclosure via 404 probing.
    """
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Document path cannot be empty")

    clean_rel = path.strip().replace("\\", "/").lstrip("/")

    # 1. Resolve candidate paths against root and pqr_matched_files
    candidate_1 = (_ROOT_DIR / clean_rel).resolve()
    candidate_2 = (_ROOT_DIR / "pqr_matched_files" / clean_rel).resolve()

    # 2. Strict Boundary Enforcement FIRST: must resolve inside ALLOWED_PQC_DIRS
    safe_1 = any(candidate_1.is_relative_to(allowed_dir) for allowed_dir in _ALLOWED_PQC_DIRS)
    safe_2 = any(candidate_2.is_relative_to(allowed_dir) for allowed_dir in _ALLOWED_PQC_DIRS)

    if not safe_1 and not safe_2:
        logger.warning(f"[SECURITY] Directory traversal attempt detected: path={path!r}")
        raise HTTPException(status_code=403, detail="Access denied: path outside permitted document directories")

    # 3. File existence check (only conducted on verified safe paths)
    target_file: Optional[Path] = None
    if safe_1 and candidate_1.is_file():
        target_file = candidate_1
    elif safe_2 and candidate_2.is_file():
        target_file = candidate_2

    if not target_file:
        raise HTTPException(status_code=404, detail="PQC document file not found on disk")

    # 4. Only serve PDF documents
    if target_file.suffix.lower() != ".pdf":
        raise HTTPException(status_code=403, detail="Access denied: only PDF documents may be viewed")

    return FileResponse(
        path=str(target_file),
        media_type="application/pdf",
        filename=target_file.name
    )





