from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

JobStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass
class JobRecord:
    job_id: str
    file_id: str
    filename: str
    status: JobStatus = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    result: dict[str, Any] | None = None
    error: str | None = None


_lock = threading.Lock()
_jobs: dict[str, JobRecord] = {}


def create(file_id: str, filename: str) -> JobRecord:
    job_id = uuid.uuid4().hex
    record = JobRecord(job_id=job_id, file_id=file_id, filename=filename)
    with _lock:
        _jobs[job_id] = record
    return record


def get(job_id: str) -> JobRecord:
    with _lock:
        return _jobs[job_id]


def mark_running(job_id: str) -> None:
    with _lock:
        _jobs[job_id].status = "running"


def mark_succeeded(job_id: str, result: dict[str, Any]) -> None:
    with _lock:
        job = _jobs[job_id]
        job.status = "succeeded"
        job.result = result


def mark_failed(job_id: str, error: str) -> None:
    with _lock:
        job = _jobs[job_id]
        job.status = "failed"
        job.error = error
