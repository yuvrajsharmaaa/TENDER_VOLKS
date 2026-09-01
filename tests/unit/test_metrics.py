import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.metrics import (
    tender_task_duration_seconds,
    tender_task_total,
    tender_queue_depth,
    f_hard_disqualified_total,
    f_hard_unconstrained_total,
    f_hard_needs_review_total,
    advisory_fabrication_discard_total,
    record_fhard_metric,
    record_advisory_discard,
    record_queue_depth,
    track_task_duration,
    generate_metrics_text
)

client = TestClient(app)


def test_metrics_registration_and_recording():
    # Record events
    record_fhard_metric("MIN_ANNUAL_TURNOVER", "DISQUALIFIED")
    record_fhard_metric("MIN_WORKING_CAPITAL", "UNCONSTRAINED")
    record_fhard_metric("REQUIRED_CERTIFICATIONS", "NEEDS_REVIEW")
    record_advisory_discard("payment_terms")
    record_queue_depth("celery_ocr", 12.0)

    # Output text verification
    text = generate_metrics_text().decode("utf-8")
    assert "f_hard_disqualified_total" in text
    assert "f_hard_unconstrained_total" in text
    assert "f_hard_needs_review_total" in text
    assert "advisory_fabrication_discard_total" in text
    assert "tender_queue_depth" in text


def test_track_task_duration_decorator():
    @track_task_duration(task_name="test_timed_task", stage="extraction")
    def sample_func():
        return "OK"

    result = sample_func()
    assert result == "OK"

    text = generate_metrics_text().decode("utf-8")
    assert "tender_task_duration_seconds" in text
    assert 'task_name="test_timed_task"' in text


def test_fastapi_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "tender_task_total" in response.text
