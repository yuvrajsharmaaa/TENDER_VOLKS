import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from backend.app.main import app
from backend.app.services.storage import StorageError
from backend.app.db.session import get_db

client = TestClient(app)

# Reset overrides before each test
@pytest.fixture(autouse=True)
def cleanup_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()

def test_upload_tender_success():
    """
    Verifies that uploading a valid PDF returns the generated file ID
    and the original filename with HTTP 200.
    """
    file_content = b"%PDF-1.4 Mock PDF Content"
    mock_file_id = "test-uuid-1234-5678"
    
    with patch("backend.app.api.routes.tenders.upload_file_to_minio") as mock_upload:
        mock_upload.return_value = mock_file_id
        
        response = client.post(
            "/tenders/upload",
            files={"file": ("tender.pdf", file_content, "application/pdf")}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["file_id"] == mock_file_id
        assert data["original_filename"] == "tender.pdf"
        
        # Verify mock was called with correct arguments
        mock_upload.assert_called_once_with(file_content, "application/pdf", "tender.pdf")

def test_upload_tender_missing_file():
    """
    Verifies that uploading an empty or missing filename triggers HTTP 400.
    """
    # Empty filename
    response = client.post(
        "/tenders/upload",
        files={"file": ("", b"", "application/pdf")}
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "no_file"
    assert "required" in data["detail"]["message"]

def test_upload_tender_invalid_type():
    """
    Verifies that uploading a non-PDF file type triggers HTTP 400.
    """
    response = client.post(
        "/tenders/upload",
        files={"file": ("tender.txt", b"Plain text content", "text/plain")}
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "invalid_type"
    assert "Only PDF files" in data["detail"]["message"]
    assert data["detail"]["received"] == "text/plain"

def test_upload_tender_empty_file():
    """
    Verifies that uploading an empty PDF (0 bytes) triggers HTTP 400.
    """
    response = client.post(
        "/tenders/upload",
        files={"file": ("empty.pdf", b"", "application/pdf")}
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "empty_file"
    assert "empty" in data["detail"]["message"]

def test_upload_tender_storage_failure():
    """
    Verifies that a StorageError from the storage layer results in HTTP 500.
    """
    file_content = b"%PDF-1.4 Mock PDF Content"
    
    with patch("backend.app.api.routes.tenders.upload_file_to_minio") as mock_upload:
        mock_upload.side_effect = StorageError("MinIO upload connection failure")
        
        response = client.post(
            "/tenders/upload",
            files={"file": ("tender.pdf", file_content, "application/pdf")}
        )
        
        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["error"] == "storage_failure"
        assert "store file" in data["detail"]["message"]

# New Tenders linked multi-document upload test cases
def test_create_tender_success():
    """
    Verifies successful creation of a tender project.
    """
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    response = client.post(
        "/tenders",
        json={
            "project_id": "proj-123",
            "tender_name": "Test Tender",
            "source_label": "NIT"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == "proj-123"
    assert data["tender_name"] == "Test Tender"
    assert "tender_project_id" in data
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()

def test_get_tender_details_success():
    """
    Verifies successful retrieval of tender details and documents.
    """
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_project = MagicMock()
    mock_project.id = "tender-uuid"
    mock_project.project_id = "proj-123"
    mock_project.tender_name = "Test Tender"
    mock_project.source_label = "NIT"
    mock_project.created_at = "2026-07-06T10:00:00"
    mock_project.updated_at = "2026-07-06T10:00:00"
    
    mock_doc = MagicMock()
    mock_doc.id = "doc-uuid"
    mock_doc.original_filename = "nit.pdf"
    mock_doc.mime_type = "application/pdf"
    mock_doc.size_bytes = 500
    mock_doc.upload_status = "uploaded"
    mock_doc.processing_status = "pending"
    mock_doc.document_type = "NIT"
    
    mock_project.documents = [mock_doc]
    mock_db.query().filter().first.return_value = mock_project
    
    response = client.get("/tenders/tender-uuid")
    assert response.status_code == 200
    data = response.json()
    assert data["tender_project_id"] == "tender-uuid"
    assert len(data["documents"]) == 1
    assert data["documents"][0]["document_id"] == "doc-uuid"
    assert data["documents"][0]["original_filename"] == "nit.pdf"

def test_get_tender_details_not_found():
    """
    Verifies 404 if tender project does not exist.
    """
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    mock_db.query().filter().first.return_value = None
    
    response = client.get("/tenders/non-existent-uuid")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "not_found"

def test_upload_tender_documents_success():
    """
    Verifies multi-document upload and database schema persistence.
    """
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_project = MagicMock()
    mock_project.id = "tender-uuid"
    mock_project.project_id = "proj-123"
    mock_db.query().filter().first.return_value = mock_project
    
    file1_content = b"%PDF-1.4 Mock PDF Content"
    file2_content = b"Mock PNG Content"
    
    with patch("backend.app.api.routes.tenders.upload_file_to_minio") as mock_upload:
        response = client.post(
            "/tenders/tender-uuid/documents",
            data={"document_type": "NIT"},
            files=[
                ("files", ("nit.pdf", file1_content, "application/pdf")),
                ("files", ("image.png", file2_content, "image/png"))
            ]
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tender_project_id"] == "tender-uuid"
        assert len(data["documents"]) == 2
        assert len(data["failed"]) == 0
        assert data["documents"][0]["original_filename"] == "nit.pdf"
        assert data["documents"][1]["original_filename"] == "image.png"
        assert mock_upload.call_count == 2
        assert mock_db.add.call_count == 2

def test_upload_tender_documents_partial_failure():
    """
    Verifies partial failure when some files are invalid content types.
    """
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_project = MagicMock()
    mock_project.id = "tender-uuid"
    mock_project.project_id = "proj-123"
    mock_db.query().filter().first.return_value = mock_project
    
    file1_content = b"%PDF-1.4 Mock PDF Content"
    
    with patch("backend.app.api.routes.tenders.upload_file_to_minio") as mock_upload:
        response = client.post(
            "/tenders/tender-uuid/documents",
            files=[
                ("files", ("nit.pdf", file1_content, "application/pdf")),
                ("files", ("bad.exe", b"executable bytes", "application/octet-stream"))
            ]
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["documents"]) == 1
        assert len(data["failed"]) == 1
        assert data["documents"][0]["original_filename"] == "nit.pdf"
        assert data["failed"][0]["filename"] == "bad.exe"
        assert data["failed"][0]["error"] == "invalid_type"
        assert mock_upload.call_count == 1


def test_process_tender_document_success():
    """
    Verifies that calling process on a pending document returns 200
    and triggers the background worker task.
    """
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_project = MagicMock()
    mock_project.id = "tender-uuid"
    
    mock_doc = MagicMock()
    mock_doc.id = "doc-uuid"
    mock_doc.tender_project_id = "tender-uuid"
    mock_doc.processing_status = "pending"
    
    # Configure DB query mock to return project and doc
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_project, mock_doc]
    
    with patch("backend.app.api.routes.tenders.background_ocr_worker") as mock_worker:
        response = client.post(
            "/tenders/tender-uuid/documents/doc-uuid/process",
            params={"run_layoutlm": True}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "doc-uuid"
        assert data["processing_status"] == "processing"
        assert mock_doc.processing_status == "processing"
        assert mock_db.commit.call_count == 1
        
        # Verify background worker was queued
        mock_worker.assert_called_once_with("doc-uuid", True)


def test_process_tender_document_not_found_tender():
    """
    Verifies 404 is returned if the tender project does not exist.
    """
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    response = client.post("/tenders/tender-missing/documents/doc-uuid/process")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"] == "not_found"
    assert "Tender Project with ID" in data["detail"]["message"]


def test_process_tender_document_not_found_document():
    """
    Verifies 404 is returned if the document does not exist or is not linked.
    """
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_project = MagicMock()
    mock_project.id = "tender-uuid"
    
    # First query (project) returns mock_project, second query (doc) returns None
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_project, None]
    
    response = client.post("/tenders/tender-uuid/documents/doc-missing/process")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"] == "not_found"
    assert "Document with ID" in data["detail"]["message"]


def test_process_tender_document_conflict_processing():
    """
    Verifies 409 is returned if the document is already processing.
    """
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_project = MagicMock()
    mock_project.id = "tender-uuid"
    
    mock_doc = MagicMock()
    mock_doc.id = "doc-uuid"
    mock_doc.tender_project_id = "tender-uuid"
    mock_doc.processing_status = "processing"
    
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_project, mock_doc]
    
    response = client.post("/tenders/tender-uuid/documents/doc-uuid/process")
    assert response.status_code == 409
    data = response.json()
    assert data["detail"]["error"] == "already_processing"


def test_process_tender_document_bad_request_completed():
    """
    Verifies 400 is returned if the document has already completed processing.
    """
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_project = MagicMock()
    mock_project.id = "tender-uuid"
    
    mock_doc = MagicMock()
    mock_doc.id = "doc-uuid"
    mock_doc.tender_project_id = "tender-uuid"
    mock_doc.processing_status = "completed"
    
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_project, mock_doc]
    
    response = client.post("/tenders/tender-uuid/documents/doc-uuid/process")
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "already_completed"

