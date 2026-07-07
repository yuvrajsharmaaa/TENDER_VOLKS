import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Add backend directory to sys.path to resolve 'app' package imports
backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
from urllib.parse import urlparse
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.minio import minio_client

# Configuration, Logging and Middleware
from backend.app.core.config import settings
from backend.app.core.logging import setup_logging
from backend.app.core.request_id import RequestIDMiddleware

# Existing Routers and Repositories
from backend.app.repositories.migrations import init_db
from backend.app.core.constants import STORAGE_ROOT
from backend.app.api import upload, jobs, visualizer
from backend.app.api.routes.health import router as health_router

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
    
    # 1. Initialize DB migrations (SQLite for jobs)
    try:
        init_db()
        logger.info("Local SQLite job database schema validated")
    except Exception as e:
        logger.error(f"Local database migration failed: {e}", exc_info=True)
        
    # 1b. Initialize PostgreSQL database tables
    try:
        from backend.app.db.session import engine, Base
        from backend.app.models.tender_project import TenderProject
        from backend.app.models.document import Document
        from backend.app.models.tender_information import TenderInformation
        Base.metadata.create_all(bind=engine)
        logger.info("SQLAlchemy database tables initialized")
    except Exception as e:
        logger.error(f"SQLAlchemy database initialization failed: {e}", exc_info=True)
        
    # 2. Setup Local filesystem directories
    (STORAGE_ROOT / "jobs").mkdir(parents=True, exist_ok=True)
    logger.info("Local storage directories initialized", extra={"custom_fields": {"storage_root": str(STORAGE_ROOT)}})
    
    # 3. Initialize storage buckets in S3 (MinIO)
    ensure_minio_buckets()
    
    yield
    # Shutdown Events
    logger.info("Shutting down VolksEnergies Tender OCR Backend")

# Initialize FastAPI App
app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan
)

# Attach Request ID Tracing Middleware (must be first/early in chain)
app.add_middleware(RequestIDMiddleware)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure local storage directory exists before mounting
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

# Mount local storage directory for static file access
app.mount("/storage", StaticFiles(directory=str(STORAGE_ROOT)), name="storage")

# Include API Routers
app.include_router(health_router)
app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(visualizer.router)
from backend.app.api.routes.tenders import router as tenders_router
app.include_router(tenders_router)
