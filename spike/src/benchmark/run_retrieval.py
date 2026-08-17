from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark.models import CanonicalDocument
from benchmark.parsers.docling_adapter import file_sha256
from benchmark.resources import ResourceMonitor


SOURCE_FILES = (
    "01_GSA_VA_Chiller_Maintenance_Solicitation.pdf",
    "02_DOE_NNSA_RFP_Section_L.pdf",
    "03_NASA_Fastener_Procurement_Standard.pdf",
)


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
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(cache / "sentence-transformers"))
    os.environ.setdefault("TORCH_HOME", str(cache / "torch"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


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


def _load_or_parse_document(
    source: Path,
    canonical_path: Path,
    project_root: Path,
    log_path: Path,
    rebuild: bool,
) -> tuple[CanonicalDocument, dict[str, Any]]:
    expected_sha = file_sha256(source)
    if canonical_path.is_file() and not rebuild:
        try:
            cached = CanonicalDocument.model_validate_json(
                canonical_path.read_text(encoding="utf-8")
            )
            if cached.sha256 == expected_sha and cached.parser_run.strategy == "docling_native":
                return cached, {
                    "source": str(source),
                    "sha256": expected_sha,
                    "canonical_output": str(canonical_path),
                    "cache_status": "reused",
                    "wall_seconds": 0.0,
                    "parser_elapsed_seconds": cached.parser_run.elapsed_seconds,
                    "pages": len(cached.pages),
                }
        except Exception as error:
            _append_log(log_path, f"Ignoring invalid cached canonical JSON: {error}")

    command = [
        sys.executable,
        "-m",
        "benchmark.run_docling",
        str(source),
        "--output",
        str(canonical_path),
        "--project-root",
        str(project_root),
    ]
    started = time.perf_counter()
    return_code = _stream_command(command, project_root, log_path)
    wall_seconds = time.perf_counter() - started
    if return_code != 0:
        raise RuntimeError(f"Docling failed for {source.name} with exit code {return_code}.")
    document = CanonicalDocument.model_validate_json(canonical_path.read_text(encoding="utf-8"))
    if document.sha256 != expected_sha:
        raise ValueError(f"SHA-256 mismatch after parsing {source.name}.")
    if [page.page_number for page in document.pages] != list(range(1, len(document.pages) + 1)):
        raise ValueError(f"Non-contiguous canonical page sequence for {source.name}.")
    return document, {
        "source": str(source),
        "sha256": expected_sha,
        "canonical_output": str(canonical_path),
        "cache_status": "created",
        "wall_seconds": round(wall_seconds, 6),
        "parser_elapsed_seconds": document.parser_run.elapsed_seconds,
        "pages": len(document.pages),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="User-run local retrieval benchmark.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--rebuild-corpus", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    _configure_environment(project_root)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = project_root / "spike" / "results" / "retrieval" / "runs" / run_id
    corpus_root = project_root / "spike" / "results" / "retrieval" / "corpus"
    summary_path = run_root / "summary.json"
    rankings_path = run_root / "rankings.json"
    corpus_manifest_path = run_root / "corpus_manifest.json"
    log_path = project_root / "spike" / "logs" / "retrieval" / f"{run_id}.log"
    latest_path = project_root / "spike" / "results" / "retrieval" / "latest.txt"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(str(summary_path), encoding="utf-8")

    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": "running",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "finished_at_utc": None,
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "corpus": [],
        "index": None,
        "metrics": None,
        "quality_gate": {
            "best_method_mean_recall@3_required": 0.8,
            "best_method_mean_mrr@5_required": 0.85,
            "passed": None,
        },
        "artifacts": {
            "summary": str(summary_path),
            "rankings": str(rankings_path),
            "corpus_manifest": str(corpus_manifest_path),
            "log": str(log_path),
            "latest_pointer": str(latest_path),
        },
        "error": None,
    }
    _write_json(summary_path, summary)
    _append_log(log_path, f"Retrieval benchmark {run_id}\n")

    exit_code = 1
    try:
        # Fail early with a persisted report before spending time parsing the corpus.
        import numpy  # noqa: F401
        import rank_bm25  # noqa: F401
        import sentence_transformers  # noqa: F401

        from benchmark.retrieval import MODEL_NAME, RetrievalBenchmark, evaluate_queries

        inputs = project_root / "spike" / "data" / "inputs"
        documents: list[CanonicalDocument] = []
        for filename in SOURCE_FILES:
            source = inputs / filename
            if not source.is_file():
                raise FileNotFoundError(f"Retrieval source PDF is missing: {source}")
            canonical_path = corpus_root / f"{source.stem}.docling.json"
            document, record = _load_or_parse_document(
                source,
                canonical_path,
                project_root,
                log_path,
                rebuild=args.rebuild_corpus,
            )
            documents.append(document)
            summary["corpus"].append(record)
            _write_json(summary_path, summary)

        _write_json(
            corpus_manifest_path,
            {
                "schema_version": "1.0",
                "created_at_utc": datetime.now(UTC).isoformat(),
                "documents": summary["corpus"],
            },
        )
        qrels_path = (
            project_root / "spike" / "data" / "ground_truth" / "retrieval_qrels.json"
        )
        qrels = json.loads(qrels_path.read_text(encoding="utf-8"))

        with ResourceMonitor() as resources:
            index = RetrievalBenchmark(
                documents,
                cache_folder=str(project_root / ".cache" / "sentence-transformers"),
                model_name=MODEL_NAME,
            )
            aggregate_metrics, rankings = evaluate_queries(index, qrels["queries"])

        summary["index"] = {
            "documents": len(documents),
            "pages": len(index.pages),
            "structural_units": len(index.units),
            "model": MODEL_NAME,
            "model_max_sequence_length": index.model.max_seq_length,
            "timings_seconds": {
                name: round(value, 6) for name, value in index.timings.items()
            },
            "peak_memory_mb": round(resources.peak_memory_mb, 3),
            "package_versions": {
                "rank-bm25": importlib.metadata.version("rank-bm25"),
                "sentence-transformers": importlib.metadata.version("sentence-transformers"),
                "numpy": importlib.metadata.version("numpy"),
            },
        }
        summary["metrics"] = aggregate_metrics
        best_method = aggregate_metrics["best_method_by_recall3_then_mrr"]
        best_metrics = aggregate_metrics["methods"][best_method]
        summary["quality_gate"]["passed"] = (
            best_metrics["recall@3"] >= 0.8 and best_metrics["mrr@5"] >= 0.85
        )
        _write_json(rankings_path, rankings)
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
