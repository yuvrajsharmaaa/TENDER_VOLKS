import pytest
from pydantic import ValidationError
from backend.app.schemas.dlq import DeadLetterEnvelope, DLQDiscardRequest
from backend.app.repositories.dlq_repository import (
    save_dead_letter_envelope,
    get_dead_letter_envelope,
    list_dead_letter_envelopes,
    update_dlq_status
)
from backend.app.core.resiliency import execute_with_dlq_retry


def test_dlq_envelope_creation_valid():
    env = DeadLetterEnvelope(
        task_id="task-123",
        task_name="tender_ingest",
        payload={"job_id": "job-abc"},
        error_type="PDFCorruptError",
        error_message="Cannot parse corrupted PDF stream",
        attempt_count=3,
        status="PENDING"
    )
    assert env.dlq_id is not None
    assert env.status == "PENDING"
    assert env.attempt_count == 3


def test_dlq_envelope_discard_blocks_without_substantive_notes():
    # Attempting to set DISCARDED without resolution_notes must fail
    with pytest.raises(ValidationError) as exc_info:
        DeadLetterEnvelope(
            task_id="task-456",
            task_name="ocr_extract",
            error_type="TimeoutError",
            error_message="Service timed out",
            status="DISCARDED",
            resolution_notes=None
        )
    assert "Transition to DISCARDED is blocked" in str(exc_info.value)

    # Attempting to set DISCARDED with short stub notes (< 10 chars) must fail
    with pytest.raises(ValidationError) as exc_info2:
        DeadLetterEnvelope(
            task_id="task-456",
            task_name="ocr_extract",
            error_type="TimeoutError",
            error_message="Service timed out",
            status="DISCARDED",
            resolution_notes="ignore it"  # 9 chars
        )
    assert "Transition to DISCARDED is blocked" in str(exc_info2.value)


def test_dlq_envelope_discard_succeeds_with_substantive_notes():
    # >= 10 chars resolution notes passes validation
    env = DeadLetterEnvelope(
        task_id="task-789",
        task_name="ocr_extract",
        error_type="TimeoutError",
        error_message="Service timed out",
        status="DISCARDED",
        resolution_notes="Buyer cancelled the procurement tender officially"  # 49 chars
    )
    assert env.status == "DISCARDED"
    assert len(env.resolution_notes) >= 10


def test_dlq_repository_lifecycle():
    env = DeadLetterEnvelope(
        task_id="task-lifecycle",
        task_name="tender_ingest",
        payload={"test": 1},
        error_type="ConnectionError",
        error_message="Connection refused",
        status="PENDING"
    )
    saved = save_dead_letter_envelope(env)
    assert saved.dlq_id == env.dlq_id

    # Retrieve
    retrieved = get_dead_letter_envelope(saved.dlq_id)
    assert retrieved is not None
    assert retrieved.dlq_id == saved.dlq_id
    assert retrieved.status == "PENDING"

    # List
    items = list_dead_letter_envelopes(status="PENDING")
    assert any(i.dlq_id == saved.dlq_id for i in items)

    # Update to REPLAYED
    updated_replay = update_dlq_status(saved.dlq_id, status="REPLAYED", resolution_notes="Manual retry")
    assert updated_replay.status == "REPLAYED"

    # Update to DISCARDED with valid note
    updated_discard = update_dlq_status(
        saved.dlq_id,
        status="DISCARDED",
        resolution_notes="Corrupted test fixture discarded after inspection"
    )
    assert updated_discard.status == "DISCARDED"


def test_execute_with_dlq_retry_success():
    call_count = 0
    def succeeding_task():
        nonlocal call_count
        call_count += 1
        return "SUCCESS_RESULT"

    res = execute_with_dlq_retry(
        succeeding_task,
        task_name="test_success_task",
        task_id="t-succ",
        backoff_delays=[0, 0, 0],
        sleep_fn=lambda s: None
    )
    assert res == "SUCCESS_RESULT"
    assert call_count == 1


def test_execute_with_dlq_retry_exhaustion_routes_to_dlq():
    attempts = 0
    def failing_task():
        nonlocal attempts
        attempts += 1
        raise ValueError(f"Forced failure attempt {attempts}")

    res = execute_with_dlq_retry(
        failing_task,
        task_name="test_failing_task",
        task_id="t-fail",
        payload={"sample_param": 42},
        backoff_delays=[0, 0, 0],
        sleep_fn=lambda s: None
    )
    assert attempts == 3
    assert isinstance(res, DeadLetterEnvelope)
    assert res.task_name == "test_failing_task"
    assert res.attempt_count == 3
    assert res.status == "PENDING"
    assert res.error_type == "ValueError"
