from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, configure_environment
from app.routers import jobs, settings, uploads

load_dotenv(PROJECT_ROOT / "workspace_local" / "backend" / ".env")
configure_environment()

# Single-process, single-worker app: settings/upload/job state lives in process memory
# (see app/settings_store.py, app/upload_store.py, app/job_store.py). Do not run this
# with --workers > 1 or behind multiple processes; that is a real scaling limit,
# acceptable for the "one local reviewer" scope this app targets.
app = FastAPI(title="Industrial Document Extraction - Local UI")

app.include_router(settings.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")

_FRONTEND_DIST = PROJECT_ROOT / "workspace_local" / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
