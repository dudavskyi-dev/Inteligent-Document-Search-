from __future__ import annotations

import hashlib
import importlib.metadata
import os
import time
from pathlib import Path
from typing import Any

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
from benchmark.resources import ResourceMonitor

LABEL_MAP = {
    "title": "title",
    "section_header": "heading",
    "heading": "heading",
    "paragraph": "paragraph",
    "text": "paragraph",
    "list_item": "list",
    "page_header": "header",
    "page_footer": "footer",
    "picture": "image",
}


def configure_docling_environment(project_root: Path) -> None:
    cache = project_root / ".cache"
    os.environ.setdefault("HF_HOME", str(cache / "huggingface"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(cache / "huggingface" / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(cache / "huggingface" / "transformers"))
    os.environ.setdefault("DOCLING_CACHE_DIR", str(cache / "docling"))
    os.environ.setdefault("DOCLING_INFERENCE_COMPILE_TORCH_MODELS", "false")
    os.environ.setdefault("DOCLING_PERF_PAGE_BATCH_SIZE", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bbox(raw: dict[str, Any], width: float, height: float) -> BoundingBox:
    origin = raw.get("coord_origin", "TOPLEFT")
    left = float(raw["l"])
    right = float(raw["r"])
    if origin == "BOTTOMLEFT":
        top = height - float(raw["t"])
        bottom = height - float(raw["b"])
    else:
        top = float(raw["t"])
        bottom = float(raw["b"])
    x1, x2 = sorted((left / width, right / width))
    y1, y2 = sorted((top / height, bottom / height))
    return BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)


def _provenance(
    raw_items: list[dict[str, Any]], pages: dict[int, tuple[float, float]], parser: str
) -> list[Provenance]:
    result: list[Provenance] = []
    for raw in raw_items:
        page_number = int(raw["page_no"])
        width, height = pages[page_number]
        result.append(
            Provenance(
                page_number=page_number,
                bbox=_bbox(raw["bbox"], width, height),
                parser=parser,
            )
        )
    return result


def normalize_docling(
    raw: dict[str, Any], source: Path, elapsed_seconds: float, peak_memory_mb: float
) -> CanonicalDocument:
    parser_name = "docling"
    page_sizes = {
        int(item["page_no"]): (float(item["size"]["width"]), float(item["size"]["height"]))
        for item in raw["pages"].values()
    }
    pages = {
        page_number: Page(
            page_number=page_number,
            width=width,
            height=height,
            blocks=[],
            tables=[],
        )
        for page_number, (width, height) in page_sizes.items()
    }

    reading_order: dict[int, int] = {page_number: 0 for page_number in pages}
    for index, item in enumerate(raw.get("texts", [])):
        provenance = _provenance(item.get("prov", []), page_sizes, parser_name)
        if not provenance:
            continue
        page_number = provenance[0].page_number
        block_type = LABEL_MAP.get(item.get("label", ""), "other")
        pages[page_number].blocks.append(
            Block(
                block_id=f"p{page_number}-b{index}",
                type=block_type,
                text=item.get("text", item.get("orig", "")),
                reading_order=reading_order[page_number],
                provenance=provenance,
            )
        )
        reading_order[page_number] += 1

    for table_index, item in enumerate(raw.get("tables", [])):
        provenance = _provenance(item.get("prov", []), page_sizes, parser_name)
        if not provenance:
            continue
        page_number = provenance[0].page_number
        cells: list[TableCell] = []
        for cell_index, cell in enumerate(item.get("data", {}).get("table_cells", [])):
            cell_provenance = [
                Provenance(
                    page_number=page_number,
                    bbox=_bbox(cell["bbox"], *page_sizes[page_number]),
                    parser=parser_name,
                )
            ]
            cells.append(
                TableCell(
                    cell_id=f"p{page_number}-t{table_index}-c{cell_index}",
                    row=int(cell.get("start_row_offset_idx", 0)),
                    column=int(cell.get("start_col_offset_idx", 0)),
                    row_span=int(cell.get("row_span", 1)),
                    column_span=int(cell.get("col_span", 1)),
                    text=cell.get("text", ""),
                    is_column_header=bool(cell.get("column_header", False)),
                    is_row_header=bool(cell.get("row_header", False)),
                    provenance=cell_provenance,
                )
            )
        captions = item.get("captions", [])
        caption = captions[0].get("text") if captions and isinstance(captions[0], dict) else None
        pages[page_number].tables.append(
            TableFragment(
                table_id=f"p{page_number}-t{table_index}",
                caption=caption,
                cells=cells,
                provenance=provenance,
            )
        )

    return CanonicalDocument(
        document_id=source.stem,
        source_filename=source.name,
        sha256=file_sha256(source),
        parser_run=ParserRun(
            strategy="docling_native",
            parser_versions={"docling": importlib.metadata.version("docling")},
            elapsed_seconds=elapsed_seconds,
            peak_memory_mb=peak_memory_mb,
            page_routes={page_number: "docling_native" for page_number in pages},
        ),
        pages=[pages[number] for number in sorted(pages)],
    )


def parse_docling_native(
    source: Path, project_root: Path, page_range: tuple[int, int] | None = None
) -> CanonicalDocument:
    configure_docling_environment(project_root)
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    kwargs = {"page_range": page_range} if page_range else {}
    started = time.perf_counter()
    with ResourceMonitor() as resources:
        conversion = converter.convert(source, **kwargs)
    elapsed = time.perf_counter() - started
    return normalize_docling(
        conversion.document.export_to_dict(), source, elapsed, resources.peak_memory_mb
    )
