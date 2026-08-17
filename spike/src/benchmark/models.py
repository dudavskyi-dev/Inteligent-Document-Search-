from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Normalized page coordinates in the inclusive range 0..1."""

    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)


class Provenance(BaseModel):
    page_number: int = Field(ge=1)
    bbox: BoundingBox
    parser: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class Block(BaseModel):
    block_id: str
    type: Literal[
        "title",
        "heading",
        "paragraph",
        "list",
        "table",
        "image",
        "header",
        "footer",
        "other",
    ]
    text: str = ""
    reading_order: int = Field(ge=0)
    section_path: list[str] = Field(default_factory=list)
    provenance: list[Provenance]


class TableCell(BaseModel):
    cell_id: str
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    text: str = ""
    is_column_header: bool = False
    is_row_header: bool = False
    provenance: list[Provenance]


class TableFragment(BaseModel):
    table_id: str
    caption: str | None = None
    cells: list[TableCell]
    provenance: list[Provenance]


class Page(BaseModel):
    page_number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    blocks: list[Block]
    tables: list[TableFragment]


class ParserRun(BaseModel):
    strategy: Literal["docling_native", "full_raster", "hybrid", "gcp"]
    parser_versions: dict[str, str]
    rendering_dpi: int | None = None
    elapsed_seconds: float = Field(ge=0)
    timings: dict[str, float] = Field(default_factory=dict)
    peak_memory_mb: float | None = Field(default=None, ge=0)
    page_routes: dict[int, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class CanonicalDocument(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    document_id: str
    source_filename: str
    sha256: str
    parser_run: ParserRun
    pages: list[Page]
