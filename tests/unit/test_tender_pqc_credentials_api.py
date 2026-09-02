import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_pqc_credentials_endpoint_workspace_job():
    """
    Tests GET /tenders/{tender_id}/pqc-credentials against a real workspace job.
    Verifies full structured response conforms to standard schema and flags value_is_estimated.
    """
    tender_id = "43474eaf-b191-4dab-aacb-4465917bf45d"
    resp = client.get(f"/tenders/{tender_id}/pqc-credentials")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    data = resp.json()
    assert data["tender_id"] == tender_id
    assert data["read_only"] is True
    assert data["value_is_estimated"] is True  # Derived via 2% EMD heuristic since GeM PDF omitted direct tender value
    assert data["qualification_status"] in ("QUALIFIED", "DISQUALIFIED")
    assert isinstance(data["qualifies"], bool)
    assert data["strategy_used"] in ("1x80%", "2x50%", "3x40%", "MSME_RELAXED", "NO_MATCH")
    assert isinstance(data["matched_credentials"], list)
    assert isinstance(data["computed_thresholds"], dict)
    assert "eighty_pct" in data["computed_thresholds"]
    assert "fifty_pct" in data["computed_thresholds"]
    assert "forty_pct" in data["computed_thresholds"]
    assert "msme_floor" in data["computed_thresholds"]
    assert isinstance(data["rationale"], str) and len(data["rationale"]) > 0

    if data["matched_credentials"]:
        first = data["matched_credentials"][0]
        assert "project_name" in first
        assert "value" in first
        assert "document_paths" in first
        assert isinstance(first["document_paths"], dict)


def test_pqc_credentials_endpoint_db_record():
    """
    Tests GET /tenders/{tender_id}/pqc-credentials against a real PostgreSQL tender_information ID.
    Verifies value_is_estimated is False when value was extracted directly from real tender data.
    """
    tender_id = "65"
    resp = client.get(f"/tenders/{tender_id}/pqc-credentials")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    data = resp.json()
    assert data["tender_id"] == tender_id
    assert data["data_source"] == "postgres_tender_information"
    assert data["estimated_value"] == 13572398.0
    assert data["value_is_estimated"] is False  # Directly extracted from real DB record
    assert data["read_only"] is True


def test_pqc_credentials_endpoint_alias():
    """
    Tests alias route GET /tenders/{tender_id}/credentials/recommend returns identical payload.
    """
    tender_id = "43474eaf-b191-4dab-aacb-4465917bf45d"
    resp = client.get(f"/tenders/{tender_id}/credentials/recommend")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tender_id"] == tender_id
    assert data["read_only"] is True


def test_pqc_credentials_endpoint_404():
    """
    Tests non-existent tender ID cleanly returns 404 with structured error message.
    """
    resp = client.get("/tenders/non-existent-tender-uuid-00000000/pqc-credentials")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_pqc_credentials_endpoint_query_overrides():
    """
    Tests optional human what-if review query parameters (value, scope, msme).
    Verifies value_is_estimated is False when human reviewer supplies an override.
    """
    tender_id = "43474eaf-b191-4dab-aacb-4465917bf45d"
    resp = client.get(
        f"/tenders/{tender_id}/pqc-credentials?override_value=20000000&override_scope=AC_UNIT&msme_relaxation=true"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["estimated_value"] == 20000000.0
    assert data["value_is_estimated"] is False
    assert data["computed_thresholds"]["eighty_pct"] == 16000000.0
    assert data["target_scope"] == "AC_UNIT"
    assert data["msme_relaxation_applicable"] is True


def test_pqc_documents_view_endpoint_success():
    """
    Tests GET /tenders/pqc-documents/view successfully serves an existing PQC PDF document.
    """
    path = "pqr-po/1778500608422_IOCL_HALDIYA_CE_CERTIFIED_PO__1_.pdf"
    resp = client.get(f"/tenders/pqc-documents/view?path={path}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 0


def test_pqc_documents_view_endpoint_traversal_defense():
    """
    Tests GET /tenders/pqc-documents/view rejects directory traversal attempts with 403 Forbidden.
    """
    traversal_paths = [
        "pqr-po/../../backend/app/main.py",
        "../../../etc/passwd",
        "pqr-completion/../../../Windows/System32/cmd.exe",
        "pqr-performance/sample.pdf",  # unapproved folder name
    ]
    for path in traversal_paths:
        resp = client.get(f"/tenders/pqc-documents/view?path={path}")
        assert resp.status_code == 403, f"Expected 403 for {path}, got {resp.status_code}"
        assert "access denied" in resp.json()["detail"].lower()


def test_pqc_documents_view_endpoint_missing_file():
    """
    Tests GET /tenders/pqc-documents/view returns 404 for a path within allowed directories that does not exist.
    """
    resp = client.get("/tenders/pqc-documents/view?path=pqr-po/nonexistent_file_000000.pdf")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


