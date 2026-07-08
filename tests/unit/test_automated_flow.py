import pytest
import sqlite3
from fastapi.testclient import TestClient
from unittest.mock import patch
from backend.app.main import app
from backend.app.repositories.job_store import create_job, get_job
from backend.app.core.constants import DB_PATH

client = TestClient(app)

@pytest.fixture(autouse=True)
def cleanup_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()

@pytest.fixture
def cleanup_jobs():
    created_ids = []
    yield created_ids
    # Cleanup DB after test runs
    with sqlite3.connect(DB_PATH) as conn:
        for jid in created_ids:
            conn.execute("DELETE FROM jobs WHERE job_id = ?", (jid,))

def test_automated_upload_success(cleanup_jobs):
    """
    Verifies that uploading a PDF returns a PENDING job ID and saves to SQLite.
    """
    file_content = b"%PDF-1.4 Mock PDF Content"
    
    response = client.post(
        "/tenders/upload",
        files={"file": ("test_tender.pdf", file_content, "application/pdf")}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    
    cleanup_jobs.append(data["job_id"])
    
    # Verify job is present in DB
    job = get_job(data["job_id"])
    assert job is not None
    assert job["status"] == "pending"

def test_automated_process_success(cleanup_jobs):
    """
    Verifies that triggering process sets status and launches background worker.
    """
    job_id = "test-job-uuid-process"
    create_job(job_id, "test_tender.pdf", "mock_pdf_path.pdf")
    cleanup_jobs.append(job_id)
    
    with patch("backend.app.api.upload.run_automated_tender_pipeline") as mock_worker:
        response = client.post(
            "/tenders/process",
            json={
                "job_id": job_id,
                "email_recipient": "auditor@example.com",
                "tender_id": 99
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "processing"
        
        mock_worker.assert_called_once()

def test_jobs_status_api():
    with patch("backend.app.api.jobs.get_job") as mock_get:
        mock_get.return_value = {
            "job_id": "test-job-uuid",
            "status": "pending",
            "original_filename": "tender.pdf"
        }
        
        response = client.get("/jobs/test-job-uuid")
        assert response.status_code == 200
        assert response.json()["status"] == "pending"

def test_jobs_download_api(tmp_path):
    with patch("backend.app.api.jobs.get_job") as mock_get, \
         patch("backend.app.api.jobs.STORAGE_ROOT", tmp_path):
         
        mock_get.return_value = {
            "job_id": "test-job-uuid",
            "status": "completed",
            "tender_id": 99
        }
        
        csv_dir = tmp_path / "jobs" / "test-job-uuid"
        csv_dir.mkdir(parents=True, exist_ok=True)
        csv_file = csv_dir / "tender_99_export.csv"
        csv_file.write_text("header1,header2\nval1,val2")
        
        response = client.get("/jobs/test-job-uuid/download?format=summary")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        # Normalize CRLF to LF for cross-platform matching
        content_normalized = response.content.replace(b"\r\n", b"\n")
        assert content_normalized == b"header1,header2\nval1,val2"
