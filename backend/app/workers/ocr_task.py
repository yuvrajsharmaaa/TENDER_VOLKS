import json
import logging
from pathlib import Path
from backend.app.repositories.job_store import update_status
from backend.app.core.constants import JobStatus, STORAGE_ROOT
from ocr.pipeline import process_pdf
from backend.app.services.tender_mapper import map_occurrences_to_tender_payloads
from backend.app.services.tender_repository import save_tender_information
from backend.app.services.export_service import export_page_aware_tender_sheets
from backend.app.services.email_service import send_email_with_attachments
from backend.app.db.session import SessionLocal

logger = logging.getLogger(__name__)

def run_ocr_job(job_id: str, pdf_path: Path, run_layoutlm: bool = False) -> None:
    """Legacy compatibility worker."""
    try:
        update_status(job_id, JobStatus.PROCESSING)
        page_results = process_pdf(job_id=job_id, pdf_path=pdf_path, run_layoutlm=run_layoutlm)
        result_path = str(pdf_path.parent / "ocr_result.json")
        update_status(job_id, JobStatus.COMPLETED, result_path=result_path)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        update_status(job_id, JobStatus.FAILED, error_message=error_msg)

def run_automated_tender_pipeline(job_id: str, tender_id: int, email_recipient: str) -> None:
    """
    Automated background worker.
    Runs OCR, extracts fields, resolves occurrences, writes database payload,
    exports summary/evidence sheets, and emails results.
    """
    try:
        # 1. Update job status to processing
        update_status(job_id, JobStatus.PROCESSING)
        
        # 2. Get original PDF path
        job_dir = STORAGE_ROOT / "jobs" / job_id
        pdf_path = job_dir / "original.pdf"
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"Original PDF not found at {pdf_path}")
            
        # 3. Run OCR and deterministic field extraction
        logger.info(f"Starting OCR and extraction for job_id {job_id}")
        # This will write extracted_fields.json inside the job directory
        process_pdf(job_id=job_id, pdf_path=pdf_path)
        
        # 4. Load the extracted fields
        extracted_fields_path = job_dir / "extracted_fields.json"
        if not extracted_fields_path.exists():
            raise FileNotFoundError(f"Extracted fields file not found at {extracted_fields_path}")
            
        with open(extracted_fields_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
        # 5. Convert OCR extracted format to flat occurrences list
        extracted_fields = raw_data.get("extracted_fields", []) if isinstance(raw_data, dict) else raw_data
        occurrences = []
        for field in extracted_fields:
            occurrences.append({
                "field_name": field.get("field_name"),
                "value_raw": field.get("value"),
                "page": field.get("source_page", 1),
                "confidence": field.get("confidence", 1.0),
                "text_snippet": field.get("evidence", "")
            })
            
        # 6. Map occurrences using page-aware scoring resolver
        logger.info(f"Resolving occurrences and mapping DB payload for tender_id {tender_id}")
        db_payload, evidence_rows = map_occurrences_to_tender_payloads(occurrences, tender_id)
        
        # 7. Write payload to PostgreSQL database using SQLAlchemy session
        db = SessionLocal()
        try:
            saved_row = save_tender_information(db, db_payload)
            db.commit()
        except Exception as db_err:
            db.rollback()
            raise db_err
        finally:
            db.close()
            
        # 8. Export Layer 1 (Summary) and Layer 2 (Evidence) CSV reports
        logger.info("Exporting summary and evidence CSV reports")
        summary_csv_path, evidence_csv_path = export_page_aware_tender_sheets(
            summary_row=saved_row,
            evidence_rows=evidence_rows,
            output_dir=str(job_dir)
        )
        
        # 9. Send email with attachments
        logger.info(f"Sending email notification to {email_recipient}")
        subject = f"Processed Tender results for ID: {tender_id}"
        body = (
            f"Hello,\n\n"
            f"Please find attached the row-level summary CSV and the auditing evidence CSV for Tender ID: {tender_id}.\n\n"
            f"Regards,\n"
            f"Tender Volks Engine\n"
        )
        send_email_with_attachments(
            to_email=email_recipient,
            subject=subject,
            body=body,
            file_paths=[summary_csv_path, evidence_csv_path]
        )
        
        # 10. Update job status to completed
        result_path = str(extracted_fields_path)
        update_status(job_id, JobStatus.COMPLETED, result_path=result_path)
        logger.info(f"Automated pipeline completed successfully for job_id {job_id}")
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Automated pipeline failed for job_id {job_id}: {e}", exc_info=True)
        update_status(job_id, JobStatus.FAILED, error_message=error_msg)
