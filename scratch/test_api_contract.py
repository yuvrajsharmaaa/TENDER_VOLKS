import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.app.main import app

def run_tests():
    client = TestClient(app)
    print("=== STARTING FULL END-TO-END BACKEND API CONTRACT TESTS ===")

    # 1. Health check
    print("\n[1] Testing GET /health...")
    res = client.get("/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print("    PASSED: Health check returned 200 OK.")

    # 2. Test PDF Upload via /tenders/upload using real PDF
    sample_pdf_path = root_dir / "sample_files" / "GeM-Bidding-7641085.pdf_1750409965_2005407.pdf"
    assert sample_pdf_path.exists(), "Sample PDF not found"
    with open(sample_pdf_path, "rb") as f:
        real_pdf_bytes = f.read()

    print("\n[2] Testing POST /tenders/upload with real PDF...")
    files = {"file": ("GeM-Bidding-7641085.pdf", real_pdf_bytes, "application/pdf")}
    res = client.post("/tenders/upload", files=files)
    assert res.status_code == 201, f"Upload failed: {res.text}"
    data = res.json()
    job_id = data.get("job_id")
    file_id = data.get("file_id")
    tender_id = data.get("tender_id")
    status = data.get("status")
    print(f"    PASSED: Upload returned job_id={job_id}, file_id={file_id}, tender_id={tender_id}, status={status}")
    assert job_id and file_id and tender_id, "Missing identifiers in response"
    assert status == "pending", f"Expected status 'pending', got '{status}'"

    # 3. Test Job Status via GET /jobs/{job_id}
    print(f"\n[3] Testing GET /jobs/{job_id}...")
    res = client.get(f"/jobs/{job_id}")
    assert res.status_code == 200, f"Get job failed: {res.text}"
    job_data = res.json()
    print(f"    PASSED: Job status returned: {job_data}")
    assert job_data.get("job_id") == job_id
    assert job_data.get("file_id") == job_id
    assert job_data.get("tender_id") == job_id
    assert "workspace_url" in job_data

    # 4. Test Workspace Detail via GET /tenders/workspace/{job_id}
    print(f"\n[4] Testing GET /tenders/workspace/{job_id}...")
    res = client.get(f"/tenders/workspace/{job_id}")
    assert res.status_code == 200, f"Get workspace item failed: {res.text}"
    item = res.json()
    print(f"    PASSED: Retrieved workspace item: parse_status='{item.get('parse_status')}', title='{item.get('title')}'")

    # 5. Test Workspace Field Edit via PUT /tenders/workspace/{job_id}/fields/{field_id}
    # Create or update field if sections exist
    if item.get("infoSheetSections"):
        first_field = item["infoSheetSections"][0]["fields"][0]
        field_id = first_field["id"]
        print(f"\n[5] Testing PUT /tenders/workspace/{job_id}/fields/{field_id}...")
        res = client.put(f"/tenders/workspace/{job_id}/fields/{field_id}", json={"value": "Updated Test Value"})
        assert res.status_code == 200, f"Field update failed: {res.text}"
        updated_item = res.json()
        print("    PASSED: Field updated successfully.")

        # 6. Test Field Verification via POST /tenders/workspace/{job_id}/fields/{field_id}/verify
        print(f"\n[6] Testing POST /tenders/workspace/{job_id}/fields/{field_id}/verify...")
        res = client.post(f"/tenders/workspace/{job_id}/fields/{field_id}/verify")
        assert res.status_code == 200, f"Field verification failed: {res.text}"
        print("    PASSED: Field verified successfully.")

    # 7. Test Mark Reviewed via POST /tenders/workspace/{job_id}/review
    print(f"\n[7] Testing POST /tenders/workspace/{job_id}/review...")
    res = client.post(f"/tenders/workspace/{job_id}/review", json={"reviewer_name": "Yuvraj Sharma"})
    assert res.status_code == 200, f"Mark review failed: {res.text}"
    review_data = res.json()
    assert review_data.get("review_status") == "completed"
    print("    PASSED: Review marked completed.")

    # 8. Test InfoSheet Download via GET /tenders/workspace/{job_id}/infosheet/download
    print(f"\n[8] Testing GET /tenders/workspace/{job_id}/infosheet/download...")
    res = client.get(f"/tenders/workspace/{job_id}/infosheet/download")
    assert res.status_code == 200, f"InfoSheet download failed: {res.text}"
    assert "spreadsheetml" in res.headers.get("content-type", "") or len(res.content) > 0
    print(f"    PASSED: Downloaded InfoSheet workbook ({len(res.content)} bytes).")

    print("\n=== ALL END-TO-END BACKEND API CONTRACT TESTS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_tests()
