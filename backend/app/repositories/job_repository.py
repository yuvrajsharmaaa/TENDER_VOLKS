from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union
from sqlalchemy.orm import Session
from backend.app.db.session import SessionLocal
from backend.app.models.job import Job
from backend.app.core.constants import JobStatus

def _get_session(db: Optional[Session] = None):
    """Context manager or session provider helper."""
    if db is not None:
        return db, False
    return SessionLocal(), True

def _job_to_dict(job: Job) -> Dict[str, Any]:
    """Convert a Job SQLAlchemy instance to a dict matching the repository contract."""
    return {
        "job_id": job.job_id,
        "status": job.status,
        "original_filename": job.original_filename or (job.file_path.split("/")[-1] if job.file_path else "original.pdf"),
        "pdf_path": job.pdf_path or job.file_path,
        "file_path": job.file_path or job.pdf_path,
        "result_path": job.result_path,
        "page_count": job.page_count,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "retry_count": job.retry_count,
        "email_recipient": job.email_recipient,
        "tender_id": job.tender_id,
    }

def create_job(
    job_id: str,
    filename: str,
    pdf_path: str,
    status: Union[JobStatus, str] = JobStatus.QUEUED,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """Creates or updates a Job record in PostgreSQL."""
    session, should_close = _get_session(db)
    try:
        now = datetime.now(timezone.utc)
        status_val = status.value if hasattr(status, "value") else str(status)
        job = session.query(Job).filter(Job.job_id == job_id).first()
        if job:
            job.status = status_val
            job.original_filename = filename
            job.pdf_path = pdf_path
            job.file_path = pdf_path
            job.updated_at = now
        else:
            job = Job(
                job_id=job_id,
                status=status_val,
                original_filename=filename,
                pdf_path=pdf_path,
                file_path=pdf_path,
                created_at=now,
                updated_at=now,
                retry_count=0
            )
            session.add(job)
        session.commit()
        session.refresh(job)
        return _job_to_dict(job)
    except Exception:
        session.rollback()
        raise
    finally:
        if should_close:
            session.close()


def get_job(job_id: str, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
    """Retrieves a Job record by job_id from PostgreSQL."""
    session, should_close = _get_session(db)
    try:
        job = session.query(Job).filter(Job.job_id == job_id).first()
        if job:
            return _job_to_dict(job)
        return None
    finally:
        if should_close:
            session.close()

def update_status(
    job_id: str,
    status: Union[JobStatus, str],
    error_message: Optional[str] = None,
    result_path: Optional[str] = None,
    page_count: Optional[int] = None,
    db: Optional[Session] = None
) -> None:
    """Updates the status and related lifecycle fields for a job in PostgreSQL."""
    session, should_close = _get_session(db)
    try:
        job = session.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            return
        
        status_val = status.value if hasattr(status, "value") else str(status)
        job.status = status_val
        now = datetime.now(timezone.utc)
        job.updated_at = now
        
        if status_val == JobStatus.PROCESSING.value:
            job.started_at = now
        elif status_val in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
            job.completed_at = now
            
        if error_message is not None:
            job.error_message = error_message
        if result_path is not None:
            job.result_path = result_path
        if page_count is not None:
            job.page_count = page_count
            
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if should_close:
            session.close()

def update_job_parameters(
    job_id: str,
    email_recipient: str,
    tender_id: Any,
    db: Optional[Session] = None
) -> None:
    """Updates the email_recipient and tender_id for a job in PostgreSQL."""
    session, should_close = _get_session(db)
    try:
        job = session.query(Job).filter(Job.job_id == job_id).first()
        if job:
            job.email_recipient = str(email_recipient) if email_recipient is not None else None
            job.tender_id = str(tender_id) if tender_id is not None else None
            job.updated_at = datetime.now(timezone.utc)
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if should_close:
            session.close()

def update_result(
    job_id: str,
    result_path: str,
    page_count: int,
    db: Optional[Session] = None
) -> None:
    """Updates a job to COMPLETED with result_path and page_count."""
    update_status(
        job_id=job_id,
        status=JobStatus.COMPLETED,
        result_path=result_path,
        page_count=page_count,
        db=db
    )

def get_all_jobs(db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Retrieves all jobs ordered by created_at descending from PostgreSQL."""
    session, should_close = _get_session(db)
    try:
        jobs = session.query(Job).order_by(Job.created_at.desc()).all()
        return [_job_to_dict(j) for j in jobs]
    finally:
        if should_close:
            session.close()

def delete_job(job_id: str, db: Optional[Session] = None) -> None:
    """Deletes a job from PostgreSQL by job_id."""
    session, should_close = _get_session(db)
    try:
        job = session.query(Job).filter(Job.job_id == job_id).first()
        if job:
            session.delete(job)
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if should_close:
            session.close()
