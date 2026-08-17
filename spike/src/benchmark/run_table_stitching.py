from __future__ import annotations

import argparse
import json
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark.models import CanonicalDocument
from benchmark.table_stitching import StitchResult, stitch_document


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _metric(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _evaluate(result: StitchResult, ground_truth: dict[str, Any]) -> dict[str, Any]:
    predicted = {
        (decision.left_page, decision.right_page): decision
        for decision in result.decisions
    }
    rows = []
    true_positive = false_positive = false_negative = true_negative = 0
    for expected in ground_truth["pairs"]:
        key = (expected["left_page"], expected["right_page"])
        decision = predicted.get(key)
        actual = decision.predicted_merge if decision else False
        wanted = bool(expected["should_merge"])
        if wanted and actual:
            true_positive += 1
            outcome = "TP"
        elif not wanted and actual:
            false_positive += 1
            outcome = "FP"
        elif wanted and not actual:
            false_negative += 1
            outcome = "FN"
        else:
            true_negative += 1
            outcome = "TN"
        rows.append(
            {
                "left_page": key[0],
                "right_page": key[1],
                "expected_merge": wanted,
                "predicted_merge": actual,
                "outcome": outcome,
                "score": decision.score if decision else None,
                "left_table_id": decision.left_table_id if decision else None,
                "right_table_id": decision.right_table_id if decision else None,
                "ground_truth_reason": expected["reason"],
            }
        )

    precision = _metric(true_positive, true_positive + false_positive)
    recall = _metric(true_positive, true_positive + false_negative)
    f1 = _metric(2 * precision * recall, precision + recall)
    accuracy = _metric(
        true_positive + true_negative,
        true_positive + false_positive + false_negative + true_negative,
    )
    labelled_keys = {
        (pair["left_page"], pair["right_page"])
        for pair in ground_truth["pairs"]
    }
    extra_candidates = [
        {"left_page": key[0], "right_page": key[1]}
        for key in sorted(predicted.keys() - labelled_keys)
    ]
    return {
        "confusion_matrix": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "true_negative": true_negative,
        },
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "accuracy": round(accuracy, 6),
        "pairs": rows,
        "extra_unlabelled_candidates": extra_candidates,
    }


def _invariants(document: CanonicalDocument, result: StitchResult) -> dict[str, Any]:
    input_table_ids = [table.table_id for page in document.pages for table in page.tables]
    output_table_ids = [
        table_id for logical_table in result.logical_tables for table_id in logical_table.fragment_ids
    ]
    input_cell_ids = [
        cell.cell_id
        for page in document.pages
        for table in page.tables
        for cell in table.cells
    ]
    output_cell_ids = [
        cell_id for logical_table in result.logical_tables for cell_id in logical_table.source_cell_ids
    ]
    checks = {
        "all_fragments_preserved_once": (
            sorted(input_table_ids) == sorted(output_table_ids)
            and len(output_table_ids) == len(set(output_table_ids))
        ),
        "all_source_cells_preserved_once": (
            sorted(input_cell_ids) == sorted(output_cell_ids)
            and len(output_cell_ids) == len(set(output_cell_ids))
        ),
        "no_synthetic_fragment_ids": set(output_table_ids) <= set(input_table_ids),
        "no_synthetic_cell_ids": set(output_cell_ids) <= set(input_cell_ids),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "input_fragments": len(input_table_ids),
        "output_fragments": len(output_table_ids),
        "input_cells": len(input_cell_ids),
        "output_cells": len(output_cell_ids),
    }


def _load_latest_hybrid(project_root: Path) -> tuple[Path, CanonicalDocument]:
    pointer = project_root / "spike" / "results" / "parsing" / "latest.txt"
    parsing_summary_path = Path(pointer.read_text(encoding="utf-8").strip())
    parsing_summary = json.loads(parsing_summary_path.read_text(encoding="utf-8"))
    if parsing_summary.get("status") != "success":
        raise ValueError(f"Latest parsing report is not successful: {parsing_summary_path}")
    hybrid_runs = [run for run in parsing_summary["runs"] if run["name"] == "hybrid"]
    if len(hybrid_runs) != 1 or hybrid_runs[0]["status"] != "success":
        raise ValueError("Latest parsing report does not contain one successful Hybrid run.")
    failed_validations = [
        validation["name"]
        for validation in hybrid_runs[0].get("validations", [])
        if not validation.get("passed")
    ]
    if failed_validations:
        raise ValueError("Hybrid canonical validations failed: " + ", ".join(failed_validations))
    canonical_path = Path(hybrid_runs[0]["canonical_output"])
    document = CanonicalDocument.model_validate_json(canonical_path.read_text(encoding="utf-8"))
    return parsing_summary_path, document


def main() -> None:
    parser = argparse.ArgumentParser(description="User-run deterministic table-stitching spike.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.72)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    result_root = project_root / "spike" / "results" / "stitching" / run_id
    summary_path = result_root / "summary.json"
    decisions_path = result_root / "decisions.json"
    logical_tables_path = result_root / "logical_tables.json"
    log_path = project_root / "spike" / "logs" / "stitching" / f"{run_id}.log"
    latest_path = project_root / "spike" / "results" / "stitching" / "latest.txt"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(str(summary_path), encoding="utf-8")

    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": "running",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "finished_at_utc": None,
        "threshold": args.threshold,
        "input_parsing_summary": None,
        "runtime_seconds": None,
        "metrics": None,
        "invariants": None,
        "quality_gate": {
            "required_precision": 1.0,
            "required_recall": 1.0,
            "required_f1": 1.0,
            "require_no_unlabelled_candidates": True,
            "require_all_invariants": True,
        },
        "artifacts": {
            "summary": str(summary_path),
            "decisions": str(decisions_path),
            "logical_tables": str(logical_tables_path),
            "log": str(log_path),
        },
        "error": None,
    }
    _write_json(summary_path, summary)

    exit_code = 1
    try:
        parsing_summary_path, document = _load_latest_hybrid(project_root)
        summary["input_parsing_summary"] = str(parsing_summary_path)
        ground_truth_path = (
            project_root / "spike" / "data" / "ground_truth" / "table_stitching_gsa.json"
        )
        ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
        if document.source_filename != ground_truth["fixture"]:
            raise ValueError(
                f"Unexpected fixture: {document.source_filename}; expected {ground_truth['fixture']}"
            )
        if document.sha256 != ground_truth["fixture_sha256"]:
            raise ValueError("Canonical document SHA-256 does not match stitching ground truth.")

        started = time.perf_counter()
        result = stitch_document(document, threshold=args.threshold)
        summary["runtime_seconds"] = round(time.perf_counter() - started, 6)
        summary["metrics"] = _evaluate(result, ground_truth)
        summary["invariants"] = _invariants(document, result)
        _write_json(
            decisions_path,
            [decision.model_dump(mode="json") for decision in result.decisions],
        )
        _write_json(
            logical_tables_path,
            [logical_table.model_dump(mode="json") for logical_table in result.logical_tables],
        )

        metrics = summary["metrics"]
        gate_passed = (
            metrics["precision"] == 1.0
            and metrics["recall"] == 1.0
            and metrics["f1"] == 1.0
            and not metrics["extra_unlabelled_candidates"]
            and summary["invariants"]["passed"]
        )
        summary["status"] = "success" if gate_passed else "quality_gate_failed"
        exit_code = 0 if gate_passed else 1
    except Exception as error:
        summary["status"] = "failed"
        summary["error"] = f"{type(error).__name__}: {error}"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        summary["finished_at_utc"] = datetime.now(UTC).isoformat()
        _write_json(summary_path, summary)
        if not log_path.exists():
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "status": summary["status"],
                        "runtime_seconds": summary["runtime_seconds"],
                        "metrics": summary["metrics"],
                        "invariants": summary["invariants"],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    print(f"status={summary['status']}")
    print(f"saved_report={summary_path}")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
