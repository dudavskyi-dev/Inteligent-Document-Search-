from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark.models import CanonicalDocument
from benchmark.resources import ResourceMonitor


def _write_json(path: Path, value: Any) -> None:
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


def _configure_environment(project_root: Path) -> None:
    cache = project_root / ".cache"
    os.environ.setdefault("HF_HOME", str(cache / "huggingface"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(cache / "huggingface" / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(cache / "huggingface" / "transformers"))
    os.environ.setdefault("TORCH_HOME", str(cache / "torch"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _validate_real_provenance(
    project_root: Path,
    cases: list[dict[str, Any]],
) -> int:
    corpus_root = project_root / "spike" / "results" / "retrieval" / "corpus"
    documents: dict[str, CanonicalDocument] = {}
    validated = 0
    for case in cases:
        if case["source_kind"] != "real":
            continue
        source = str(case["source"])
        if source not in documents:
            canonical_path = corpus_root / f"{Path(source).stem}.docling.json"
            if not canonical_path.is_file():
                raise FileNotFoundError(
                    f"Canonical retrieval corpus is missing: {canonical_path}"
                )
            documents[source] = CanonicalDocument.model_validate_json(
                canonical_path.read_text(encoding="utf-8")
            )
        document = documents[source]
        page = next(
            (
                item
                for item in document.pages
                if item.page_number == int(case["page_number"])
            ),
            None,
        )
        if page is None:
            raise ValueError(f"Missing source page for extraction case {case['case_id']}.")
        block = next(
            (item for item in page.blocks if item.block_id == case["evidence_id"]),
            None,
        )
        if block is None:
            raise ValueError(f"Missing evidence block for extraction case {case['case_id']}.")
        if case["text"] not in block.text:
            raise ValueError(
                f"Case text is not an exact substring of evidence {case['evidence_id']}."
            )
        validated += 1
    return validated


def main() -> None:
    parser = argparse.ArgumentParser(description="User-run local GLiNER extraction benchmark.")
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    _configure_environment(project_root)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = project_root / "spike" / "results" / "gliner" / "runs" / run_id
    summary_path = run_root / "summary.json"
    predictions_path = run_root / "predictions.json"
    log_path = project_root / "spike" / "logs" / "gliner" / f"{run_id}.log"
    latest_path = project_root / "spike" / "results" / "gliner" / "latest.txt"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(str(summary_path), encoding="utf-8")

    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": "running",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "finished_at_utc": None,
        "model": "gliner-community/gliner_small-v2.5",
        "device": "cpu",
        "dataset": None,
        "runtime": None,
        "metrics": None,
        "quality_gate": None,
        "artifacts": {
            "summary": str(summary_path),
            "predictions": str(predictions_path),
            "log": str(log_path),
            "latest_pointer": str(latest_path),
        },
        "error": None,
    }
    _write_json(summary_path, summary)
    _append_log(log_path, f"GLiNER extraction benchmark {run_id}\n")

    exit_code = 1
    try:
        import gliner
        import torch
        from gliner import GLiNER

        from benchmark.gliner_extraction import (
            MODEL_NAME,
            THRESHOLDS,
            evaluate_predictions,
            predict_cases,
            prepare_cases,
        )

        dataset_path = (
            project_root
            / "spike"
            / "data"
            / "ground_truth"
            / "gliner_extraction_cases.json"
        )
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        cases = prepare_cases(dataset)
        validated_real_cases = _validate_real_provenance(project_root, cases)
        source_counts: dict[str, int] = {}
        for case in cases:
            kind = case["source_kind"]
            source_counts[kind] = source_counts.get(kind, 0) + 1
        summary["dataset"] = {
            "path": str(dataset_path),
            "case_count": len(cases),
            "source_counts": source_counts,
            "expected_entity_count": sum(len(case["expected"]) for case in cases),
            "real_provenance_cases_validated": validated_real_cases,
            "labels": dataset["labels"],
            "thresholds": list(THRESHOLDS),
        }
        _write_json(summary_path, summary)

        with ResourceMonitor() as resources:
            load_started = datetime.now(UTC)
            model = GLiNER.from_pretrained(
                MODEL_NAME,
                load_tokenizer=True,
                map_location="cpu",
            )
            model.eval()
            load_seconds = (datetime.now(UTC) - load_started).total_seconds()
            predictions = predict_cases(
                model,
                dataset,
                cases,
                minimum_threshold=min(THRESHOLDS),
            )
            metrics = evaluate_predictions(predictions, THRESHOLDS)

        summary["runtime"] = {
            "model_loading_seconds": round(load_seconds, 6),
            "peak_memory_mb": round(resources.peak_memory_mb, 3),
            "package_versions": {
                "gliner": importlib.metadata.version("gliner"),
                "torch": importlib.metadata.version("torch"),
            },
            "inference": metrics["latency"],
        }
        summary["metrics"] = metrics
        summary["quality_gate"] = metrics["quality_gate"]
        _write_json(predictions_path, predictions)
        summary["status"] = "success"
        exit_code = 0
    except KeyboardInterrupt:
        summary["status"] = "interrupted"
        summary["error"] = "Interrupted by user."
        _append_log(log_path, traceback.format_exc())
    except Exception as error:
        summary["status"] = "failed"
        summary["error"] = f"{type(error).__name__}: {error}"
        _append_log(log_path, traceback.format_exc())
    finally:
        summary["finished_at_utc"] = datetime.now(UTC).isoformat()
        _write_json(summary_path, summary)
        _append_log(log_path, f"status={summary['status']}\nsummary={summary_path}\n")

    print(f"status={summary['status']}")
    print(f"saved_report={summary_path}")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
