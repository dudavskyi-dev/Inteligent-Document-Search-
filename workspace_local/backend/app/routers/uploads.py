from __future__ import annotations

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from app import upload_store

router = APIRouter()


class UploadResponse(BaseModel):
    file_id: str
    filename: str


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile) -> UploadResponse:
    content = await file.read()
    record = upload_store.save_upload(file.filename or "document.pdf", content)
    return UploadResponse(file_id=record.file_id, filename=record.filename)
