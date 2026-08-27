from benchmark.context_assembly import (
    Neighbor,
    build_chunk_context,
    build_llm_context,
    find_neighbor_blocks,
    find_table_fragment,
    index_logical_tables,
    render_logical_table,
)
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


def _provenance(page_number: int) -> Provenance:
    return Provenance(
        page_number=page_number,
        bbox=BoundingBox(x1=0.1, y1=0.1, x2=0.9, y2=0.2),
        parser="fixture",
        confidence=0.99,
    )


def _block(block_id: str, reading_order: int, text: str, page_number: int, block_type: str = "paragraph") -> Block:
    return Block(
        block_id=block_id,
        type=block_type,
        text=text,
        reading_order=reading_order,
        provenance=[_provenance(page_number)],
    )


def _cell(
    cell_id: str, row: int, column: int, text: str, page_number: int, is_column_header: bool = False
) -> TableCell:
    return TableCell(
        cell_id=cell_id,
        row=row,
        column=column,
        text=text,
        is_column_header=is_column_header,
        provenance=[_provenance(page_number)],
    )


def _table(table_id: str, cells: list[TableCell], page_number: int) -> TableFragment:
    return TableFragment(table_id=table_id, cells=cells, provenance=[_provenance(page_number)])


def _document(pages: list[Page], document_id: str = "doc") -> CanonicalDocument:
    return CanonicalDocument(
        document_id=document_id,
        source_filename=f"{document_id}.pdf",
        sha256="0" * 64,
        parser_run=ParserRun(strategy="hybrid", parser_versions={"fixture": "1.0"}, elapsed_seconds=0.1),
        pages=pages,
    )


def test_neighbors_within_same_page() -> None:
    page = Page(
        page_number=1,
        width=1000,
        height=1400,
        blocks=[
            _block("b1", 0, "First", 1),
            _block("b2", 1, "Second", 1),
            _block("b3", 2, "Third", 1),
        ],
        tables=[],
    )
    document = _document([page])

    previous, following = find_neighbor_blocks(document, 1, "b2")

    assert previous == Neighbor(1, page.blocks[0])
    assert following == Neighbor(1, page.blocks[2])


def test_neighbor_crosses_page_boundary() -> None:
    page1 = Page(
        page_number=1,
        width=1000,
        height=1400,
        blocks=[_block("b1", 0, "First", 1), _block("b2", 1, "Second", 1)],
        tables=[],
    )
    page2 = Page(
        page_number=2,
        width=1000,
        height=1400,
        blocks=[_block("b3", 0, "Third", 2), _block("b4", 1, "Fourth", 2)],
        tables=[],
    )
    document = _document([page1, page2])

    previous, following = find_neighbor_blocks(document, 2, "b3")

    assert previous == Neighbor(1, page1.blocks[1])
    assert following == Neighbor(2, page2.blocks[1])


def test_no_neighbor_at_document_edges() -> None:
    page1 = Page(
        page_number=1,
        width=1000,
        height=1400,
        blocks=[_block("b1", 0, "First", 1), _block("b2", 1, "Second", 1)],
        tables=[],
    )
    page2 = Page(
        page_number=2,
        width=1000,
        height=1400,
        blocks=[_block("b3", 0, "Third", 2)],
        tables=[],
    )
    document = _document([page1, page2])

    first_previous, _ = find_neighbor_blocks(document, 1, "b1")
    _, last_following = find_neighbor_blocks(document, 2, "b3")

    assert first_previous is None
    assert last_following is None


def test_single_block_document_has_no_neighbors() -> None:
    page = Page(
        page_number=1,
        width=1000,
        height=1400,
        blocks=[_block("b1", 0, "Only block", 1)],
        tables=[],
    )
    document = _document([page])

    previous, following = find_neighbor_blocks(document, 1, "b1")

    assert previous is None
    assert following is None


def test_build_chunk_context_marks_target_and_preserves_order() -> None:
    page = Page(
        page_number=1,
        width=1000,
        height=1400,
        blocks=[
            _block("b1", 0, "Before text", 1),
            _block("b2", 1, "Target text", 1),
            _block("b3", 2, "After text", 1),
        ],
        tables=[],
    )
    document = _document([page])

    context = build_chunk_context(document, 1, "b2")

    before_index = context.index("Before text")
    target_index = context.index("[TARGET] paragraph: Target text")
    after_index = context.index("After text")
    assert before_index < target_index < after_index


def test_render_logical_table_skips_repeated_header() -> None:
    fragment_1 = _table(
        "t1",
        [
            _cell("t1-c1", 0, 0, "Model", 1, is_column_header=True),
            _cell("t1-c2", 0, 1, "Qty", 1, is_column_header=True),
            _cell("t1-c3", 1, 0, "A100", 1),
            _cell("t1-c4", 1, 1, "5", 1),
        ],
        1,
    )
    fragment_2 = _table(
        "t2",
        [
            _cell("t2-c1", 0, 0, "Model", 2, is_column_header=True),
            _cell("t2-c2", 0, 1, "Qty", 2, is_column_header=True),
            _cell("t2-c3", 1, 0, "B200", 2),
            _cell("t2-c4", 1, 1, "3", 2),
        ],
        2,
    )
    page1 = Page(page_number=1, width=1000, height=1400, blocks=[], tables=[fragment_1])
    page2 = Page(page_number=2, width=1000, height=1400, blocks=[], tables=[fragment_2])
    document = _document([page1, page2])
    logical_table = LogicalTable(
        logical_table_id="lt1",
        fragment_ids=["t1", "t2"],
        page_numbers=[1, 2],
        source_cell_ids=["t1-c1", "t1-c2", "t1-c3", "t1-c4", "t2-c3", "t2-c4"],
        joins=[{"left_table_id": "t1", "right_table_id": "t2", "column_offset": 0, "score": 0.95}],
    )

    rendered = render_logical_table(document, logical_table)

    assert rendered.count("Model | Qty") == 1
    assert "A100 | 5" in rendered
    assert "B200 | 3" in rendered
    assert "warning" not in rendered


def test_render_logical_table_realigns_columns_using_stitch_offset() -> None:
    # Mirrors a real parsing gap: the continuation fragment's OCR pass missed the
    # "Building" column entirely, so its cells are locally numbered 0..2 instead of
    # 1..3. table_stitching already computes the +1 column_offset needed to place
    # them back under the correct header; rendering must apply it rather than just
    # concatenating the fragment's own column indices.
    fragment_1 = _table(
        "t1",
        [
            _cell("t1-c1", 0, 0, "Building", 1, is_column_header=True),
            _cell("t1-c2", 0, 1, "Quantity", 1, is_column_header=True),
            _cell("t1-c3", 0, 2, "Model", 1, is_column_header=True),
            _cell("t1-c4", 1, 0, "31", 1),
            _cell("t1-c5", 1, 1, "3", 1),
            _cell("t1-c6", 1, 2, "York 1200-ton", 1),
        ],
        1,
    )
    fragment_2 = _table(
        "t2",
        [
            _cell("t2-c1", 0, 0, "1", 2),
            _cell("t2-c2", 0, 1, "York JHJB 1130-ton", 2),
        ],
        2,
    )
    page1 = Page(page_number=1, width=1000, height=1400, blocks=[], tables=[fragment_1])
    page2 = Page(page_number=2, width=1000, height=1400, blocks=[], tables=[fragment_2])
    document = _document([page1, page2])
    logical_table = LogicalTable(
        logical_table_id="lt1",
        fragment_ids=["t1", "t2"],
        page_numbers=[1, 2],
        source_cell_ids=[],
        joins=[{"left_table_id": "t1", "right_table_id": "t2", "column_offset": 1, "score": 0.9}],
    )

    rendered = render_logical_table(document, logical_table)

    assert "Building | Quantity | Model" in rendered
    assert "31 | 3 | York 1200-ton" in rendered
    # Building is genuinely missing for this row: it must stay blank, not absorb "1".
    assert " | 1 | York JHJB 1130-ton" in rendered
    assert "1 | York JHJB 1130-ton |" not in rendered
    assert "warning" not in rendered


def test_render_logical_table_keeps_data_row_mislabelled_as_header() -> None:
    # Real gap found on a scanned continuation page: the OCR table-structure pass
    # flagged an ordinary equipment row as is_column_header=True even though its text
    # has nothing to do with the real header. A naive "skip flagged rows" rule would
    # silently drop this chiller record from the final LLM context.
    fragment_1 = _table(
        "t1",
        [
            _cell("t1-c1", 0, 0, "Building", 1, is_column_header=True),
            _cell("t1-c2", 0, 1, "Quantity", 1, is_column_header=True),
            _cell("t1-c3", 1, 0, "2", 1),
            _cell("t1-c4", 1, 1, "2", 1),
        ],
        1,
    )
    fragment_2 = _table(
        "t2",
        [
            _cell("t2-c1", 0, 0, "3", 2, is_column_header=True),
            _cell("t2-c2", 0, 1, "York 1200-ton", 2, is_column_header=True),
            _cell("t2-c3", 1, 0, "1", 2),
            _cell("t2-c4", 1, 1, "York JHJB 1130-ton", 2),
        ],
        2,
    )
    page1 = Page(page_number=1, width=1000, height=1400, blocks=[], tables=[fragment_1])
    page2 = Page(page_number=2, width=1000, height=1400, blocks=[], tables=[fragment_2])
    document = _document([page1, page2])
    logical_table = LogicalTable(
        logical_table_id="lt1",
        fragment_ids=["t1", "t2"],
        page_numbers=[1, 2],
        source_cell_ids=[],
        joins=[{"left_table_id": "t1", "right_table_id": "t2", "column_offset": 0, "score": 0.9}],
    )

    rendered = render_logical_table(document, logical_table)

    assert "3 | York 1200-ton" in rendered
    assert "1 | York JHJB 1130-ton" in rendered


def test_render_logical_table_warns_when_alignment_is_unknown() -> None:
    fragment_1 = _table(
        "t1",
        [_cell("t1-c1", 0, 0, "Model", 1, is_column_header=True), _cell("t1-c2", 1, 0, "A100", 1)],
        1,
    )
    fragment_2 = _table("t2", [_cell("t2-c1", 0, 0, "B200", 2)], 2)
    page1 = Page(page_number=1, width=1000, height=1400, blocks=[], tables=[fragment_1])
    page2 = Page(page_number=2, width=1000, height=1400, blocks=[], tables=[fragment_2])
    document = _document([page1, page2])
    logical_table = LogicalTable(
        logical_table_id="lt1",
        fragment_ids=["t1", "t2"],
        page_numbers=[1, 2],
        source_cell_ids=[],
        joins=[],
    )

    rendered = render_logical_table(document, logical_table)

    assert "warning: column alignment for t2 could not be determined" in rendered


def test_render_logical_table_warns_on_low_confidence_merge() -> None:
    fragment_1 = _table(
        "t1",
        [_cell("t1-c1", 0, 0, "Model", 1, is_column_header=True), _cell("t1-c2", 1, 0, "A100", 1)],
        1,
    )
    fragment_2 = _table("t2", [_cell("t2-c1", 0, 0, "B200", 2)], 2)
    page1 = Page(page_number=1, width=1000, height=1400, blocks=[], tables=[fragment_1])
    page2 = Page(page_number=2, width=1000, height=1400, blocks=[], tables=[fragment_2])
    document = _document([page1, page2])
    logical_table = LogicalTable(
        logical_table_id="lt1",
        fragment_ids=["t1", "t2"],
        page_numbers=[1, 2],
        source_cell_ids=[],
        joins=[{"left_table_id": "t1", "right_table_id": "t2", "column_offset": 0, "score": 0.80}],
    )

    rendered = render_logical_table(document, logical_table)

    assert "warning: low-confidence merge for t2" in rendered
    assert "0.800" in rendered
    assert "B200" in rendered  # the row itself still renders, just with a caveat


def test_render_logical_table_no_warning_for_confident_merge() -> None:
    fragment_1 = _table(
        "t1",
        [_cell("t1-c1", 0, 0, "Model", 1, is_column_header=True), _cell("t1-c2", 1, 0, "A100", 1)],
        1,
    )
    fragment_2 = _table("t2", [_cell("t2-c1", 0, 0, "B200", 2)], 2)
    page1 = Page(page_number=1, width=1000, height=1400, blocks=[], tables=[fragment_1])
    page2 = Page(page_number=2, width=1000, height=1400, blocks=[], tables=[fragment_2])
    document = _document([page1, page2])
    logical_table = LogicalTable(
        logical_table_id="lt1",
        fragment_ids=["t1", "t2"],
        page_numbers=[1, 2],
        source_cell_ids=[],
        joins=[{"left_table_id": "t1", "right_table_id": "t2", "column_offset": 0, "score": 0.92}],
    )

    rendered = render_logical_table(document, logical_table)

    assert "warning" not in rendered


def test_index_logical_tables_maps_every_fragment_id() -> None:
    logical_table = LogicalTable(
        logical_table_id="lt1",
        fragment_ids=["t1", "t2"],
        page_numbers=[1, 2],
        source_cell_ids=[],
        joins=[],
    )
    stitch_result = StitchResult(source_document_id="doc", decisions=[], logical_tables=[logical_table])

    index = index_logical_tables(stitch_result)

    assert index["t1"] is logical_table
    assert index["t2"] is logical_table


def test_build_llm_context_routes_block_unit_id_to_chunk_context() -> None:
    page = Page(
        page_number=1,
        width=1000,
        height=1400,
        blocks=[
            _block("b1", 0, "Before text", 1),
            _block("b2", 1, "Target text", 1),
        ],
        tables=[],
    )
    document = _document([page], document_id="doc")
    stitch_result = StitchResult(source_document_id="doc", decisions=[], logical_tables=[])

    context = build_llm_context(document, stitch_result, "doc:b2")

    assert "[TARGET] paragraph: Target text" in context
    assert "Before text" in context


def test_build_llm_context_routes_table_row_unit_id_to_stitched_table() -> None:
    fragment_1 = _table(
        "t1",
        [
            _cell("t1-c1", 0, 0, "Model", 1, is_column_header=True),
            _cell("t1-c2", 1, 0, "A100", 1),
        ],
        1,
    )
    fragment_2 = _table(
        "t2",
        [_cell("t2-c1", 0, 0, "B200", 2)],
        2,
    )
    page1 = Page(page_number=1, width=1000, height=1400, blocks=[], tables=[fragment_1])
    page2 = Page(page_number=2, width=1000, height=1400, blocks=[], tables=[fragment_2])
    document = _document([page1, page2], document_id="doc")
    logical_table = LogicalTable(
        logical_table_id="lt1",
        fragment_ids=["t1", "t2"],
        page_numbers=[1, 2],
        source_cell_ids=[],
        joins=[],
    )
    stitch_result = StitchResult(source_document_id="doc", decisions=[], logical_tables=[logical_table])

    context = build_llm_context(document, stitch_result, "doc:t1-r1")

    assert "A100" in context
    assert "B200" in context
    assert "[Stitched table across pages [1, 2]]" in context


def test_build_llm_context_falls_back_to_single_fragment_when_not_stitched() -> None:
    fragment = _table(
        "t1",
        [
            _cell("t1-c1", 0, 0, "Model", 1, is_column_header=True),
            _cell("t1-c2", 1, 0, "A100", 1),
        ],
        1,
    )
    page = Page(page_number=1, width=1000, height=1400, blocks=[], tables=[fragment])
    document = _document([page], document_id="doc")
    stitch_result = StitchResult(source_document_id="doc", decisions=[], logical_tables=[])

    context = build_llm_context(document, stitch_result, "doc:t1-r1")

    assert "Model" in context
    assert "A100" in context
    assert find_table_fragment(document, "t1") is fragment
