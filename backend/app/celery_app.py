import os
import sys
from pathlib import Path
from celery import Celery

# Ensure backend and root directory are in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(backend_dir.parent) not in sys.path:
    sys.path.insert(0, str(backend_dir.parent))

from backend.app.core.config import settings

# Determine Redis broker and backend URL
redis_url = getattr(settings, "redis_url", None) or os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "tender_volks",
    broker=redis_url,
    backend=redis_url,
    include=["backend.app.api.routes.tenders"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)
