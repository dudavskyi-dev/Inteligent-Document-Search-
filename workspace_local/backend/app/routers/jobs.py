from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app import job_store, settings_store, upload_store
from app.job_store import JobStatus
from app.pipeline import job_artifacts
from app.pipeline.run_pipeline import run_extraction_pipeline

router = APIRouter()


class CreateJobRequest(BaseModel):
    file_id: str


class CreateJobResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    filename: str
    created_at: str
    result: dict[str, Any] | None
    error: str | None


def _execute_job(job_id: str, pdf_path: Path, model: str) -> None:
    job_store.mark_running(job_id)
    try:
        result = run_extraction_pipeline(job_id, pdf_path, model)
        job_store.mark_succeeded(job_id, result)
    except Exception as exc:  # noqa: BLE001 - single background-worker error boundary
        job_store.mark_failed(job_id, f"{type(exc).__name__}: {exc}")
    finally:
        job = job_store.get(job_id)
        job_artifacts.save_stage(
            job_id,
            "job",
            {
                "job_id": job.job_id,
                "file_id": job.file_id,
                "filename": job.filename,
                "status": job.status,
                "created_at": job.created_at,
                "error": job.error,
            },
        )


@router.post("/jobs", response_model=CreateJobResponse)
def create_job(payload: CreateJobRequest) -> CreateJobResponse:
    upload = upload_store.get_upload(payload.file_id)
    job = job_store.create(file_id=upload.file_id, filename=upload.filename)
    job_artifacts.save_stage(
        job.job_id,
        "00_upload",
        {"file_id": upload.file_id, "filename": upload.filename, "size_bytes": upload.path.stat().st_size},
    )
    threading.Thread(
        target=_execute_job, args=(job.job_id, upload.path, settings_store.get_model()), daemon=True
    ).start()
    return CreateJobResponse(job_id=job.job_id)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    job = job_store.get(job_id)
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        filename=job.filename,
        created_at=job.created_at,
        result=job.result,
        error=job.error,
    )
