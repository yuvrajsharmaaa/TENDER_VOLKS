import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db.session import get_db

client = TestClient(app)

def test_force_reprocess_flow():
    mock_db = MagicMock()
    
    mock_project = MagicMock()
    mock_project.id = "proj-reprocess-test"
    
    mock_doc = MagicMock()
    mock_doc.id = "doc-reprocess-test"
    mock_doc.tender_project_id = "proj-reprocess-test"
    mock_doc.processing_status = "pending"
    mock_doc.file_path = "sample_files/GeM-Bidding-7724454.pdf_1748685463_3605671.pdf"
    mock_doc.file_type = "tender_pdf"

    def query_side_effect(model):
        q_mock = MagicMock()
        model_name = getattr(model, "__name__", str(model))
        if "TenderProject" in model_name:
            q_mock.filter.return_value.first.return_value = mock_project
        else:
            q_mock.filter.return_value.first.return_value = mock_doc
        return q_mock

    mock_db.query.side_effect = query_side_effect
    app.dependency_overrides[get_db] = lambda: mock_db

    # 1. First processing call when pending -> 200 OK
    res1 = client.post("/tenders/proj-reprocess-test/documents/doc-reprocess-test/process")
    assert res1.status_code == 200, res1.json()
    assert res1.json()["processing_status"] == "processing"

    # Simulate completed status
    mock_doc.processing_status = "completed"

    # 2. Second call without force_reprocess -> 400 already_completed
    res2 = client.post("/tenders/proj-reprocess-test/documents/doc-reprocess-test/process")
    assert res2.status_code == 400
    assert res2.json()["detail"]["error"] == "already_completed"

    # 3. Third call with force_reprocess=true -> 200 OK
    res3 = client.post("/tenders/proj-reprocess-test/documents/doc-reprocess-test/process?force_reprocess=true")
    assert res3.status_code == 200, res3.json()
    assert res3.json()["processing_status"] == "processing"

    app.dependency_overrides.clear()
