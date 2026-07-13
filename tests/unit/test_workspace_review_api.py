import pytest
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.constants import STORAGE_ROOT

client = TestClient(app)

@pytest.fixture
def mock_tender_detail():
    job_id = "test-job-uuid-review"
    job_dir = STORAGE_ROOT / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    detail_file = job_dir / "tender_detail.json"
    
    mock_data = {
        "id": job_id,
        "title": "Test Tender Title",
        "authorityName": "Test Authority",
        "deadline": "2026-07-28T17:00:00Z",
        "tenderValue": "10.00 Lakh",
        "emdAmount": "20.00 Thousand",
        "tenderFee": "NA",
        "location": "Delhi",
        "documents": {
            "sourceDocuments": [
                {
                    "id": f"src-{job_id}",
                    "name": "original.pdf",
                    "kind": "pdf",
                    "origin": "source",
                    "isPrimary": True
                }
            ],
            "generatedOutputs": [],
            "extractedLinkedPdfs": [],
            "mentionedAttachments": []
        },
        "infoSheetSections": [
            {
                "id": "sec-1",
                "title": "Basic Information",
                "fields": [
                    {
                        "id": "f-1",
                        "label": "Tender Name / Title",
                        "value": "Test Tender Title",
                        "confidence": 95.0,
                        "critical": True,
                        "status": "extracted"
                    },
                    {
                        "id": "f-2",
                        "label": "Estimated Tender Value",
                        "value": "10.00 Lakh",
                        "confidence": 50.0,
                        "critical": True,
                        "status": "extracted"
                    }
                ]
            }
        ],
        "rawTextPages": [{"page": 1, "text": "Test Tender Title"}],
        "parse_status": "completed",
        "parse_confidence": 90.0,
        "review_status": "unreviewed",
        "issues_count": 1
    }
    
    with open(detail_file, "w", encoding="utf-8") as f:
        json.dump(mock_data, f, indent=2)
        
    yield job_id, detail_file
    
    # Cleanup
    if detail_file.exists():
        detail_file.unlink()
    xlsx_file = job_dir / "original_InfoSheet.xlsx"
    if xlsx_file.exists():
        xlsx_file.unlink()
    if job_dir.exists():
        try:
            job_dir.rmdir()
        except Exception:
            pass

def test_update_workspace_field(mock_tender_detail):
    job_id, detail_file = mock_tender_detail
    
    response = client.put(
        f"/tenders/workspace/{job_id}/fields/f-2",
        json={"value": "12.00 Lakh"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["issues_count"] == 0
    
    field = data["infoSheetSections"][0]["fields"][1]
    assert field["value"] == "12.00 Lakh"
    assert field["status"] == "edited"
    
    xlsx_path = detail_file.parent / "original_InfoSheet.xlsx"
    assert xlsx_path.exists()

def test_verify_workspace_field(mock_tender_detail):
    job_id, detail_file = mock_tender_detail
    
    response = client.post(
        f"/tenders/workspace/{job_id}/fields/f-2/verify"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["issues_count"] == 0
    
    field = data["infoSheetSections"][0]["fields"][1]
    assert field["status"] == "verified"
    
    xlsx_path = detail_file.parent / "original_InfoSheet.xlsx"
    assert xlsx_path.exists()

def test_review_workspace_tender(mock_tender_detail):
    job_id, detail_file = mock_tender_detail
    
    response = client.post(
        f"/tenders/workspace/{job_id}/review",
        json={"reviewer_name": "Test Reviewer"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["review_status"] == "completed"
    assert data["reviewer_name"] == "Test Reviewer"
    assert data["issues_count"] == 0
    
    for sec in data["infoSheetSections"]:
        for f in sec["fields"]:
            assert f["status"] == "verified"
            
    xlsx_path = detail_file.parent / "original_InfoSheet.xlsx"
    assert xlsx_path.exists()
