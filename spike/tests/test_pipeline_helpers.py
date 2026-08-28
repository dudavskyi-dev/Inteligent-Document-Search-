from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.models import (
    Block,
    BoundingBox,
    CanonicalDocument,
    Page,
    ParserRun,
    Provenance,
    TableCell,
    TableFragment,
)
from benchmark.run_pipeline import (
    build_page_evidence,
    collect_allowed_evidence_ids,
    expand_linked_tables,
    extract_json_object,
    from_evidence_id,
    to_evidence_id,
    to_wire_schema,
    validate_candidate,
    verify_canonical,
)
from benchmark.table_stitching import LogicalTable, StitchResult

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "extraction_candidate_v1.schema.json"
)


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _provenance(page_number: int = 7) -> list[Provenance]:
    return [
        Provenance(
            page_number=page_number,
            bbox=BoundingBox(x1=0.1, y1=0.2, x2=0.9, y2=0.3),
            parser="docling",
        )
    ]


def _document() -> CanonicalDocument:
    page = Page(
        page_number=7,
        width=595.0,
        height=842.0,
        blocks=[
            Block(
                block_id="p7-b0",
                type="heading",
                text="Price Schedule",
                reading_order=0,
                provenance=_provenance(),
            ),
            Block(
                block_id="p7-b1",
                type="paragraph",
                text="   ",
                reading_order=1,
                provenance=_provenance(),
            ),
        ],
        tables=[
            TableFragment(
                table_id="p7-t0",
                caption="Line items",
                cells=[
                    TableCell(
                        cell_id="p7-t0-c0",
                        row=0,
                        column=0,
                        text="Part",
                        is_column_header=True,
                        provenance=_provenance(),
                    ),
                    TableCell(
                        cell_id="p7-t0-c1",
                        row=1,
                        column=0,
                        text="AX-1042",
                        provenance=_provenance(),
                    ),
                    TableCell(
                        cell_id="p7-t0-c2",
                        row=1,
                        column=1,
                        text="250",
                        provenance=_provenance(),
                    ),
                ],
                provenance=_provenance(),
            )
        ],
    )
    return CanonicalDocument(
        document_id="doc",
        source_filename="doc.pdf",
        sha256="0" * 64,
        parser_run=ParserRun(strategy="hybrid", parser_versions={}, elapsed_seconds=1.0),
        pages=[page],
    )


# --------------------------------------------------------------------------------------
# Evidence IDs
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("canonical_id", ["p7-b12", "p7-t2-c5", "p13-t0-r4"])
def test_evidence_id_round_trips(canonical_id: str) -> None:
    assert from_evidence_id(to_evidence_id(canonical_id)) == canonical_id


def test_evidence_id_rejects_ambiguous_input() -> None:
    with pytest.raises(ValueError):
        to_evidence_id("p7_b12")
    with pytest.raises(ValueError):
        from_evidence_id("p7-b12")


def test_evidence_id_matches_contract_example_style() -> None:
    assert to_evidence_id("p7-b3") == "ev_p7_b3"
    assert to_evidence_id("p7-t2-c5") == "ev_p7_t2_c5"


# --------------------------------------------------------------------------------------
# Wire schema
# --------------------------------------------------------------------------------------


def test_wire_schema_removes_unsupported_keywords() -> None:
    wire = to_wire_schema(_contract())
    serialized = json.dumps(wire)
    assert "oneOf" not in serialized
    assert "minLength" not in serialized
    assert "uniqueItems" not in serialized
    assert '"const"' not in serialized
    assert "$schema" not in wire
    assert "$id" not in wire


def test_wire_schema_converts_const_and_oneof() -> None:
    wire = to_wire_schema(_contract())
    assert wire["properties"]["schema_version"]["enum"] == ["industrial-document-candidate/1.0"]
    document_number = wire["properties"]["document_number"]
    assert "anyOf" in document_number
    assert {"type": "null"} in document_number["anyOf"]


def test_wire_schema_preserves_structure() -> None:
    wire = to_wire_schema(_contract())
    assert wire["type"] == "object"
    assert wire["additionalProperties"] is False
    assert set(wire["required"]) == set(wire["properties"])
    assert "candidateLineItem" in wire["$defs"]


def test_wire_schema_rejects_a_contract_that_breaks_strict_mode() -> None:
    contract = _contract()
    contract["properties"]["surprise"] = {"type": "string"}
    with pytest.raises(ValueError, match="every property to be required"):
        to_wire_schema(contract)

    contract = _contract()
    contract["additionalProperties"] = True
    with pytest.raises(ValueError, match="additionalProperties:false"):
        to_wire_schema(contract)


# --------------------------------------------------------------------------------------
# Linked table expansion
# --------------------------------------------------------------------------------------


def _stitch(tables: list[LogicalTable]) -> StitchResult:
    return StitchResult(source_document_id="doc", decisions=[], logical_tables=tables)


def test_expansion_pulls_in_the_continuation_page() -> None:
    stitch = _stitch(
        [
            LogicalTable(
                logical_table_id="lt-001",
                fragment_ids=["p24-t0", "p25-t0"],
                page_numbers=[24, 25],
                source_cell_ids=[],
                joins=[],
            )
        ]
    )
    expanded, trace = expand_linked_tables({24}, stitch)
    assert expanded == {24, 25}
    assert trace[0]["logical_table_id"] == "lt-001"
    assert trace[0]["added_pages"] == [25]


def test_expansion_ignores_untouched_tables() -> None:
    stitch = _stitch(
        [
            LogicalTable(
                logical_table_id="lt-002",
                fragment_ids=["p40-t0", "p41-t0"],
                page_numbers=[40, 41],
                source_cell_ids=[],
                joins=[],
            )
        ]
    )
    expanded, trace = expand_linked_tables({24}, stitch)
    assert expanded == {24}
    assert trace == []


def test_expansion_records_nothing_when_all_pages_already_selected() -> None:
    stitch = _stitch(
        [
            LogicalTable(
                logical_table_id="lt-003",
                fragment_ids=["p24-t0", "p25-t0"],
                page_numbers=[24, 25],
                source_cell_ids=[],
                joins=[],
            )
        ]
    )
    expanded, trace = expand_linked_tables({24, 25}, stitch)
    assert expanded == {24, 25}
    assert trace == []


# --------------------------------------------------------------------------------------
# Canonical verification and evidence catalog
# --------------------------------------------------------------------------------------


def test_verify_canonical_accepts_a_well_formed_document() -> None:
    verify_canonical(_document())


def test_verify_canonical_rejects_a_duplicate_block_id() -> None:
    document = _document()
    document.pages[0].blocks[1].block_id = "p7-b0"
    with pytest.raises(ValueError, match="Duplicate canonical block ID"):
        verify_canonical(document)


def test_verify_canonical_rejects_a_page_mismatch() -> None:
    document = _document()
    document.pages[0].blocks[0].provenance[0].page_number = 8
    with pytest.raises(ValueError, match="cites page 8"):
        verify_canonical(document)


def test_page_evidence_skips_blank_blocks_and_emits_rows_and_cells() -> None:
    evidence = build_page_evidence(_document().pages[0])
    assert [block["evidence_id"] for block in evidence["blocks"]] == ["ev_p7_b0"]
    rows = evidence["tables"][0]["rows"]
    assert [row["evidence_id"] for row in rows] == ["ev_p7_t0_r0", "ev_p7_t0_r1"]
    assert rows[0]["is_header_row"] is True
    assert rows[1]["text"] == "AX-1042 | 250"

    allowed = collect_allowed_evidence_ids([evidence])
    assert "ev_p7_b0" in allowed
    assert "ev_p7_t0_r1" in allowed
    assert "ev_p7_t0_c2" in allowed
    assert len(allowed) == len(set(allowed))


# --------------------------------------------------------------------------------------
# Response parsing and validation
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        'Here is the result:\n{"a": 1}',
    ],
)
def test_extract_json_object_tolerates_wrappers(content: str) -> None:
    assert extract_json_object(content) == {"a": 1}


def test_extract_json_object_rejects_prose() -> None:
    with pytest.raises(ValueError):
        extract_json_object("I could not find the document number.")


def _candidate(**overrides) -> dict:
    candidate = {
        "schema_version": "industrial-document-candidate/1.0",
        "document_number": {
            "status": "supported",
            "raw": "RFQ 2026-184/B",
            "value": "2026-184/B",
            "evidence_ids": ["ev_p7_b0"],
            "conflict_evidence_ids": [],
        },
        "parties": [],
        "deadlines": [],
        "line_items": [],
        "abstained_field_paths": [],
    }
    candidate.update(overrides)
    return candidate


ALLOWED = {"ev_p7_b0", "ev_p7_t0_c1", "ev_p7_t0_c2"}


def test_validation_accepts_a_clean_candidate() -> None:
    assert validate_candidate(_candidate(), _contract(), ALLOWED) == []


def test_validation_rejects_an_unknown_evidence_id() -> None:
    candidate = _candidate()
    candidate["document_number"]["evidence_ids"] = ["ev_p99_b1"]
    issues = validate_candidate(candidate, _contract(), ALLOWED)
    assert [issue["rule"] for issue in issues] == ["evidence_allow_list"]
    assert "ev_p99_b1" in issues[0]["message"]


def test_validation_rejects_supported_without_a_value() -> None:
    candidate = _candidate()
    candidate["document_number"]["value"] = None
    issues = validate_candidate(candidate, _contract(), ALLOWED)
    assert any(issue["rule"] == "status_coherence" for issue in issues)


def test_validation_rejects_a_normalized_value_on_not_found() -> None:
    candidate = _candidate()
    candidate["document_number"]["status"] = "not_found"
    issues = validate_candidate(candidate, _contract(), ALLOWED)
    assert any(
        issue["rule"] == "status_coherence" and issue["field_path"].endswith("/value")
        for issue in issues
    )


def test_validation_checks_quantity_decimals_and_tolerance_bounds() -> None:
    candidate = _candidate(
        line_items=[
            {
                "source_row_ids": ["ev_p7_t0_c1"],
                "part_number": None,
                "description": None,
                "quantity": {
                    "status": "supported",
                    "raw": "two hundred",
                    "value": "two hundred",
                    "unit": "EA",
                    "evidence_ids": ["ev_p7_t0_c2"],
                    "conflict_evidence_ids": [],
                },
                "tolerances": [
                    {
                        "status": "supported",
                        "type": "dimensional",
                        "target": "diameter",
                        "raw": "20 +0.02/-0.01 mm",
                        "nominal": "20.00",
                        "lower_limit": "21.00",
                        "upper_limit": "20.02",
                        "unit": "millimetre",
                        "standard": None,
                        "evidence_ids": ["ev_p7_t0_c2"],
                        "conflict_evidence_ids": [],
                    }
                ],
                "unit_price": None,
                "line_total": None,
                "delivery_deadline": None,
            }
        ]
    )
    rules = {issue["rule"] for issue in validate_candidate(candidate, _contract(), ALLOWED)}
    # "two hundred" also violates the contract's decimal pattern, so schema fires too.
    assert "decimal_parse" in rules
    assert "tolerance_bounds" in rules


def test_validation_reports_schema_errors() -> None:
    candidate = _candidate()
    del candidate["line_items"]
    issues = validate_candidate(candidate, _contract(), ALLOWED)
    assert any(issue["rule"] == "schema" for issue in issues)
