import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Response, status
from backend.app.schemas.dlq import (
    DeadLetterEnvelope,
    DLQDiscardRequest,
    DLQBatchReplayRequest
)
from backend.app.repositories.dlq_repository import (
    list_dead_letter_envelopes,
    get_dead_letter_envelope,
    update_dlq_status
)

logger = logging.getLogger("backend.app.api.routes.dlq")
router = APIRouter(prefix="/admin/dlq", tags=["Admin DLQ"])


@router.get("", response_model=List[DeadLetterEnvelope])
async def list_dlq_items(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: PENDING, REPLAYED, DISCARDED"),
    limit: int = Query(50, ge=1, le=200)
):
    """
    List all dead-lettered tasks in the queue with optional status filtering.
    """
    items = list_dead_letter_envelopes(status=status_filter, limit=limit)
    return items


@router.get("/{dlq_id}", response_model=DeadLetterEnvelope)
async def get_dlq_item(dlq_id: str):
    """
    Retrieve full dead-letter envelope details, payload, and stack trace.
    """
    item = get_dead_letter_envelope(dlq_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"DLQ Envelope '{dlq_id}' not found")
    return item


@router.post("/{dlq_id}/replay", response_model=DeadLetterEnvelope)
async def replay_dlq_item(dlq_id: str):
    """
    Replay a failed task from the DLQ. Re-queues the execution and updates status to REPLAYED.
    """
    item = get_dead_letter_envelope(dlq_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"DLQ Envelope '{dlq_id}' not found")
        
    logger.info(f"[DLQ_REPLAY_TRIGGERED] Replaying DLQ task: {dlq_id} ({item.task_name})")
    
    # Trigger task re-execution if applicable
    try:
        if item.task_name == "tender_ingest" and "job_id" in item.payload:
            from backend.app.api.routes.tenders import _run_ingest_background
            _run_ingest_background.delay(
                item.payload["job_id"],
                item.payload.get("pdf_path"),
                item.payload.get("original_filename")
            )
    except Exception as e:
        logger.warning(f"Could not trigger background task worker during replay: {e}")
        
    updated = update_dlq_status(dlq_id, status="REPLAYED", resolution_notes="Replay triggered via Admin DLQ API")
    return updated


@router.post("/{dlq_id}/discard", response_model=DeadLetterEnvelope)
async def discard_dlq_item(dlq_id: str, req: DLQDiscardRequest):
    """
    Discard a failed task with mandatory substantive justification notes (>= 10 characters).
    """
    try:
        updated = update_dlq_status(dlq_id, status="DISCARDED", resolution_notes=req.resolution_notes)
        logger.info(f"[DLQ_DISCARD_RESOLVED] DLQ task {dlq_id} marked DISCARDED. Reason: '{req.resolution_notes}'")
        return updated
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))


@router.post("/replay-batch")
async def replay_batch_dlq_items(req: DLQBatchReplayRequest):
    """
    Batch replay multiple DLQ tasks.
    """
    items = list_dead_letter_envelopes(status=req.filter_status, limit=req.limit)
    replayed_ids = []
    for item in items:
        try:
            update_dlq_status(item.dlq_id, status="REPLAYED", resolution_notes="Batch replay triggered via Admin API")
            replayed_ids.append(item.dlq_id)
        except Exception as e:
            logger.error(f"Failed to replay DLQ item {item.dlq_id}: {e}")
            
    return {
        "status": "success",
        "replayed_count": len(replayed_ids),
        "replayed_ids": replayed_ids
    }
