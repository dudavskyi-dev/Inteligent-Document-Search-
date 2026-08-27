from __future__ import annotations

import os
from pathlib import Path

# app/ -> backend/ -> workspace_local/ -> repo root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SPIKE_SRC = PROJECT_ROOT / "spike" / "src"
CONTRACTS_DIR = PROJECT_ROOT / "contracts"
CACHE_DIR = PROJECT_ROOT / ".cache"

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
JOBS_DIR = DATA_DIR / "jobs"
SETTINGS_PATH = DATA_DIR / "settings.json"

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
LOCAL_RERANKER_MODEL_DIR = PROJECT_ROOT / "spike" / ".local_models" / "ms-marco-MiniLM-L6-v2"


def configure_environment() -> None:
    """Point every HF/Torch/Paddle cache at the project-local .cache/, matching the
    convention already used by spike/src/benchmark/run_context_assembly_demo.py, so
    model downloads land in one predictable, gitignored place instead of the user's
    home directory."""
    os.environ.setdefault("HF_HOME", str(CACHE_DIR / "huggingface"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(CACHE_DIR / "huggingface" / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(CACHE_DIR / "huggingface" / "transformers"))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(CACHE_DIR / "sentence-transformers"))
    os.environ.setdefault("TORCH_HOME", str(CACHE_DIR / "torch"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def reranker_model_name() -> str:
    """Use the local model copy if this machine has one (workaround for a
    network/SSL-restricted dev sandbox); otherwise fall back to the Hugging Face repo id,
    which downloads normally on a machine with regular internet access."""
    if LOCAL_RERANKER_MODEL_DIR.is_dir():
        return str(LOCAL_RERANKER_MODEL_DIR)
    return RERANKER_MODEL
