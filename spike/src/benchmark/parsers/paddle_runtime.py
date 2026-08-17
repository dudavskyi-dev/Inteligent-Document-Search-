from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import ModuleType


def configure_paddle_environment(project_root: Path) -> None:
    cache = project_root / ".cache"
    os.environ.setdefault("PADDLE_HOME", str(cache / "paddle"))
    os.environ.setdefault("PADDLEOCR_HOME", str(cache / "paddleocr"))
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache / "paddlex"))
    os.environ.setdefault("PADDLE_PDX_CPU_NUM_THREADS", "4")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "huggingface")
    os.environ.setdefault("MODELSCOPE_CACHE", str(cache / "modelscope"))
    os.environ.setdefault("HF_HOME", str(cache / "huggingface"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(cache / "huggingface" / "hub"))


def import_paddle_locally(project_root: Path) -> tuple[ModuleType, ModuleType]:
    """Import Paddle while keeping its hard-coded user cache inside the project.

    Paddle 3.3 initializes ``~/.cache/paddle/dataset`` during import even when
    ``PADDLE_HOME`` is set. Temporarily overriding ``expanduser`` scopes that
    initialization to this process without changing HOME or USERPROFILE.
    """

    configure_paddle_environment(project_root)
    local_home = project_root / ".cache" / "paddle-home"
    local_home.mkdir(parents=True, exist_ok=True)
    original_expanduser = os.path.expanduser

    def local_expanduser(path: str | os.PathLike[str]) -> str:
        value = os.fspath(path)
        if value == "~":
            return str(local_home)
        if value.startswith(("~/", "~\\")):
            return str(local_home / value[2:])
        return original_expanduser(path)

    os.path.expanduser = local_expanduser
    try:
        # PaddleX imports ModelScope, which imports torch. On Windows, loading
        # Paddle DLLs first can make torch's shm.dll resolution fail.
        importlib.import_module("torch")
        paddle = importlib.import_module("paddle")
        paddleocr = importlib.import_module("paddleocr")
    finally:
        os.path.expanduser = original_expanduser
    return paddle, paddleocr
