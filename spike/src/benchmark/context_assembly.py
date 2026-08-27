from __future__ import annotations

import re
from collections import defaultdict
from typing import NamedTuple

from benchmark.models import Block, CanonicalDocument, Page, TableCell, TableFragment
from benchmark.table_stitching import LogicalTable, StitchResult

# Mirrors the unit_id suffix built for table rows in retrieval.build_records():
# f"{document.document_id}:{table.table_id}-r{row_number}".
_TABLE_ROW_SUFFIX = re.compile(r"^(?P<table_id>.+)-r(?P<row_number>\d+)$")


class Neighbor(NamedTuple):
    page_number: int
    block: Block


def _page_by_number(document: CanonicalDocument, page_number: int) -> Page:
    for page in document.pages:
        if page.page_number == page_number:
            return page
    raise KeyError(f"Document {document.document_id!r} has no page {page_number}.")


def find_neighbor_blocks(
    document: CanonicalDocument, page_number: int, block_id: str
) -> tuple[Neighbor | None, Neighbor | None]:
    pages_by_number = {page.page_number: page for page in document.pages}
    page = pages_by_number.get(page_number)
    if page is None:
        raise KeyError(f"Document {document.document_id!r} has no page {page_number}.")
    ordered = sorted(page.blocks, key=lambda block: block.reading_order)
    index = next(
        (position for position, block in enumerate(ordered) if block.block_id == block_id),
        None,
    )
    if index is None:
        raise KeyError(f"Page {page_number} has no block {block_id!r}.")

    if index > 0:
        previous: Neighbor | None = Neighbor(page_number, ordered[index - 1])
    else:
        previous_page = pages_by_number.get(page_number - 1)
        previous_blocks = (
            sorted(previous_page.blocks, key=lambda block: block.reading_order)
            if previous_page is not None
            else []
        )
        previous = Neighbor(page_number - 1, previous_blocks[-1]) if previous_blocks else None

    if index < len(ordered) - 1:
        following: Neighbor | None = Neighbor(page_number, ordered[index + 1])
    else:
        next_page = pages_by_number.get(page_number + 1)
        next_blocks = (
            sorted(next_page.blocks, key=lambda block: block.reading_order)
            if next_page is not None
            else []
        )
        following = Neighbor(page_number + 1, next_blocks[0]) if next_blocks else None

    return previous, following


def _current_heading(page: Page, before_reading_order: int) -> str:
    heading = ""
    for block in sorted(page.blocks, key=lambda item: item.reading_order):
        if block.reading_order >= before_reading_order:
            break
        if block.type in {"title", "heading"} and block.text.strip():
            heading = block.text.strip()
    return heading


def _format_block_text(
    document: CanonicalDocument, page_number: int, block: Block, *, is_target: bool
) -> str:
    page = _page_by_number(document, page_number)
    section = " > ".join(block.section_path) or _current_heading(page, block.reading_order)
    lines = [f"Document: {document.source_filename}", f"Page: {page_number}"]
    if section:
        lines.append(f"Section: {section}")
    label = "[TARGET] " if is_target else ""
    lines.append(f"{label}{block.type}: {block.text.strip()}")
    return "\n".join(lines)


def build_chunk_context(document: CanonicalDocument, page_number: int, block_id: str) -> str:
    page = _page_by_number(document, page_number)
    target = next((block for block in page.blocks if block.block_id == block_id), None)
    if target is None:
        raise KeyError(f"Page {page_number} has no block {block_id!r}.")

    previous, following = find_neighbor_blocks(document, page_number, block_id)

    parts: list[str] = []
    if previous is not None:
        parts.append(_format_block_text(document, previous.page_number, previous.block, is_target=False))
    parts.append(_format_block_text(document, page_number, target, is_target=True))
    if following is not None:
        parts.append(_format_block_text(document, following.page_number, following.block, is_target=False))
    return "\n\n".join(parts)


def index_logical_tables(stitch_result: StitchResult) -> dict[str, LogicalTable]:
    index: dict[str, LogicalTable] = {}
    for logical_table in stitch_result.logical_tables:
        for fragment_id in logical_table.fragment_ids:
            index[fragment_id] = logical_table
    return index


def find_table_fragment(document: CanonicalDocument, table_id: str) -> TableFragment:
    for page in document.pages:
        for table in page.tables:
            if table.table_id == table_id:
                return table
    raise KeyError(f"Document {document.document_id!r} has no table {table_id!r}.")


def _page_number_for_table(document: CanonicalDocument, table_id: str) -> int:
    for page in document.pages:
        for table in page.tables:
            if table.table_id == table_id:
                return page.page_number
    raise KeyError(f"Document {document.document_id!r} has no table {table_id!r}.")


def _page_number_for_block(document: CanonicalDocument, block_id: str) -> int:
    for page in document.pages:
        for block in page.blocks:
            if block.block_id == block_id:
                return page.page_number
    raise KeyError(f"Document {document.document_id!r} has no block {block_id!r}.")


def _cumulative_column_shifts(logical_table: LogicalTable) -> dict[str, int]:
    """Map each fragment_id with a known alignment to its column offset.

    table_stitching.decide_pair() already computes, per adjacent pair, the column_offset
    such that left_column = right_column + offset (see _best_column_alignment). Chaining
    these pairwise offsets recovers the correct column for a continuation fragment even
    when the source parser numbered its columns locally (e.g. a column the OCR pass
    missed on a later page, which otherwise silently shifts every later column left).

    A fragment_id is absent from the result if its offset (or an earlier link in its
    chain) is unknown, so callers can tell "shift is 0" apart from "shift is unknown".
    """
    offset_by_right = {join["right_table_id"]: join["column_offset"] for join in logical_table.joins}
    shifts: dict[str, int] = {}
    cumulative = 0
    for index, fragment_id in enumerate(logical_table.fragment_ids):
        if index == 0:
            shifts[fragment_id] = 0
            continue
        if fragment_id not in offset_by_right:
            break  # unknown link breaks the chain; later fragments are unknown too
        cumulative += offset_by_right[fragment_id]
        shifts[fragment_id] = cumulative
    return shifts


def _render_fragments(
    document: CanonicalDocument,
    fragment_ids: list[str],
    page_numbers: list[int],
    column_shifts: dict[str, int] | None = None,
) -> str:
    shifts = column_shifts or {}
    fragments = [find_table_fragment(document, fragment_id) for fragment_id in fragment_ids]

    positions = [
        cell.column + shifts.get(fragment.table_id, 0)
        for fragment in fragments
        for cell in fragment.cells
    ]
    lines = [f"[Stitched table across pages {page_numbers}]"]
    if not positions:
        return "\n".join(lines)
    min_position = min(positions)
    column_count = max(positions) - min_position + 1

    for position, fragment in enumerate(fragments):
        if position > 0 and fragment.table_id not in shifts:
            lines.append(
                f"[warning: column alignment for {fragment.table_id} could not be "
                "determined; values below may be shifted]"
            )
        shift = shifts.get(fragment.table_id, 0)
        by_row: dict[int, list[TableCell]] = defaultdict(list)
        for cell in fragment.cells:
            by_row[cell.row].append(cell)
        for row_number in sorted(by_row):
            cells = by_row[row_number]
            if position > 0 and any(cell.is_column_header for cell in cells):
                continue
            values = [""] * column_count
            for cell in cells:
                text = cell.text.strip()
                if text:
                    values[cell.column + shift - min_position] = text
            if any(values):
                lines.append(" | ".join(values))
    return "\n".join(lines)


def render_logical_table(document: CanonicalDocument, logical_table: LogicalTable) -> str:
    shifts = _cumulative_column_shifts(logical_table)
    return _render_fragments(document, logical_table.fragment_ids, logical_table.page_numbers, shifts)


def build_llm_context(
    document: CanonicalDocument, stitch_result: StitchResult, unit_id: str
) -> str:
    _, separator, remainder = unit_id.partition(":")
    if not separator:
        raise ValueError(f"Malformed unit_id (missing document prefix): {unit_id!r}")

    table_match = _TABLE_ROW_SUFFIX.match(remainder)
    if table_match:
        table_id = table_match.group("table_id")
        logical_table = index_logical_tables(stitch_result).get(table_id)
        if logical_table is not None:
            return render_logical_table(document, logical_table)
        return _render_fragments(document, [table_id], [_page_number_for_table(document, table_id)])

    block_id = remainder
    page_number = _page_number_for_block(document, block_id)
    return build_chunk_context(document, page_number, block_id)
