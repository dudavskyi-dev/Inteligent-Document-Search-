from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from benchmark.models import CanonicalDocument, Page, ParserRun
from benchmark.parsers.docling_adapter import file_sha256
from benchmark.parsers.router import assess_text_layer
from benchmark.resources import ResourceMonitor


def _write_subset_pdf(source: Path, page_numbers: list[int], output: Path) -> None:
    reader = PdfReader(source)
    writer = PdfWriter()
    for page_number in page_numbers:
        writer.add_page(reader.pages[page_number - 1])
    with output.open("wb") as stream:
        writer.write(stream)


def _remap_page(page: Page, source_page: int) -> None:
    local_page = page.page_number
    old_prefix = f"p{local_page}-"
    new_prefix = f"p{source_page}-"
    page.page_number = source_page
    for block in page.blocks:
        block.block_id = block.block_id.replace(old_prefix, new_prefix, 1)
        for provenance in block.provenance:
            provenance.page_number = source_page
    for table in page.tables:
        table.table_id = table.table_id.replace(old_prefix, new_prefix, 1)
        for provenance in table.provenance:
            provenance.page_number = source_page
        for cell in table.cells:
            cell.cell_id = cell.cell_id.replace(old_prefix, new_prefix, 1)
            for provenance in cell.provenance:
                provenance.page_number = source_page


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def parse_hybrid(source: Path, project_root: Path, dpi: int = 180) -> CanonicalDocument:
    started = time.perf_counter()
    route_started = time.perf_counter()
    assessments = assess_text_layer(source)
    routing_seconds = time.perf_counter() - route_started
    native_pages = [a.page_number for a in assessments if a.route == "docling_native"]
    raster_pages = [a.page_number for a in assessments if a.route == "paddle_ppstructurev3"]

    temp_root = project_root / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    documents: list[CanonicalDocument] = []
    child_timings: dict[str, float] = {}
    with ResourceMonitor() as resources:  # noqa: SIM117 - scopes peak child RSS.
        with tempfile.TemporaryDirectory(prefix="hybrid-", dir=temp_root) as temp_name:
            temp_dir = Path(temp_name)
            if native_pages:
                subset = temp_dir / "native-pages.pdf"
                native_output = temp_dir / "native.json"
                _write_subset_pdf(source, native_pages, subset)
                child_started = time.perf_counter()
                _run(
                    [
                        sys.executable,
                        "-m",
                        "benchmark.run_docling",
                        str(subset),
                        "--output",
                        str(native_output),
                        "--project-root",
                        str(project_root),
                    ]
                )
                child_timings["docling_process"] = time.perf_counter() - child_started
                native_document = CanonicalDocument.model_validate_json(
                    native_output.read_text(encoding="utf-8")
                )
                local_pages = sorted(native_document.pages, key=lambda page: page.page_number)
                if len(local_pages) != len(native_pages):
                    raise ValueError(
                        "Docling subset page count does not match the native-page routing plan: "
                        f"{len(local_pages)} != {len(native_pages)}"
                    )
                # Iterate over stable Page objects. Looking pages up again after mutating
                # page_number can select an already-remapped object when numbers collide.
                for page, source_page in zip(local_pages, native_pages, strict=True):
                    _remap_page(page, source_page)
                documents.append(native_document)

            if raster_pages:
                raster_output = temp_dir / "raster.json"
                child_started = time.perf_counter()
                _run(
                    [
                        sys.executable,
                        "-m",
                        "benchmark.run_paddle",
                        str(source),
                        "--output",
                        str(raster_output),
                        "--project-root",
                        str(project_root),
                        "--pages",
                        ",".join(str(page) for page in raster_pages),
                        "--dpi",
                        str(dpi),
                    ]
                )
                child_timings["paddle_process"] = time.perf_counter() - child_started
                documents.append(
                    CanonicalDocument.model_validate_json(raster_output.read_text(encoding="utf-8"))
                )

    all_pages = sorted(
        [page for document in documents for page in document.pages], key=lambda page: page.page_number
    )
    versions = {
        key: value
        for document in documents
        for key, value in document.parser_run.parser_versions.items()
    }
    elapsed = time.perf_counter() - started
    child_timings["routing"] = routing_seconds
    return CanonicalDocument(
        document_id=source.stem,
        source_filename=source.name,
        sha256=file_sha256(source),
        parser_run=ParserRun(
            strategy="hybrid",
            parser_versions=versions,
            rendering_dpi=dpi,
            elapsed_seconds=elapsed,
            timings=child_timings,
            peak_memory_mb=resources.peak_memory_mb,
            page_routes={assessment.page_number: assessment.route for assessment in assessments},
            warnings=[warning for document in documents for warning in document.parser_run.warnings],
            diagnostics={
                "page_assessments": [
                    json.loads(assessment.model_dump_json()) for assessment in assessments
                ]
            },
        ),
        pages=all_pages,
    )
