import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Add backend directory and its parent to sys.path to resolve both 'app' and 'backend.app' package imports
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(backend_dir.parent) not in sys.path:
    sys.path.insert(0, str(backend_dir.parent))
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.minio import minio_client

# Configuration, Logging and Middleware
from backend.app.core.config import settings
from backend.app.core.logging import setup_logging
from backend.app.core.request_id import RequestIDMiddleware

# Existing Routers and Repositories
from backend.app.core.constants import STORAGE_ROOT
from backend.app.api import upload, jobs, visualizer
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.tenders import router as tenders_router
from backend.app.api.routes.notify import router as notify_router

# Setup structured logging prior to boot
setup_logging(log_level=settings.log_level, service_name="tender_backend")
logger = logging.getLogger("backend.app.main")

def ensure_minio_buckets() -> None:
    """
    Day 2 Startup logic to automatically create raw and processed buckets in MinIO.
    """
    try:
        for bucket_name in [settings.minio_bucket_raw, settings.minio_bucket_processed, settings.MINIO_BUCKET]:
            if not minio_client.bucket_exists(bucket_name):
                minio_client.make_bucket(bucket_name)
                logger.info(f"MinIO bucket successfully initialized", extra={"custom_fields": {"bucket": bucket_name}})
            else:
                logger.info(f"MinIO bucket already present", extra={"custom_fields": {"bucket": bucket_name}})
    except Exception as e:
        logger.error(f"Unable to verify/create MinIO buckets during startup: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Events
    logger.info("Initializing VolksEnergies Tender OCR Backend", extra={"custom_fields": {
        "app_name": settings.app_name,
        "environment": settings.environment,
        "debug": settings.debug
    }})
    
    # 1. Initialize PostgreSQL database tables
    try:
        from backend.app.db.session import engine, Base
        from backend.app.models.tender_project import TenderProject
        from backend.app.models.document import Document
        from backend.app.models.tender_information import TenderInformation
        from backend.app.models.job import Job
        Base.metadata.create_all(bind=engine)
        logger.info("SQLAlchemy database tables verified")
    except Exception as e:
        logger.error(f"SQLAlchemy database initialization failed: {e}", exc_info=True)
        
    # 2. Setup Local filesystem directories
    (STORAGE_ROOT / "jobs").mkdir(parents=True, exist_ok=True)
    logger.info("Local storage directories initialized", extra={"custom_fields": {"storage_root": str(STORAGE_ROOT)}})
    
    # 3. Initialize storage buckets in S3 (MinIO)
    ensure_minio_buckets()
    
    # 4. Automatically recover and resume stuck jobs (pending/queued/processing)
    try:
        from backend.app.repositories.job_repository import get_all_jobs
        import asyncio
        from backend.app.api.routes.tenders import _run_ingest_background
        
        async def resume_stuck_jobs():
            await asyncio.sleep(2)
            jobs = get_all_jobs()
            for j in jobs:
                if j.get("status") in ("pending", "queued", "processing"):
                    logger.info(f"Resuming stuck job {j['job_id']} via Celery on startup")
                    _run_ingest_background.delay(
                        j["job_id"],
                        j["pdf_path"],
                        j["original_filename"]
                    )
        asyncio.create_task(resume_stuck_jobs())
    except Exception as recovery_err:
        logger.error(f"Failed to trigger startup job recovery: {recovery_err}", exc_info=True)


    # 5. Initialize Neo4j graph schema (constraints)
    try:
        from backend.app.db.neo4j_session import get_neo4j_driver, init_neo4j_schema
        neo4j_driver = get_neo4j_driver(
            uri=settings.NEO4J_URI,
            user=settings.NEO4J_USER,
            password=settings.NEO4J_PASSWORD
        )
        init_neo4j_schema(driver=neo4j_driver)
        logger.info("Neo4j graph schema initialized successfully")
    except Exception as e:
        logger.warning(f"Neo4j initialization skipped (non-fatal): {e}")

    yield
    # Shutdown Events
    logger.info("Shutting down VolksEnergies Tender OCR Backend")
    try:
        from backend.app.db.neo4j_session import close_neo4j_driver
        close_neo4j_driver()
        logger.info("Neo4j driver closed cleanly")
    except Exception as e:
        logger.warning(f"Neo4j driver close failed: {e}")

# Initialize FastAPI App
app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan
)

from fastapi.responses import FileResponse, Response
from backend.app.core.metrics import generate_metrics_text, CONTENT_TYPE_LATEST
from backend.app.api.routes.dlq import router as dlq_router

# Attach Request ID Tracing Middleware (must be first/early in chain)
app.add_middleware(RequestIDMiddleware)

# CORS Configuration — Strictly restricted to production URIs from settings (no wildcard fallback)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins if isinstance(settings.allowed_origins, list) else [settings.allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure local storage directory exists before mounting
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

# Mount local storage directory for static file access
app.mount("/storage", StaticFiles(directory=str(STORAGE_ROOT)), name="storage")

# Prometheus Metrics Endpoint
@app.get("/metrics", tags=["Observability"])
def prometheus_metrics():
    """Exposes application and pipeline telemetry in standard Prometheus text format."""
    return Response(content=generate_metrics_text(), media_type=CONTENT_TYPE_LATEST)

# Include API Routers
app.include_router(health_router)
app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(visualizer.router)
app.include_router(tenders_router)
app.include_router(notify_router)
app.include_router(dlq_router)

# Mount Built React Frontend & SPA Fallback Route for Production LAN Access
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="frontend_assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        api_prefixes = ("api/", "tenders/", "jobs/", "job/", "storage/", "health", "visualizer", "docs", "openapi.json", "redoc")
        if any(full_path.startswith(p) for p in api_prefixes):
            raise HTTPException(status_code=404, detail="Not found")
        file_path = frontend_dist / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")
