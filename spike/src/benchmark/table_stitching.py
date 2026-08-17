from __future__ import annotations

import re
from collections import defaultdict
from statistics import mean

from pydantic import BaseModel, Field

from benchmark.models import Block, CanonicalDocument, Page, TableFragment


class StitchFeatures(BaseModel):
    left_bottom_score: float = Field(ge=0, le=1)
    right_top_score: float = Field(ge=0, le=1)
    horizontal_overlap: float = Field(ge=0, le=1)
    column_count_similarity: float = Field(ge=0, le=1)
    column_alignment: float = Field(ge=0, le=1)
    column_offset: int
    header_similarity: float = Field(ge=0, le=1)
    left_has_trailing_content: bool
    right_has_leading_content: bool


class StitchDecision(BaseModel):
    left_page: int
    right_page: int
    left_table_id: str
    right_table_id: str
    score: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    predicted_merge: bool
    features: StitchFeatures
    reasons: list[str]


class LogicalTable(BaseModel):
    logical_table_id: str
    fragment_ids: list[str]
    page_numbers: list[int]
    source_cell_ids: list[str]
    joins: list[dict[str, int | str | float]]


class StitchResult(BaseModel):
    schema_version: str = "1.0"
    source_document_id: str
    decisions: list[StitchDecision]
    logical_tables: list[LogicalTable]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _table_bounds(table: TableFragment) -> tuple[float, float, float, float]:
    boxes = [provenance.bbox for provenance in table.provenance]
    if not boxes:
        boxes = [
            provenance.bbox
            for cell in table.cells
            for provenance in cell.provenance
        ]
    if not boxes:
        raise ValueError(f"Table {table.table_id} has no bounding-box provenance.")
    return (
        min(box.x1 for box in boxes),
        min(box.y1 for box in boxes),
        max(box.x2 for box in boxes),
        max(box.y2 for box in boxes),
    )


def _horizontal_overlap(left: TableFragment, right: TableFragment) -> float:
    left_x1, _, left_x2, _ = _table_bounds(left)
    right_x1, _, right_x2, _ = _table_bounds(right)
    intersection = max(0.0, min(left_x2, right_x2) - max(left_x1, right_x1))
    smaller_width = min(left_x2 - left_x1, right_x2 - right_x1)
    return _clamp(intersection / smaller_width) if smaller_width > 0 else 0.0


def _column_centers(table: TableFragment) -> dict[int, float]:
    centers: dict[int, list[float]] = defaultdict(list)
    for cell in table.cells:
        if cell.provenance:
            bbox = cell.provenance[0].bbox
            centers[cell.column].append((bbox.x1 + bbox.x2) / 2)
    return {column: mean(values) for column, values in centers.items() if values}


def _best_column_alignment(left: TableFragment, right: TableFragment) -> tuple[float, int]:
    left_centers = _column_centers(left)
    right_centers = _column_centers(right)
    if not left_centers or not right_centers:
        return 0.0, 0

    best_score = 0.0
    best_offset = 0
    maximum_shift = max(len(left_centers), len(right_centers))
    for offset in range(-maximum_shift, maximum_shift + 1):
        similarities = []
        for right_column, right_center in right_centers.items():
            left_column = right_column + offset
            if left_column in left_centers:
                distance = abs(left_centers[left_column] - right_center)
                similarities.append(_clamp(1.0 - distance / 0.12))
        if not similarities:
            continue
        coverage = min(1.0, len(similarities) / min(2, len(right_centers)))
        score = mean(similarities) * coverage
        if score > best_score:
            best_score = score
            best_offset = offset
    return _clamp(best_score), best_offset


def _header_tokens(table: TableFragment) -> set[str]:
    text = " ".join(cell.text for cell in table.cells if cell.is_column_header)
    return set(re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE))


def _header_similarity(left: TableFragment, right: TableFragment) -> float:
    left_tokens = _header_tokens(left)
    right_tokens = _header_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _meaningful_block(block: Block) -> bool:
    return block.type not in {"header", "footer"} and bool(block.text.strip())


def _has_content_after(page: Page, y: float) -> bool:
    return any(
        _meaningful_block(block)
        and any(provenance.bbox.y1 > y + 0.01 for provenance in block.provenance)
        for block in page.blocks
    )


def _has_content_before(page: Page, y: float) -> bool:
    return any(
        _meaningful_block(block)
        and any(provenance.bbox.y2 < y - 0.01 for provenance in block.provenance)
        for block in page.blocks
    )


def decide_pair(
    left_page: Page,
    left: TableFragment,
    right_page: Page,
    right: TableFragment,
    threshold: float = 0.72,
) -> StitchDecision:
    _, _, _, left_y2 = _table_bounds(left)
    _, right_y1, _, _ = _table_bounds(right)
    left_bottom_score = _clamp((left_y2 - 0.70) / 0.15)
    right_top_score = _clamp((0.22 - right_y1) / 0.15)
    overlap = _horizontal_overlap(left, right)
    left_columns = {cell.column for cell in left.cells}
    right_columns = {cell.column for cell in right.cells}
    column_count_similarity = (
        min(len(left_columns), len(right_columns))
        / max(len(left_columns), len(right_columns))
        if left_columns and right_columns
        else 0.0
    )
    column_alignment, column_offset = _best_column_alignment(left, right)
    header_similarity = _header_similarity(left, right)
    left_has_trailing_content = _has_content_after(left_page, left_y2)
    right_has_leading_content = _has_content_before(right_page, right_y1)

    score = (
        0.45 * left_bottom_score
        + 0.20 * right_top_score
        + 0.15 * overlap
        + 0.10 * column_alignment
        + 0.05 * column_count_similarity
        + 0.05 * header_similarity
    )
    if left_has_trailing_content:
        score -= 0.35
    if right_has_leading_content:
        score -= 0.15
    score = _clamp(score)

    boundary_gate = left_bottom_score >= 0.75 and right_top_score >= 0.65
    predicted_merge = score >= threshold and boundary_gate and not left_has_trailing_content
    reasons = [
        f"left_bottom={left_bottom_score:.3f}",
        f"right_top={right_top_score:.3f}",
        f"horizontal_overlap={overlap:.3f}",
        f"column_alignment={column_alignment:.3f} offset={column_offset:+d}",
    ]
    if left_has_trailing_content:
        reasons.append("guard: meaningful content follows the left table")
    if right_has_leading_content:
        reasons.append("penalty: meaningful content precedes the right table")
    if not boundary_gate:
        reasons.append("guard: table fragments do not meet both page-boundary thresholds")

    return StitchDecision(
        left_page=left_page.page_number,
        right_page=right_page.page_number,
        left_table_id=left.table_id,
        right_table_id=right.table_id,
        score=round(score, 6),
        threshold=threshold,
        predicted_merge=predicted_merge,
        features=StitchFeatures(
            left_bottom_score=left_bottom_score,
            right_top_score=right_top_score,
            horizontal_overlap=overlap,
            column_count_similarity=column_count_similarity,
            column_alignment=column_alignment,
            column_offset=column_offset,
            header_similarity=header_similarity,
            left_has_trailing_content=left_has_trailing_content,
            right_has_leading_content=right_has_leading_content,
        ),
        reasons=reasons,
    )


def _candidate_pairs(
    document: CanonicalDocument,
) -> list[tuple[Page, TableFragment, Page, TableFragment]]:
    pages = {page.page_number: page for page in document.pages}
    candidates = []
    for page_number in sorted(pages):
        right_page = pages.get(page_number + 1)
        left_page = pages[page_number]
        if right_page is None or not left_page.tables or not right_page.tables:
            continue
        left_table = max(left_page.tables, key=lambda table: _table_bounds(table)[3])
        right_table = min(right_page.tables, key=lambda table: _table_bounds(table)[1])
        candidates.append((left_page, left_table, right_page, right_table))
    return candidates


def stitch_document(document: CanonicalDocument, threshold: float = 0.72) -> StitchResult:
    decisions = [
        decide_pair(left_page, left, right_page, right, threshold)
        for left_page, left, right_page, right in _candidate_pairs(document)
    ]

    tables = [table for page in document.pages for table in page.tables]
    table_by_id = {table.table_id: table for table in tables}
    page_by_table = {
        table.table_id: page.page_number
        for page in document.pages
        for table in page.tables
    }
    parent = {table_id: table_id for table_id in table_by_id}

    def find(table_id: str) -> str:
        while parent[table_id] != table_id:
            parent[table_id] = parent[parent[table_id]]
            table_id = parent[table_id]
        return table_id

    def union(left_id: str, right_id: str) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root != right_root:
            parent[right_root] = left_root

    for decision in decisions:
        if decision.predicted_merge:
            union(decision.left_table_id, decision.right_table_id)

    groups: dict[str, list[str]] = defaultdict(list)
    for table_id in table_by_id:
        groups[find(table_id)].append(table_id)

    logical_tables: list[LogicalTable] = []
    sorted_groups = sorted(
        groups.values(),
        key=lambda ids: min((page_by_table[table_id], table_id) for table_id in ids),
    )
    for index, fragment_ids in enumerate(sorted_groups, start=1):
        ordered_ids = sorted(fragment_ids, key=lambda table_id: (page_by_table[table_id], table_id))
        joins = [
            {
                "left_table_id": decision.left_table_id,
                "right_table_id": decision.right_table_id,
                "column_offset": decision.features.column_offset,
                "score": decision.score,
            }
            for decision in decisions
            if decision.predicted_merge
            and decision.left_table_id in ordered_ids
            and decision.right_table_id in ordered_ids
        ]
        logical_tables.append(
            LogicalTable(
                logical_table_id=f"lt-{index:03d}",
                fragment_ids=ordered_ids,
                page_numbers=sorted({page_by_table[table_id] for table_id in ordered_ids}),
                source_cell_ids=[
                    cell.cell_id
                    for table_id in ordered_ids
                    for cell in table_by_id[table_id].cells
                ],
                joins=joins,
            )
        )

    return StitchResult(
        source_document_id=document.document_id,
        decisions=decisions,
        logical_tables=logical_tables,
    )
