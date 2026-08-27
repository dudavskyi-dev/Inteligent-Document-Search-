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
from benchmark.table_stitching import LogicalTable, StitchResult

from app.pipeline.evidence import collect_evidence_ids


def _provenance(page_number: int) -> Provenance:
    return Provenance(
        page_number=page_number,
        bbox=BoundingBox(x1=0.1, y1=0.1, x2=0.9, y2=0.2),
        parser="fixture",
        confidence=0.99,
    )


def _block(block_id: str, reading_order: int, text: str, page_number: int) -> Block:
    return Block(
        block_id=block_id,
        type="paragraph",
        text=text,
        reading_order=reading_order,
        provenance=[_provenance(page_number)],
    )


def _cell(cell_id: str, row: int, column: int, text: str, page_number: int) -> TableCell:
    return TableCell(cell_id=cell_id, row=row, column=column, text=text, provenance=[_provenance(page_number)])


def _document(pages: list[Page], document_id: str = "doc") -> CanonicalDocument:
    return CanonicalDocument(
        document_id=document_id,
        source_filename=f"{document_id}.pdf",
        sha256="0" * 64,
        parser_run=ParserRun(strategy="hybrid", parser_versions={"fixture": "1.0"}, elapsed_seconds=0.1),
        pages=pages,
    )


def test_collect_evidence_ids_for_a_block_includes_its_neighbors() -> None:
    page = Page(
        page_number=1,
        width=1000,
        height=1400,
        blocks=[
            _block("b1", 0, "Before", 1),
            _block("b2", 1, "Target", 1),
            _block("b3", 2, "After", 1),
        ],
        tables=[],
    )
    document = _document([page])
    stitch_result = StitchResult(source_document_id="doc", decisions=[], logical_tables=[])

    ids = collect_evidence_ids(document, stitch_result, "doc:b2")

    assert set(ids) == {"b1", "b2", "b3"}


def test_collect_evidence_ids_for_a_stitched_table_uses_source_cell_ids() -> None:
    fragment = TableFragment(
        table_id="t1", cells=[_cell("t1-c1", 0, 0, "A", 1)], provenance=[_provenance(1)]
    )
    page = Page(page_number=1, width=1000, height=1400, blocks=[], tables=[fragment])
    document = _document([page])
    logical_table = LogicalTable(
        logical_table_id="lt1",
        fragment_ids=["t1"],
        page_numbers=[1],
        source_cell_ids=["t1-c1", "t1-c2"],
        joins=[],
    )
    stitch_result = StitchResult(source_document_id="doc", decisions=[], logical_tables=[logical_table])

    ids = collect_evidence_ids(document, stitch_result, "doc:t1-r0")

    assert ids == ["t1-c1", "t1-c2"]


def test_collect_evidence_ids_for_an_unstitched_table_uses_its_own_cells() -> None:
    fragment = TableFragment(
        table_id="t1",
        cells=[_cell("t1-c1", 0, 0, "A", 1), _cell("t1-c2", 0, 1, "B", 1)],
        provenance=[_provenance(1)],
    )
    page = Page(page_number=1, width=1000, height=1400, blocks=[], tables=[fragment])
    document = _document([page])
    stitch_result = StitchResult(source_document_id="doc", decisions=[], logical_tables=[])

    ids = collect_evidence_ids(document, stitch_result, "doc:t1-r0")

    assert set(ids) == {"t1-c1", "t1-c2"}
