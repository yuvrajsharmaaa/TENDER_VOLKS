from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.db.migrations import init_db
from app.routers import upload, jobs, visualizer
from shared.constants import STORAGE_ROOT

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    (STORAGE_ROOT / "jobs").mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown

app = FastAPI(lifespan=lifespan)

# Mount storage directory for static file access (images, page JSONs)
app.mount("/storage", StaticFiles(directory=str(STORAGE_ROOT)), name="storage")

app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(visualizer.router)

