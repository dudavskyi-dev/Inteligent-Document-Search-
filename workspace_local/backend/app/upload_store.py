from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import UPLOADS_DIR


@dataclass(frozen=True)
class UploadRecord:
    file_id: str
    filename: str
    path: Path


_lock = threading.Lock()
_uploads: dict[str, UploadRecord] = {}


def save_upload(filename: str, content: bytes) -> UploadRecord:
    file_id = uuid.uuid4().hex
    path = UPLOADS_DIR / f"{file_id}.pdf"
    path.write_bytes(content)
    record = UploadRecord(file_id=file_id, filename=filename, path=path)
    with _lock:
        _uploads[file_id] = record
    return record


def get_upload(file_id: str) -> UploadRecord:
    with _lock:
        return _uploads[file_id]
