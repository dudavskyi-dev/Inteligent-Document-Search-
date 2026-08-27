from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from benchmark.context_assembly import build_llm_context
from benchmark.models import CanonicalDocument
from benchmark.table_stitching import stitch_document


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


def _latest_successful_retrieval(project_root: Path) -> dict[str, Any]:
    pointer = project_root / "spike" / "results" / "retrieval" / "latest.txt"
    if not pointer.is_file():
        raise FileNotFoundError("Run the retrieval spike first; latest.txt is missing.")
    summary_path = Path(pointer.read_text(encoding="utf-8").strip()).resolve()
    summary = _load_json(summary_path)
    if summary.get("status") != "success":
        raise ValueError(f"Latest retrieval run is not successful: {summary.get('status')!r}.")
    return summary


def _load_documents(retrieval_summary: dict[str, Any]) -> list[CanonicalDocument]:
    documents: list[CanonicalDocument] = []
    for item in retrieval_summary["corpus"]:
        canonical_path = Path(item["canonical_output"]).resolve()
        document = CanonicalDocument.model_validate_json(canonical_path.read_text(encoding="utf-8"))
        if document.sha256 != item["sha256"]:
            raise ValueError(f"Canonical SHA-256 does not match retrieval run: {canonical_path.name}")
        documents.append(document)
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Manual demo: for one qrels query, find the real top-ranked structural unit "
            "via the existing reranker, then print the chunk+neighbor / stitched-table "
            "context that build_llm_context() would send to an LLM extractor for it."
        )
    )
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--query-id", type=str, required=True)
    parser.add_argument("--candidate-k", type=int, default=10)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    _configure_environment(project_root)

    from benchmark.reranking import RERANKER_MODEL, RerankingBenchmark

    retrieval_summary = _latest_successful_retrieval(project_root)
    documents = _load_documents(retrieval_summary)

    qrels_path = project_root / "spike" / "data" / "ground_truth" / "retrieval_qrels.json"
    qrels = _load_json(qrels_path)
    query = next((item for item in qrels["queries"] if item["query_id"] == args.query_id), None)
    if query is None:
        raise KeyError(f"Query {args.query_id!r} is not in {qrels_path}.")

    retrieval_rankings_path = Path(retrieval_summary["artifacts"]["rankings"]).resolve()
    retrieval_rows = _load_json(retrieval_rankings_path)
    retrieval_row = next(
        (row for row in retrieval_rows if row["query_id"] == args.query_id), None
    )
    if retrieval_row is None:
        raise KeyError(f"Query {args.query_id!r} is missing from the retrieval rankings.")
    candidate_ids = [
        item["page_id"]
        for item in retrieval_row["methods"]["hybrid_rrf"]["ranking"][: args.candidate_k]
    ]

    benchmark = RerankingBenchmark(
        documents,
        cache_folder=str(project_root / ".cache" / "sentence-transformers"),
        model_name=RERANKER_MODEL,
    )
    results = benchmark.rerank(query["query"], candidate_ids)
    top_entry = results["structural_cross_encoder"]["ranking"][0]
    evidence = top_entry["evidence"]
    if evidence is None:
        raise ValueError("The top-ranked page has no structural evidence to build a chunk from.")
    top_unit_id = evidence["unit_id"]

    document = next(doc for doc in documents if doc.source_filename == query["document"])
    stitch_result = stitch_document(document)

    context = build_llm_context(document, stitch_result, top_unit_id)

    print(f"query_id={args.query_id}")
    print(f"query={query['query']}")
    print(f"top_unit_id={top_unit_id} (kind={evidence['kind']}, score={evidence['score']:.4f})")
    print("--- context that would be sent to the LLM extractor ---")
    print(context)


if __name__ == "__main__":
    main()
