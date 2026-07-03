from pathlib import Path
from backend.app.repositories.job_store import update_status
from ocr.pipeline import process_pdf
from backend.app.core.constants import JobStatus

def run_ocr_job(job_id: str, pdf_path: Path, run_layoutlm: bool = False) -> None:
    try:
        update_status(job_id, JobStatus.PROCESSING)
        page_results = process_pdf(job_id=job_id, pdf_path=pdf_path, run_layoutlm=run_layoutlm)

        result_path = str(pdf_path.parent / "ocr_result.json")
        update_status(job_id, JobStatus.COMPLETED, result_path=result_path)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        update_status(job_id, JobStatus.FAILED, error_message=error_msg)
