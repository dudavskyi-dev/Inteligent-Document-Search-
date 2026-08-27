from __future__ import annotations

import re

from benchmark.context_assembly import (
    find_neighbor_blocks,
    find_table_fragment,
    index_logical_tables,
)
from benchmark.models import CanonicalDocument
from benchmark.table_stitching import StitchResult

# Mirrors the private _TABLE_ROW_SUFFIX in benchmark.context_assembly (not imported
# directly to avoid depending on that module's private internals from outside spike/).
_TABLE_ROW_SUFFIX = re.compile(r"^(?P<table_id>.+)-r(?P<row_number>\d+)$")


def collect_evidence_ids(
    document: CanonicalDocument, stitch_result: StitchResult, unit_id: str
) -> list[str]:
    """Mirror build_llm_context()'s own dispatch logic to report which real block/cell
    ids the assembled context text was built from, so the LLM prompt can cite them as
    ALLOWED_EVIDENCE_IDS. This does not re-render any text, only re-derives the id list.
    """
    _, separator, remainder = unit_id.partition(":")
    if not separator:
        raise ValueError(f"Malformed unit_id (missing document prefix): {unit_id!r}")

    table_match = _TABLE_ROW_SUFFIX.match(remainder)
    if table_match:
        table_id = table_match.group("table_id")
        logical_table = index_logical_tables(stitch_result).get(table_id)
        if logical_table is not None:
            return list(logical_table.source_cell_ids)
        fragment = find_table_fragment(document, table_id)
        return [cell.cell_id for cell in fragment.cells]

    block_id = remainder
    page_number = next(
        page.page_number
        for page in document.pages
        for block in page.blocks
        if block.block_id == block_id
    )
    previous, following = find_neighbor_blocks(document, page_number, block_id)
    ids = [block_id]
    if previous is not None:
        ids.append(previous.block.block_id)
    if following is not None:
        ids.append(following.block.block_id)
    return ids
