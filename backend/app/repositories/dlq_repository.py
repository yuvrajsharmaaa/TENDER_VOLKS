import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from backend.app.schemas.dlq import DeadLetterEnvelope
from backend.app.core.metrics import tender_task_total, tender_queue_depth

logger = logging.getLogger("backend.app.repositories.dlq_repository")

# In-memory storage cache for local operations and offline testing
_IN_MEMORY_DLQ: Dict[str, DeadLetterEnvelope] = {}


def save_dead_letter_envelope(envelope: DeadLetterEnvelope) -> DeadLetterEnvelope:
    """
    Persists a DeadLetterEnvelope to PostgreSQL and in-memory cache,
    and updates telemetry metrics.
    """
    _IN_MEMORY_DLQ[envelope.dlq_id] = envelope
    
    try:
        from backend.app.db.session import SessionLocal
        from backend.app.models.dead_letter import DeadLetterRecord
        
        db = SessionLocal()
        record = DeadLetterRecord(
            dlq_id=envelope.dlq_id,
            task_id=envelope.task_id,
            task_name=envelope.task_name,
            payload=envelope.payload,
            error_type=envelope.error_type,
            error_message=envelope.error_message,
            stack_trace=envelope.stack_trace,
            attempt_count=envelope.attempt_count,
            status=envelope.status,
            resolution_notes=envelope.resolution_notes,
            created_at=envelope.created_at,
            updated_at=envelope.updated_at
        )
        db.merge(record)
        db.commit()
        db.close()
    except Exception as e:
        logger.warning(f"Could not persist DLQ record to DB (saved to memory): {e}")

    # Telemetry update
    tender_task_total.labels(task_name=envelope.task_name, status="dlq").inc()
    pending_count = sum(1 for e in _IN_MEMORY_DLQ.values() if e.status == "PENDING")
    tender_queue_depth.labels(queue_name="dlq").set(pending_count)
    
    logger.error(
        f"[DLQ_ENVELOPE_STORED] DLQ ID: {envelope.dlq_id} | Task: {envelope.task_name} | "
        f"Attempts: {envelope.attempt_count} | Error: {envelope.error_type}: {envelope.error_message}"
    )
    return envelope


def get_dead_letter_envelope(dlq_id: str) -> Optional[DeadLetterEnvelope]:
    """Retrieves a single DLQ envelope by ID."""
    if dlq_id in _IN_MEMORY_DLQ:
        return _IN_MEMORY_DLQ[dlq_id]
        
    try:
        from backend.app.db.session import SessionLocal
        from backend.app.models.dead_letter import DeadLetterRecord
        
        db = SessionLocal()
        record = db.query(DeadLetterRecord).filter(DeadLetterRecord.dlq_id == dlq_id).first()
        db.close()
        if record:
            env = DeadLetterEnvelope(
                dlq_id=record.dlq_id,
                task_id=record.task_id,
                task_name=record.task_name,
                payload=record.payload or {},
                error_type=record.error_type,
                error_message=record.error_message,
                stack_trace=record.stack_trace,
                attempt_count=record.attempt_count,
                status=record.status,
                resolution_notes=record.resolution_notes,
                created_at=record.created_at,
                updated_at=record.updated_at
            )
            _IN_MEMORY_DLQ[env.dlq_id] = env
            return env
    except Exception as e:
        logger.warning(f"DB error retrieving DLQ record {dlq_id}: {e}")
        
    return None


def list_dead_letter_envelopes(status: Optional[str] = None, limit: int = 50) -> List[DeadLetterEnvelope]:
    """Lists DLQ envelopes optionally filtered by status."""
    try:
        from backend.app.db.session import SessionLocal
        from backend.app.models.dead_letter import DeadLetterRecord
        
        db = SessionLocal()
        query = db.query(DeadLetterRecord)
        if status:
            query = query.filter(DeadLetterRecord.status == status)
        records = query.order_by(DeadLetterRecord.created_at.desc()).limit(limit).all()
        db.close()
        
        if records:
            res = []
            for r in records:
                env = DeadLetterEnvelope(
                    dlq_id=r.dlq_id,
                    task_id=r.task_id,
                    task_name=r.task_name,
                    payload=r.payload or {},
                    error_type=r.error_type,
                    error_message=r.error_message,
                    stack_trace=r.stack_trace,
                    attempt_count=r.attempt_count,
                    status=r.status,
                    resolution_notes=r.resolution_notes,
                    created_at=r.created_at,
                    updated_at=r.updated_at
                )
                _IN_MEMORY_DLQ[env.dlq_id] = env
                res.append(env)
            return res
    except Exception as e:
        logger.warning(f"DB error listing DLQ records: {e}")
        
    # Fallback to in-memory store
    items = list(_IN_MEMORY_DLQ.values())
    if status:
        items = [i for i in items if i.status == status]
    items.sort(key=lambda x: x.created_at, reverse=True)
    return items[:limit]


def update_dlq_status(
    dlq_id: str,
    status: str,
    resolution_notes: Optional[str] = None
) -> DeadLetterEnvelope:
    """
    Updates the status and resolution notes of a DLQ envelope,
    enforcing Pydantic validation (e.g. >= 10 chars for DISCARDED).
    """
    env = get_dead_letter_envelope(dlq_id)
    if not env:
        raise ValueError(f"DLQ Envelope with ID '{dlq_id}' not found.")
        
    # Build updated envelope to trigger model validation
    updated = DeadLetterEnvelope(
        dlq_id=env.dlq_id,
        task_id=env.task_id,
        task_name=env.task_name,
        payload=env.payload,
        error_type=env.error_type,
        error_message=env.error_message,
        stack_trace=env.stack_trace,
        attempt_count=env.attempt_count,
        status=status,
        resolution_notes=resolution_notes if resolution_notes is not None else env.resolution_notes,
        created_at=env.created_at,
        updated_at=datetime.now(timezone.utc)
    )
    
    _IN_MEMORY_DLQ[dlq_id] = updated
    
    try:
        from backend.app.db.session import SessionLocal
        from backend.app.models.dead_letter import DeadLetterRecord
        
        db = SessionLocal()
        record = db.query(DeadLetterRecord).filter(DeadLetterRecord.dlq_id == dlq_id).first()
        if record:
            record.status = updated.status
            record.resolution_notes = updated.resolution_notes
            record.updated_at = updated.updated_at
            db.commit()
        db.close()
    except Exception as e:
        logger.warning(f"Could not update DLQ record in DB: {e}")
        
    pending_count = sum(1 for e in _IN_MEMORY_DLQ.values() if e.status == "PENDING")
    tender_queue_depth.labels(queue_name="dlq").set(pending_count)
    return updated
