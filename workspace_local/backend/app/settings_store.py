from __future__ import annotations

import json
import threading

from app.config import SETTINGS_PATH

_lock = threading.Lock()


def get_model() -> str:
    with _lock:
        if not SETTINGS_PATH.is_file():
            return ""
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data.get("model", "")


def set_model(model: str) -> str:
    with _lock:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps({"model": model}), encoding="utf-8")
        return model
