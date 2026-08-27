from __future__ import annotations

from typing import NamedTuple


class FieldFamily(NamedTuple):
    key: str
    label: str
    query: str


# Matches the five field families defined in architecture_blueprint.md, section
# "4. Structural retrieval, not whole-page-only search".
FIELD_FAMILIES: list[FieldFamily] = [
    FieldFamily(
        key="document_identity",
        label="Document identity / parties",
        query=(
            "document number, buyer, supplier, contractor and other parties named in "
            "this document"
        ),
    ),
    FieldFamily(
        key="parts_and_quantities",
        label="Parts and quantities",
        query="part numbers, item descriptions, and quantities ordered",
    ),
    FieldFamily(
        key="tolerances",
        label="Tolerances / acceptance criteria",
        query=(
            "dimensional tolerances, acceptance criteria, and quality or inspection "
            "standards"
        ),
    ),
    FieldFamily(
        key="deadlines",
        label="Deadlines / periods",
        query=(
            "bid submission deadline, delivery deadline, performance start and end "
            "dates"
        ),
    ),
    FieldFamily(
        key="prices_and_fees",
        label="Prices / fees",
        query="unit prices, line totals, fees, and currency",
    ),
]
