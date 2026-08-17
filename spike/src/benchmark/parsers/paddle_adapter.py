from __future__ import annotations

import importlib.metadata
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

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
from benchmark.parsers.docling_adapter import file_sha256
from benchmark.parsers.paddle_runtime import import_paddle_locally
from benchmark.resources import ResourceMonitor

LABEL_MAP = {
    "doc_title": "title",
    "paragraph_title": "heading",
    "text": "paragraph",
    "content": "paragraph",
    "abstract": "paragraph",
    "reference": "paragraph",
    "reference_content": "paragraph",
    "header": "header",
    "footer": "footer",
    "image": "image",
}


def _box(values: list[float], width: float, height: float) -> BoundingBox:
    x1, y1, x2, y2 = values
    return BoundingBox(x1=x1 / width, y1=y1 / height, x2=x2 / width, y2=y2 / height)


def _html_cells(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    result: list[dict[str, Any]] = []
    occupied: set[tuple[int, int]] = set()
    for row_index, row in enumerate(soup.find_all("tr")):
        column = 0
        for element in row.find_all(["td", "th"], recursive=False):
            while (row_index, column) in occupied:
                column += 1
            row_span = int(element.get("rowspan", 1))
            column_span = int(element.get("colspan", 1))
            result.append(
                {
                    "row": row_index,
                    "column": column,
                    "row_span": row_span,
                    "column_span": column_span,
                    "text": element.get_text(" ", strip=True),
                    "is_column_header": element.name == "th" or row_index == 0,
                }
            )
            for row_offset in range(row_span):
                for column_offset in range(column_span):
                    occupied.add((row_index + row_offset, column + column_offset))
            column += column_span
    return result


def normalize_paddle_page(raw: dict[str, Any], page_number: int) -> Page:
    result = raw.get("res", raw)
    width = float(result["width"])
    height = float(result["height"])
    page = Page(page_number=page_number, width=width, height=height, blocks=[], tables=[])

    for fallback_order, item in enumerate(result.get("parsing_res_list", [])):
        label = item.get("block_label", "")
        if label == "table":
            continue
        bbox = _box([float(value) for value in item["block_bbox"]], width, height)
        page.blocks.append(
            Block(
                block_id=f"p{page_number}-b{item.get('block_id', fallback_order)}",
                type=LABEL_MAP.get(label, "other"),
                text=item.get("block_content", "").strip(),
                reading_order=int(item.get("block_order") or fallback_order),
                provenance=[
                    Provenance(page_number=page_number, bbox=bbox, parser="paddle_ppstructurev3")
                ],
            )
        )

    table_blocks = [
        item for item in result.get("parsing_res_list", []) if item.get("block_label") == "table"
    ]
    for table_index, table in enumerate(result.get("table_res_list", [])):
        html_cells = _html_cells(table.get("pred_html", ""))
        cell_boxes = table.get("cell_box_list", [])
        cells: list[TableCell] = []
        for cell_index, cell in enumerate(html_cells):
            if cell_index >= len(cell_boxes):
                break
            bbox = _box([float(value) for value in cell_boxes[cell_index]], width, height)
            cells.append(
                TableCell(
                    cell_id=f"p{page_number}-t{table_index}-c{cell_index}",
                    row=cell["row"],
                    column=cell["column"],
                    row_span=cell["row_span"],
                    column_span=cell["column_span"],
                    text=cell["text"],
                    is_column_header=cell["is_column_header"],
                    provenance=[
                        Provenance(
                            page_number=page_number,
                            bbox=bbox,
                            parser="paddle_ppstructurev3",
                        )
                    ],
                )
            )
        if table_index < len(table_blocks):
            table_bbox = _box(
                [float(value) for value in table_blocks[table_index]["block_bbox"]], width, height
            )
        elif cells:
            table_bbox = BoundingBox(
                x1=min(cell.provenance[0].bbox.x1 for cell in cells),
                y1=min(cell.provenance[0].bbox.y1 for cell in cells),
                x2=max(cell.provenance[0].bbox.x2 for cell in cells),
                y2=max(cell.provenance[0].bbox.y2 for cell in cells),
            )
        else:
            continue
        page.tables.append(
            TableFragment(
                table_id=f"p{page_number}-t{table_index}",
                cells=cells,
                provenance=[
                    Provenance(
                        page_number=page_number,
                        bbox=table_bbox,
                        parser="paddle_ppstructurev3",
                    )
                ],
            )
        )
    return page


def parse_paddle_full_raster(
    source: Path,
    project_root: Path,
    page_numbers: list[int] | None = None,
    dpi: int = 180,
) -> CanonicalDocument:
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False")
    _, paddleocr = import_paddle_locally(project_root)
    import fitz

    timings: dict[str, float] = {}
    started = time.perf_counter()
    with ResourceMonitor() as resources:
        init_started = time.perf_counter()
        pipeline = paddleocr.PPStructureV3(
            layout_detection_model_name="PP-DocLayout-M",
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="en_PP-OCRv5_mobile_rec",
            wired_table_structure_recognition_model_name="SLANet",
            wireless_table_structure_recognition_model_name="SLANet_plus",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            use_seal_recognition=False,
            use_formula_recognition=False,
            use_chart_recognition=False,
            use_region_detection=False,
            use_table_recognition=True,
            device="cpu",
            enable_mkldnn=False,
        )
        timings["initialization"] = time.perf_counter() - init_started

        document = fitz.open(source)
        selected = page_numbers or list(range(1, document.page_count + 1))
        pages: list[Page] = []
        render_seconds = 0.0
        inference_seconds = 0.0
        temp_root = project_root / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="paddle-pages-", dir=temp_root) as temp_name:
            temp_dir = Path(temp_name)
            for page_number in selected:
                render_started = time.perf_counter()
                pdf_page = document.load_page(page_number - 1)
                scale = dpi / 72.0
                pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                image_path = temp_dir / f"page-{page_number}.png"
                pixmap.save(image_path)
                render_seconds += time.perf_counter() - render_started

                inference_started = time.perf_counter()
                predictions = list(
                    pipeline.predict(
                        str(image_path),
                        use_e2e_wired_table_rec_model=True,
                        use_table_orientation_classify=False,
                    )
                )
                inference_seconds += time.perf_counter() - inference_started
                pages.append(normalize_paddle_page(predictions[0].json, page_number))
        document.close()
        timings["rendering"] = render_seconds
        timings["inference"] = inference_seconds
    elapsed = time.perf_counter() - started

    return CanonicalDocument(
        document_id=source.stem,
        source_filename=source.name,
        sha256=file_sha256(source),
        parser_run=ParserRun(
            strategy="full_raster",
            parser_versions={
                "paddleocr": importlib.metadata.version("paddleocr"),
                "paddlepaddle": importlib.metadata.version("paddlepaddle"),
                "pymupdf": importlib.metadata.version("pymupdf"),
            },
            rendering_dpi=dpi,
            elapsed_seconds=elapsed,
            timings=timings,
            peak_memory_mb=resources.peak_memory_mb,
            page_routes={page_number: "paddle_ppstructurev3" for page_number in selected},
            warnings=["MKL-DNN disabled for Paddle 3.3.1 compatibility on Windows."],
        ),
        pages=pages,
    )
