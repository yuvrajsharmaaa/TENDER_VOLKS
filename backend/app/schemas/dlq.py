import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel, Field, model_validator


class DeadLetterEnvelope(BaseModel):
    """
    Standardized Dead Letter Queue (DLQ) Envelope for failed asynchronous tasks.
    Enforces substantive audit resolution notes before any task can be marked DISCARDED.
    """
    dlq_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    task_name: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    attempt_count: int = 1
    status: Literal["PENDING", "REPLAYED", "DISCARDED", "RESOLVED"] = "PENDING"
    resolution_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_discarded_resolution_notes(self) -> "DeadLetterEnvelope":
        """
        Guardrail: Strictly blocks transition to 'DISCARDED' status without a substantive
        resolution note (at least 10 non-whitespace characters) explaining the justification.
        """
        if self.status == "DISCARDED":
            notes = (self.resolution_notes or "").strip()
            if len(notes) < 10:
                raise ValueError(
                    f"Transition to DISCARDED is blocked: Substantive resolution_notes (>= 10 characters) "
                    f"is required to discard a failed task. Provided note was '{notes}' ({len(notes)} chars)."
                )
        return self


class DLQDiscardRequest(BaseModel):
    resolution_notes: str = Field(
        ...,
        min_length=10,
        description="Mandatory substantive explanation (>= 10 chars) for discarding failed DLQ task"
    )


class DLQBatchReplayRequest(BaseModel):
    filter_status: Optional[str] = "PENDING"
    limit: int = 50
