import os
import sys
import logging
from fastapi import APIRouter
from typing import Dict, Any
from urllib.parse import urlparse
import psycopg2
import redis
from backend.app.core.minio import minio_client

from backend.app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

def get_memory_usage_mb() -> float:
    """
    Retrieves the memory footprint of the current process in MB.
    Uses /proc/self/status on Linux or falls back to the resource module.
    """
    try:
        if os.path.exists("/proc/self/status"):
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        return round(float(parts[1]) / 1024.0, 2)
    except Exception:
        pass
    
    try:
        import resource
        # ru_maxrss is in KB on Linux, but bytes on macOS
        factor = 1024.0 if sys.platform != "darwin" else 1024.0 * 1024.0
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / factor, 2)
    except Exception:
        pass
    
    return 0.0

def get_cpu_load() -> float:
    """
    Returns the system 1-minute load average. Returns 0.0 if not supported.
    """
    try:
        return round(os.getloadavg()[0], 2)
    except Exception:
        return 0.0

@router.get("/health", status_code=200)
@router.get("/api/health", status_code=200)
async def health_check() -> Dict[str, Any]:
    """
    Day 2 health endpoint checking database, caching, storage and resources.
    """
    # 1. PostgreSQL check
    postgres_ok = False
    try:
        conn = psycopg2.connect(settings.database_url, connect_timeout=3)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        postgres_ok = True
        conn.close()
    except Exception as e:
        logger.error(f"PostgreSQL health check failure: {e}", exc_info=True)
        
    # 2. Redis check
    redis_ok = False
    try:
        r = redis.Redis.from_url(settings.redis_url, socket_timeout=3)
        redis_ok = bool(r.ping())
    except Exception as e:
        logger.error(f"Redis health check failure: {e}", exc_info=True)
        
    # 3. MinIO check
    minio_ok = False
    try:
        minio_client.list_buckets()
        minio_ok = True
    except Exception as e:
        logger.error(f"MinIO health check failure: {e}", exc_info=True)
        
    status = "healthy"
    if not (postgres_ok and redis_ok and minio_ok):
        status = "degraded"
        
    return {
        "status": status,
        "environment": settings.environment,
        "services": {
            "postgres": "healthy" if postgres_ok else "unhealthy",
            "redis": "healthy" if redis_ok else "unhealthy",
            "minio": "healthy" if minio_ok else "unhealthy"
        },
        "system": {
            "memory_usage_mb": get_memory_usage_mb(),
            "cpu_load_1m": get_cpu_load(),
            "pid": os.getpid()
        }
    }
