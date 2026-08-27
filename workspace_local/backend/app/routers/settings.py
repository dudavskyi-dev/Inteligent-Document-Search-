from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import settings_store

router = APIRouter()


class SettingsPayload(BaseModel):
    model: str


@router.get("/settings", response_model=SettingsPayload)
def get_settings() -> SettingsPayload:
    return SettingsPayload(model=settings_store.get_model())


@router.put("/settings", response_model=SettingsPayload)
def put_settings(payload: SettingsPayload) -> SettingsPayload:
    return SettingsPayload(model=settings_store.set_model(payload.model))
