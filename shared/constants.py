from enum import Enum
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE_ROOT = PROJECT_ROOT / "storage"
DB_PATH = PROJECT_ROOT / "data" / "tender.db"

# Status strings
class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
