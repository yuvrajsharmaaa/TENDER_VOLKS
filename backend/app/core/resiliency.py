import time
import logging
import traceback
from typing import Callable, Any, Dict, List, Optional
from backend.app.schemas.dlq import DeadLetterEnvelope
from backend.app.repositories.dlq_repository import save_dead_letter_envelope
from backend.app.core.metrics import tender_task_total

logger = logging.getLogger("backend.app.core.resiliency")

# Standard 3-attempt exponential backoff delays (2s -> 10s -> 30s)
DEFAULT_BACKOFF_DELAYS = [2, 10, 30]


def execute_with_dlq_retry(
    func: Callable,
    task_name: str,
    task_id: str,
    payload: Optional[Dict[str, Any]] = None,
    backoff_delays: Optional[List[int]] = None,
    sleep_fn: Callable[[float], None] = time.sleep
) -> Any:
    """
    Executes a task function with 3-attempt exponential retry backoff (2s, 10s, 30s).
    If all 3 attempts fail, catches the exception, constructs a DeadLetterEnvelope,
    persists it to the DLQ, and re-raises or returns the envelope.
    """
    delays = backoff_delays if backoff_delays is not None else DEFAULT_BACKOFF_DELAYS
    max_attempts = len(delays)
    payload_data = payload or {}
    
    last_error: Optional[Exception] = None
    last_trace: Optional[str] = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"[TASK_EXEC_ATTEMPT] Task: '{task_name}' (ID: {task_id}) | Attempt {attempt}/{max_attempts}")
            result = func()
            tender_task_total.labels(task_name=task_name, status="success").inc()
            return result
        except Exception as exc:
            last_error = exc
            last_trace = traceback.format_exc()
            logger.warning(
                f"[TASK_RETRY_BACKOFF] Task: '{task_name}' (ID: {task_id}) failed attempt {attempt}/{max_attempts}: {exc}"
            )
            tender_task_total.labels(task_name=task_name, status="retry").inc()
            
            if attempt < max_attempts:
                delay_sec = delays[attempt - 1]
                logger.info(f"Applying exponential backoff: sleeping {delay_sec}s before attempt {attempt + 1}...")
                sleep_fn(delay_sec)
            else:
                logger.error(
                    f"[TASK_EXHAUSTED_RETRIES] Task: '{task_name}' (ID: {task_id}) exhausted all {max_attempts} attempts. "
                    f"Routing to Dead Letter Queue (DLQ)."
                )
                
    # Exhausted retries -> Create and store DeadLetterEnvelope
    error_type_name = type(last_error).__name__ if last_error else "UnknownError"
    error_msg = str(last_error) if last_error else "Task failed after retries"
    
    envelope = DeadLetterEnvelope(
        task_id=task_id,
        task_name=task_name,
        payload=payload_data,
        error_type=error_type_name,
        error_message=error_msg,
        stack_trace=last_trace,
        attempt_count=max_attempts,
        status="PENDING"
    )
    saved_env = save_dead_letter_envelope(envelope)
    return saved_env
