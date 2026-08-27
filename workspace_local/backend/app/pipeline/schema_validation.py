from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from app.config import CONTRACTS_DIR

SCHEMA_PATH = CONTRACTS_DIR / "extraction_candidate_v1.schema.json"


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_candidate(data: Any) -> list[str]:
    validator = Draft202012Validator(load_schema())
    return [
        f"{'/'.join(str(part) for part in error.path)}: {error.message}"
        for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    ]
