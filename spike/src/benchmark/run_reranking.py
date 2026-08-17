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
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(cache / "sentence-transformers"))
    os.environ.setdefault("TORCH_HOME", str(cache / "torch"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"Required artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_successful_retrieval(project_root: Path) -> tuple[Path, dict[str, Any]]:
    pointer = project_root / "spike" / "results" / "retrieval" / "latest.txt"
    if not pointer.is_file():
        raise FileNotFoundError("Run the retrieval spike first; latest.txt is missing.")
    summary_path = Path(pointer.read_text(encoding="utf-8").strip()).resolve()
    summary = _load_json(summary_path)
    if summary.get("status") != "success":
        raise ValueError(
            f"Latest retrieval run is not successful: {summary.get('status')!r}."
        )
    return summary_path, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="User-run local reranking benchmark.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--candidate-k", type=int, default=10)
    parser.add_argument("--units-per-page", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    if args.candidate_k < 5:
        parser.error("--candidate-k must be at least 5.")
    if args.candidate_k > 10:
        parser.error("--candidate-k cannot exceed the ten pages saved by retrieval.")
    if args.units_per_page < 1:
        parser.error("--units-per-page must be at least 1.")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1.")

    project_root = args.project_root.resolve()
    _configure_environment(project_root)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = project_root / "spike" / "results" / "reranking" / "runs" / run_id
    summary_path = run_root / "summary.json"
    rankings_path = run_root / "rankings.json"
    log_path = project_root / "spike" / "logs" / "reranking" / f"{run_id}.log"
    latest_path = project_root / "spike" / "results" / "reranking" / "latest.txt"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(str(summary_path), encoding="utf-8")

    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": "running",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "finished_at_utc": None,
        "model": "cross-encoder/ms-marco-MiniLM-L6-v2",
        "configuration": {
            "candidate_source": "hybrid_rrf",
            "candidate_k": args.candidate_k,
            "units_per_page": args.units_per_page,
            "batch_size": args.batch_size,
            "device": "cpu",
        },
        "retrieval_input": None,
        "corpus": None,
        "runtime": None,
        "metrics": None,
        "quality_gate": None,
        "artifacts": {
            "summary": str(summary_path),
            "rankings": str(rankings_path),
            "log": str(log_path),
            "latest_pointer": str(latest_path),
        },
        "error": None,
    }
    _write_json(summary_path, summary)
    _append_log(log_path, f"Reranking benchmark {run_id}\n")

    exit_code = 1
    try:
        import numpy  # noqa: F401
        import rank_bm25  # noqa: F401
        import sentence_transformers  # noqa: F401

        from benchmark.reranking import (
            RERANKER_MODEL,
            RerankingBenchmark,
            evaluate_reranking,
        )

        retrieval_summary_path, retrieval_summary = _latest_successful_retrieval(
            project_root
        )
        retrieval_rankings_path = Path(
            retrieval_summary["artifacts"]["rankings"]
        ).resolve()
        retrieval_rows = _load_json(retrieval_rankings_path)
        summary["retrieval_input"] = {
            "run_id": retrieval_summary["run_id"],
            "summary": str(retrieval_summary_path),
            "rankings": str(retrieval_rankings_path),
        }

        documents: list[CanonicalDocument] = []
        corpus_records: list[dict[str, Any]] = []
        for item in retrieval_summary["corpus"]:
            canonical_path = Path(item["canonical_output"]).resolve()
            document = CanonicalDocument.model_validate_json(
                canonical_path.read_text(encoding="utf-8")
            )
            if document.sha256 != item["sha256"]:
                raise ValueError(
                    f"Canonical SHA-256 does not match retrieval run: {canonical_path.name}"
                )
            documents.append(document)
            corpus_records.append(
                {
                    "source": item["source"],
                    "sha256": item["sha256"],
                    "canonical_output": str(canonical_path),
                    "pages": len(document.pages),
                }
            )
        summary["corpus"] = corpus_records
        _write_json(summary_path, summary)

        qrels_path = (
            project_root / "spike" / "data" / "ground_truth" / "retrieval_qrels.json"
        )
        qrels = _load_json(qrels_path)

        with ResourceMonitor() as resources:
            benchmark = RerankingBenchmark(
                documents,
                cache_folder=str(project_root / ".cache" / "sentence-transformers"),
                model_name=RERANKER_MODEL,
                units_per_page=args.units_per_page,
                batch_size=args.batch_size,
            )
            metrics, rankings = evaluate_reranking(
                benchmark,
                qrels["queries"],
                retrieval_rows,
                candidate_k=args.candidate_k,
            )

        model_max_length = getattr(benchmark.model, "max_seq_length", None)
        summary["runtime"] = {
            "documents": len(documents),
            "pages": len(benchmark.pages),
            "structural_units": len(benchmark.units),
            "model": RERANKER_MODEL,
            "model_max_length": model_max_length,
            "timings_seconds": {
                name: round(value, 6) for name, value in benchmark.timings.items()
            },
            "peak_memory_mb": round(resources.peak_memory_mb, 3),
            "package_versions": {
                "rank-bm25": importlib.metadata.version("rank-bm25"),
                "sentence-transformers": importlib.metadata.version(
                    "sentence-transformers"
                ),
                "numpy": importlib.metadata.version("numpy"),
            },
        }
        summary["metrics"] = metrics
        summary["quality_gate"] = metrics["quality_gate"]
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
