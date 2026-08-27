from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import JOBS_DIR


def job_dir(job_id: str) -> Path:
    path = JOBS_DIR / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_stage(job_id: str, name: str, data: Any) -> None:
    """Persist one pipeline stage's output as its own numbered JSON file under
    data/jobs/{job_id}/, mirroring the spike/results/<stage>/ convention, so a run can
    be inspected after the fact stage by stage (parsing, stitching, retrieval, LLM)."""
    path = job_dir(job_id) / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
