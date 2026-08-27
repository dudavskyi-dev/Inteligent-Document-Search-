import json

from app.config import CONTRACTS_DIR
from app.pipeline.contract_models import ExtractionCandidateResponse
from app.pipeline.schema_validation import validate_candidate

EXAMPLE_PATH = CONTRACTS_DIR / "extraction_candidate_v1.example.json"


def _load_example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def test_real_example_passes_schema_validation() -> None:
    assert validate_candidate(_load_example()) == []


def test_real_example_parses_into_contract_models() -> None:
    result = ExtractionCandidateResponse.model_validate(_load_example())

    assert result.document_number is not None
    assert result.document_number.value == "2026-184/B"
    assert len(result.line_items) == 1
    assert result.line_items[0].part_number.value == "AX-1042"


def test_missing_required_field_is_reported() -> None:
    data = _load_example()
    del data["abstained_field_paths"]

    errors = validate_candidate(data)

    assert any("abstained_field_paths" in error for error in errors)


def test_invalid_status_enum_is_reported() -> None:
    data = _load_example()
    data["document_number"]["status"] = "definitely_not_a_valid_status"

    errors = validate_candidate(data)

    assert len(errors) == 1
    assert "document_number" in errors[0]
