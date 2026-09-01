import time
import functools
import logging
from typing import Callable, Any, Optional
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY
)

logger = logging.getLogger("backend.app.core.metrics")

# =============================================================================
# PROMETHEUS METRIC REGISTRY & DEFINITIONS (WEEK 8 OBSERVABILITY)
# =============================================================================

# 1. Pipeline Task Duration Histogram
# Tracks execution latency per task and stage with percentile distributions (p50, p95, p99)
TASK_DURATION_BUCKETS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)

tender_task_duration_seconds = Histogram(
    "tender_task_duration_seconds",
    "Duration of tender processing tasks in seconds by stage and status",
    labelnames=["task_name", "stage", "status"],
    buckets=TASK_DURATION_BUCKETS
)

# 2. Pipeline Task Execution Counter
# Tracks total task throughput, completions, retries, and errors
tender_task_total = Counter(
    "tender_task_total",
    "Total count of tender processing tasks executed by name and outcome status",
    labelnames=["task_name", "status"]
)

# 3. Queue Depth Gauge
# Tracks live backlog size and queue buffer saturation
tender_queue_depth = Gauge(
    "tender_queue_depth",
    "Current depth/backlog of tasks in processing queues",
    labelnames=["queue_name"]
)

# 4. Direct Structured-Log-Bound Counters
f_hard_disqualified_total = Counter(
    "f_hard_disqualified_total",
    "Total tender disqualifications emitted by Hard Compliance Filter rules",
    labelnames=["rule_name"]
)

f_hard_unconstrained_total = Counter(
    "f_hard_unconstrained_total",
    "Total unconstrained auto-passes where buyer omitted optional statutory clauses",
    labelnames=["rule_name"]
)

f_hard_needs_review_total = Counter(
    "f_hard_needs_review_total",
    "Total tenders routed to human review by Hard Compliance Filter rules",
    labelnames=["rule_name"]
)

advisory_fabrication_discard_total = Counter(
    "advisory_fabrication_discard_total",
    "Total ungrounded/hallucinated generative advisory drafts discarded by validation guardrails",
    labelnames=["clause_type"]
)

# Gauge for Alert Cutover Job Execution Timestamp
alert_cutover_job_last_run_timestamp = Gauge(
    "alert_cutover_job_last_run_timestamp",
    "Unix timestamp of the last successful run of the 14-day steady-state alert cutover job"
)


# =============================================================================
# TELEMETRY HELPERS & CONTEXT MANAGERS
# =============================================================================

def track_task_duration(task_name: str, stage: str = "default"):
    """
    Decorator to automatically record execution latency and outcome status in Prometheus.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as exc:
                status = "error"
                tender_task_total.labels(task_name=task_name, status="failure").inc()
                raise exc
            finally:
                duration = time.time() - start_time
                tender_task_duration_seconds.labels(
                    task_name=task_name, stage=stage, status=status
                ).observe(duration)
                tender_task_total.labels(task_name=task_name, status=status).inc()
        return wrapper
    return decorator


def record_fhard_metric(rule_name: str, status: str) -> None:
    """
    Increments structured log-bound metrics for F_hard compliance evaluation.
    """
    if status == "DISQUALIFIED":
        f_hard_disqualified_total.labels(rule_name=rule_name).inc()
    elif status == "NEEDS_REVIEW":
        f_hard_needs_review_total.labels(rule_name=rule_name).inc()
    elif status in ("QUALIFIED", "EXEMPT", "UNCONSTRAINED"):
        f_hard_unconstrained_total.labels(rule_name=rule_name).inc()


def record_advisory_discard(clause_type: str) -> None:
    """
    Increments fabrication discard counter for generative advisory guardrails.
    """
    advisory_fabrication_discard_total.labels(clause_type=clause_type).inc()


def record_queue_depth(queue_name: str, count: float) -> None:
    """
    Sets current queue depth for the specified queue.
    """
    tender_queue_depth.labels(queue_name=queue_name).set(count)


def generate_metrics_text() -> bytes:
    """
    Generates standard Prometheus exposition format text for the /metrics endpoint.
    """
    return generate_latest(REGISTRY)
