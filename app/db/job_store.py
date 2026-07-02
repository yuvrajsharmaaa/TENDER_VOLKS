import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import time
from typing import Optional, Dict, Any
from shared.constants import DB_PATH, JobStatus

def create_job(job_id: str, filename: str, pdf_path: str, db_path: Path = DB_PATH) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """INSERT INTO jobs (job_id, status, original_filename, pdf_path, created_at) 
               VALUES (?, ?, ?, ?, ?)""",
            (job_id, JobStatus.PENDING, filename, pdf_path, now)
        )

def get_job(job_id: str, db_path: Path = DB_PATH) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
        return None

def update_status(job_id: str, status: JobStatus, error_message: str = None, result_path: str = None, page_count: int = None, db_path: Path = DB_PATH) -> None:
    now = datetime.now(timezone.utc).isoformat()
    
    updates = ["status = ?"]
    params = [status]
    
    if status == JobStatus.PROCESSING:
        updates.append("started_at = ?")
        params.append(now)
    elif status in (JobStatus.COMPLETED, JobStatus.FAILED):
        updates.append("completed_at = ?")
        params.append(now)
        
    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)
        
    if result_path is not None:
        updates.append("result_path = ?")
        params.append(result_path)
        
    if page_count is not None:
        updates.append("page_count = ?")
        params.append(page_count)
        
    params.append(job_id)
    query = f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?"
    
    # Simple retry mechanism for WAL mode locks
    for i in range(3):
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(query, tuple(params))
                break
        except sqlite3.OperationalError as e:
            if i == 2:
                raise e
            time.sleep(1)

def update_result(job_id: str, result_path: str, page_count: int, db_path: Path = DB_PATH) -> None:
    update_status(job_id, JobStatus.COMPLETED, result_path=result_path, page_count=page_count, db_path=db_path)
