from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
import traceback
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import psutil

from benchmark.models import CanonicalDocument


@dataclass(frozen=True)
class RunSpec:
    name: str
    module: str
    input_path: Path
    pages: str | None = None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _append_log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(text)
        if text and not text.endswith("\n"):
            stream.write("\n")


def _system_information() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    information: dict[str, Any] = {
        "platform": platform.platform(),
        "python": sys.version,
        "python_executable": str(Path(sys.executable).resolve()),
        "cpu": platform.processor() or None,
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "physical_cpu_count": psutil.cpu_count(logical=False),
        "total_memory_mb": round(memory.total / (1024 * 1024), 1),
    }
    try:
        gpu = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if gpu.returncode == 0 and gpu.stdout.strip():
            information["nvidia_gpu"] = gpu.stdout.strip().splitlines()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        information["nvidia_gpu"] = None
    return information


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE)


def _token_f1(left: str, right: str) -> float | None:
    left_tokens = Counter(_tokens(left))
    right_tokens = Counter(_tokens(right))
    if not left_tokens and not right_tokens:
        return None
    overlap = sum((left_tokens & right_tokens).values())
    precision = overlap / sum(left_tokens.values()) if left_tokens else 0.0
    recall = overlap / sum(right_tokens.values()) if right_tokens else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _page_text(page: Any) -> str:
    return "\n".join(block.text for block in page.blocks if block.text.strip())


def _page_cell_text(page: Any) -> str:
    ordered_cells = sorted(
        (cell for table in page.tables for cell in table.cells),
        key=lambda cell: (cell.row, cell.column, cell.cell_id),
    )
    return "\n".join(cell.text for cell in ordered_cells if cell.text.strip())


def _has_usable_provenance(item: Any) -> bool:
    return bool(item.provenance) and all(
        provenance.page_number >= 1
        and provenance.bbox.x1 <= provenance.bbox.x2
        and provenance.bbox.y1 <= provenance.bbox.y2
        for provenance in item.provenance
    )


def _document_metrics(document: CanonicalDocument) -> dict[str, Any]:
    blocks = [block for page in document.pages for block in page.blocks]
    tables = [table for page in document.pages for table in page.tables]
    cells = [cell for table in tables for cell in table.cells]
    evidence_items = [*blocks, *tables, *cells]
    text_characters = sum(len(block.text.strip()) for block in blocks)
    cell_characters = sum(len(cell.text.strip()) for cell in cells)
    pages_count = len(document.pages)
    elapsed = document.parser_run.elapsed_seconds

    page_metrics = []
    for page in document.pages:
        page_cells = [cell for table in page.tables for cell in table.cells]
        page_metrics.append(
            {
                "page_number": page.page_number,
                "blocks": len(page.blocks),
                "nonempty_blocks": sum(bool(block.text.strip()) for block in page.blocks),
                "tables": len(page.tables),
                "cells": len(page_cells),
                "text_characters": sum(len(block.text.strip()) for block in page.blocks),
                "cell_characters": sum(len(cell.text.strip()) for cell in page_cells),
            }
        )

    return {
        "strategy": document.parser_run.strategy,
        "schema_version": document.schema_version,
        "source_filename": document.source_filename,
        "sha256": document.sha256,
        "parser_versions": document.parser_run.parser_versions,
        "rendering_dpi": document.parser_run.rendering_dpi,
        "pages": pages_count,
        "elapsed_seconds": round(elapsed, 4),
        "seconds_per_page": round(elapsed / pages_count, 4) if pages_count else None,
        "peak_memory_mb": document.parser_run.peak_memory_mb,
        "internal_timings": document.parser_run.timings,
        "route_counts": dict(Counter(document.parser_run.page_routes.values())),
        "blocks": len(blocks),
        "nonempty_blocks": sum(bool(block.text.strip()) for block in blocks),
        "tables": len(tables),
        "cells": len(cells),
        "text_characters": text_characters,
        "cell_characters": cell_characters,
        "evidence_bbox_coverage": (
            round(sum(_has_usable_provenance(item) for item in evidence_items) / len(evidence_items), 4)
            if evidence_items
            else None
        ),
        "warnings": document.parser_run.warnings,
        "pages_detail": page_metrics,
    }


def _document_validations(document: CanonicalDocument) -> list[dict[str, Any]]:
    page_numbers = [page.page_number for page in document.pages]
    expected_sequence = list(range(1, len(document.pages) + 1))
    sequence_ok = page_numbers == expected_sequence

    provenance_mismatches: list[dict[str, Any]] = []
    for page in document.pages:
        items = [*page.blocks, *page.tables]
        items.extend(cell for table in page.tables for cell in table.cells)
        for item in items:
            wrong_pages = sorted(
                {
                    provenance.page_number
                    for provenance in item.provenance
                    if provenance.page_number != page.page_number
                }
            )
            if wrong_pages:
                provenance_mismatches.append(
                    {
                        "canonical_page": page.page_number,
                        "item_id": getattr(
                            item,
                            "block_id",
                            getattr(item, "table_id", getattr(item, "cell_id", "unknown")),
                        ),
                        "provenance_pages": wrong_pages,
                    }
                )

    validations: list[dict[str, Any]] = [
        {
            "name": "canonical_page_sequence",
            "passed": sequence_ok,
            "expected": expected_sequence,
            "observed": page_numbers,
        },
        {
            "name": "provenance_page_consistency",
            "passed": not provenance_mismatches,
            "mismatches": provenance_mismatches,
        },
    ]

    if document.source_filename == "05_GSA_Mixed_Table_Fixture.pdf":
        expected_source_pages = {1: 13, 3: 15, 4: 24, 6: 26}
        observed: dict[int, list[int]] = {}
        for page in document.pages:
            markers: set[int] = set()
            for block in page.blocks:
                for match in re.finditer(r"\bPage\s+(\d+)\s+of\s+\d+\b", block.text, re.I):
                    markers.add(int(match.group(1)))
            observed[page.page_number] = sorted(markers)
        marker_mismatches = {
            canonical_page: {
                "expected_source_page": source_page,
                "observed_source_pages": observed.get(canonical_page, []),
            }
            for canonical_page, source_page in expected_source_pages.items()
            if source_page not in observed.get(canonical_page, [])
        }
        validations.append(
            {
                "name": "fixture_source_page_markers",
                "passed": not marker_mismatches,
                "expected": expected_source_pages,
                "observed": observed,
                "mismatches": marker_mismatches,
            }
        )
    return validations


def _compare_documents(
    left_name: str,
    left: CanonicalDocument,
    right_name: str,
    right: CanonicalDocument,
) -> dict[str, Any]:
    left_pages = {page.page_number: page for page in left.pages}
    right_pages = {page.page_number: page for page in right.pages}
    shared_pages = sorted(left_pages.keys() & right_pages.keys())
    rows: list[dict[str, Any]] = []
    for page_number in shared_pages:
        left_page = left_pages[page_number]
        right_page = right_pages[page_number]
        rows.append(
            {
                "page_number": page_number,
                "block_text_token_f1": _token_f1(
                    _page_text(left_page), _page_text(right_page)
                ),
                "table_cell_text_token_f1": _token_f1(
                    _page_cell_text(left_page), _page_cell_text(right_page)
                ),
                "left_table_count": len(left_page.tables),
                "right_table_count": len(right_page.tables),
                "left_cell_count": sum(len(table.cells) for table in left_page.tables),
                "right_cell_count": sum(len(table.cells) for table in right_page.tables),
            }
        )

    block_scores = [row["block_text_token_f1"] for row in rows if row["block_text_token_f1"] is not None]
    cell_scores = [
        row["table_cell_text_token_f1"]
        for row in rows
        if row["table_cell_text_token_f1"] is not None
    ]
    return {
        "left": left_name,
        "right": right_name,
        "warning": (
            "These are automated agreement diagnostics, not accuracy against manually "
            "verified ground truth."
        ),
        "shared_pages": shared_pages,
        "mean_block_text_token_f1": round(mean(block_scores), 4) if block_scores else None,
        "mean_table_cell_text_token_f1": round(mean(cell_scores), 4) if cell_scores else None,
        "pages": rows,
    }


def _command_for(
    spec: RunSpec,
    project_root: Path,
    output_path: Path,
    dpi: int,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        spec.module,
        str(spec.input_path),
        "--output",
        str(output_path),
        "--project-root",
        str(project_root),
    ]
    if spec.pages:
        command.extend(["--pages", spec.pages])
    if spec.name in {"full_raster", "hybrid"}:
        command.extend(["--dpi", str(dpi)])
    return command


def _stream_command(command: list[str], project_root: Path, log_path: Path) -> int:
    display = subprocess.list2cmdline(command)
    heading = f"\n$ {display}\n"
    print(heading, end="", flush=True)
    _append_log(log_path, heading)
    process = subprocess.Popen(
        command,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=os.environ.copy(),
    )
    assert process.stdout is not None
    try:
        for line in process.stdout:
            print(line, end="", flush=True)
            _append_log(log_path, line)
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=30)
        raise


def _build_specs(project_root: Path, only: str) -> list[RunSpec]:
    inputs = project_root / "spike" / "data" / "inputs"
    specs = [
        RunSpec(
            name="docling_native",
            module="benchmark.run_docling",
            input_path=inputs / "05_GSA_Mixed_Table_Fixture.pdf",
            pages="1-7",
        ),
        RunSpec(
            name="full_raster",
            module="benchmark.run_paddle",
            input_path=inputs / "04_GSA_Table_Scan_Fixture.pdf",
            pages="1-7",
        ),
        RunSpec(
            name="hybrid",
            module="benchmark.run_hybrid",
            input_path=inputs / "05_GSA_Mixed_Table_Fixture.pdf",
            pages=None,
        ),
    ]
    if only == "hybrid":
        return [spec for spec in specs if spec.name == "hybrid"]
    return specs


def _validate_inputs(specs: list[RunSpec]) -> None:
    missing = sorted({str(spec.input_path) for spec in specs if not spec.input_path.is_file()})
    if missing:
        raise FileNotFoundError("Missing benchmark input(s): " + ", ".join(missing))


def run_benchmark(project_root: Path, dpi: int, only: str) -> tuple[Path, bool]:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results_root = project_root / "spike" / "results" / "parsing" / run_id
    outputs_root = results_root / "outputs"
    log_path = project_root / "spike" / "logs" / "parsing" / f"{run_id}.log"
    summary_path = results_root / "summary.json"
    latest_path = project_root / "spike" / "results" / "parsing" / "latest.txt"
    specs = _build_specs(project_root, only)
    _validate_inputs(specs)

    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": "running",
        "profile": "hybrid_only_7_pages" if only == "hybrid" else "full_7_pages",
        "dpi": dpi,
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "system": _system_information(),
        "evaluation_note": (
            "Runtime/resource values are measured. Content F1 is an automated cross-parser "
            "agreement proxy and is not human-verified parsing accuracy."
        ),
        "runs": [],
        "comparisons": [],
        "artifacts": {
            "summary": str(summary_path),
            "log": str(log_path),
            "latest_pointer": str(latest_path),
        },
    }
    _write_json(summary_path, summary)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(str(summary_path), encoding="utf-8")
    _append_log(log_path, f"Parsing benchmark {run_id}\nStarted: {summary['started_at_utc']}\n")

    documents: dict[str, CanonicalDocument] = {}
    interrupted = False
    for spec in specs:
        output_path = outputs_root / f"{spec.name}.json"
        command = _command_for(spec, project_root, output_path, dpi)
        record: dict[str, Any] = {
            "name": spec.name,
            "status": "running",
            "input": str(spec.input_path),
            "requested_pages": spec.pages or "all",
            "canonical_output": str(output_path),
            "command": subprocess.list2cmdline(command),
            "wall_seconds": None,
            "return_code": None,
            "metrics": None,
            "validations": [],
            "error": None,
        }
        summary["runs"].append(record)
        _write_json(summary_path, summary)
        started = time.perf_counter()
        try:
            return_code = _stream_command(command, project_root, log_path)
            record["wall_seconds"] = round(time.perf_counter() - started, 4)
            record["return_code"] = return_code
            if return_code != 0:
                record["status"] = "failed"
                record["error"] = f"Child process returned exit code {return_code}."
            elif not output_path.is_file():
                record["status"] = "failed"
                record["error"] = "Child process succeeded but canonical output is missing."
            else:
                document = CanonicalDocument.model_validate_json(
                    output_path.read_text(encoding="utf-8")
                )
                record["metrics"] = _document_metrics(document)
                record["validations"] = _document_validations(document)
                failed_validations = [
                    validation["name"]
                    for validation in record["validations"]
                    if not validation["passed"]
                ]
                if failed_validations:
                    record["status"] = "failed"
                    record["error"] = (
                        "Canonical validation failed: " + ", ".join(failed_validations)
                    )
                else:
                    documents[spec.name] = document
                    record["status"] = "success"
        except KeyboardInterrupt:
            record["wall_seconds"] = round(time.perf_counter() - started, 4)
            record["status"] = "interrupted"
            record["error"] = "Interrupted by user."
            interrupted = True
        except Exception as error:  # Keep evidence for the next debugging iteration.
            record["wall_seconds"] = round(time.perf_counter() - started, 4)
            record["status"] = "failed"
            record["error"] = f"{type(error).__name__}: {error}"
            _append_log(log_path, traceback.format_exc())
        finally:
            _write_json(summary_path, summary)
        if interrupted:
            break

    comparison_pairs = [
        ("full_raster", "hybrid"),
        ("docling_native", "hybrid"),
    ]
    for left_name, right_name in comparison_pairs:
        if left_name in documents and right_name in documents:
            summary["comparisons"].append(
                _compare_documents(
                    left_name,
                    documents[left_name],
                    right_name,
                    documents[right_name],
                )
            )

    statuses = [record["status"] for record in summary["runs"]]
    success = len(statuses) == len(specs) and all(status == "success" for status in statuses)
    if interrupted:
        summary["status"] = "interrupted"
    elif success:
        summary["status"] = "success"
    elif any(status == "success" for status in statuses):
        summary["status"] = "partial"
    else:
        summary["status"] = "failed"
    summary["finished_at_utc"] = _utc_now()
    _write_json(summary_path, summary)
    _append_log(log_path, f"Finished: {summary['finished_at_utc']}\nStatus: {summary['status']}\n")
    return summary_path, success


def main() -> None:
    parser = argparse.ArgumentParser(
        description="User-run parsing benchmark with persistent JSON and log artifacts."
    )
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--only", choices=("all", "hybrid"), default="all")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    try:
        summary_path, success = run_benchmark(project_root, args.dpi, args.only)
    except Exception as error:
        print(f"Benchmark could not start: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    print(f"\nSaved report: {summary_path}")
    print("Send that summary.json to the assistant after the run.")
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
