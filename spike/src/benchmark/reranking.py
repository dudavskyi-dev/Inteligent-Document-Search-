from __future__ import annotations

import math
import time
from collections import defaultdict
from statistics import mean
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from benchmark.models import CanonicalDocument
from benchmark.retrieval import PageRecord, StructuralUnit, build_records, tokenize


RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
METHODS = ("hybrid_rrf_baseline", "page_cross_encoder", "structural_cross_encoder")


def _rank(scores: dict[str, float], original_order: list[str]) -> list[str]:
    original_rank = {page_id: rank for rank, page_id in enumerate(original_order)}
    return sorted(
        original_order,
        key=lambda page_id: (-scores[page_id], original_rank[page_id]),
    )


def _metrics(ranked_pages: list[int], relevant_pages: set[int]) -> dict[str, float]:
    values: dict[str, float] = {}
    for k in (1, 2, 3, 5, 10):
        top = ranked_pages[:k]
        hits = sum(page in relevant_pages for page in top)
        values[f"recall@{k}"] = hits / len(relevant_pages)
        values[f"hit@{k}"] = float(hits > 0)

    reciprocal_rank = 0.0
    for rank, page_number in enumerate(ranked_pages[:5], start=1):
        if page_number in relevant_pages:
            reciprocal_rank = 1.0 / rank
            break
    values["mrr@5"] = reciprocal_rank

    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, page_number in enumerate(ranked_pages[:5], start=1)
        if page_number in relevant_pages
    )
    ideal_hits = min(5, len(relevant_pages))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    values["ndcg@5"] = dcg / idcg if idcg else 0.0
    return values


class RerankingBenchmark:
    def __init__(
        self,
        documents: list[CanonicalDocument],
        cache_folder: str,
        model_name: str = RERANKER_MODEL,
        units_per_page: int = 5,
        batch_size: int = 16,
    ) -> None:
        self.units_per_page = units_per_page
        self.batch_size = batch_size
        self.timings: dict[str, float] = {}

        started = time.perf_counter()
        self.pages, self.units = build_records(documents)
        self.page_by_id: dict[str, PageRecord] = {page.page_id: page for page in self.pages}
        self.unit_indices_by_page: dict[str, list[int]] = defaultdict(list)
        for index, unit in enumerate(self.units):
            self.unit_indices_by_page[unit.page_id].append(index)
        self.timings["record_building"] = time.perf_counter() - started

        started = time.perf_counter()
        self.unit_bm25 = BM25Okapi([tokenize(unit.text) for unit in self.units])
        self.timings["unit_bm25_indexing"] = time.perf_counter() - started

        started = time.perf_counter()
        self.model = CrossEncoder(
            model_name,
            device="cpu",
            cache_folder=cache_folder,
        )
        self.model_name = model_name
        self.timings["model_loading"] = time.perf_counter() - started

    def _predict(self, pairs: list[tuple[str, str]]) -> np.ndarray:
        if not pairs:
            return np.asarray([], dtype=float)
        return np.asarray(
            self.model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            ),
            dtype=float,
        ).reshape(-1)

    def _validate_candidates(self, candidate_ids: list[str]) -> None:
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("The candidate pool contains duplicate page IDs.")
        missing = [page_id for page_id in candidate_ids if page_id not in self.page_by_id]
        if missing:
            raise KeyError(f"Candidate pages are absent from the canonical corpus: {missing}")

    def rerank(self, query: str, candidate_ids: list[str]) -> dict[str, Any]:
        self._validate_candidates(candidate_ids)
        baseline = list(candidate_ids)

        started = time.perf_counter()
        page_scores_array = self._predict(
            [(query, self.page_by_id[page_id].text) for page_id in candidate_ids]
        )
        page_scores = {
            page_id: float(score) for page_id, score in zip(candidate_ids, page_scores_array)
        }
        page_ranking = _rank(page_scores, candidate_ids)
        page_latency = time.perf_counter() - started

        started = time.perf_counter()
        lexical_scores = np.asarray(self.unit_bm25.get_scores(tokenize(query)))
        selected_units: list[StructuralUnit] = []
        for page_id in candidate_ids:
            indices = sorted(
                self.unit_indices_by_page.get(page_id, []),
                key=lambda index: (-float(lexical_scores[index]), index),
            )[: self.units_per_page]
            if not indices:
                raise ValueError(f"Candidate page has no structural units: {page_id}")
            selected_units.extend(self.units[index] for index in indices)

        unit_scores_array = self._predict([(query, unit.text) for unit in selected_units])
        page_unit_scores: dict[str, float] = {page_id: -math.inf for page_id in candidate_ids}
        best_unit_by_page: dict[str, dict[str, Any]] = {}
        for unit, score_value in zip(selected_units, unit_scores_array):
            score = float(score_value)
            if score > page_unit_scores[unit.page_id]:
                page_unit_scores[unit.page_id] = score
                best_unit_by_page[unit.page_id] = {
                    "unit_id": unit.unit_id,
                    "kind": unit.kind,
                    "score": score,
                    "preview": unit.text[:500],
                }
        structural_ranking = _rank(page_unit_scores, candidate_ids)
        structural_latency = time.perf_counter() - started

        original_rank = {page_id: rank for rank, page_id in enumerate(candidate_ids, start=1)}

        def render(
            ranking: list[str],
            scores: dict[str, float] | None = None,
            evidence: dict[str, dict[str, Any]] | None = None,
        ) -> list[dict[str, Any]]:
            return [
                {
                    "page_id": page_id,
                    "page_number": self.page_by_id[page_id].page_number,
                    "retrieval_rank": original_rank[page_id],
                    "score": None if scores is None else scores[page_id],
                    "evidence": None if evidence is None else evidence.get(page_id),
                    "preview": self.page_by_id[page_id].text[:500],
                }
                for page_id in ranking
            ]

        return {
            "hybrid_rrf_baseline": {
                "latency_seconds": 0.0,
                "ranking": render(baseline),
            },
            "page_cross_encoder": {
                "latency_seconds": round(page_latency, 6),
                "ranking": render(page_ranking, page_scores),
            },
            "structural_cross_encoder": {
                "latency_seconds": round(structural_latency, 6),
                "scored_units": len(selected_units),
                "ranking": render(structural_ranking, page_unit_scores, best_unit_by_page),
            },
        }


def evaluate_reranking(
    benchmark: RerankingBenchmark,
    queries: list[dict[str, Any]],
    retrieval_rows: list[dict[str, Any]],
    candidate_k: int = 10,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    retrieval_by_id = {row["query_id"]: row for row in retrieval_rows}
    if len(retrieval_by_id) != len(retrieval_rows):
        raise ValueError("Retrieval rankings contain duplicate query IDs.")

    metric_values: dict[str, dict[str, list[float]]] = {
        method: defaultdict(list) for method in METHODS
    }
    latencies: dict[str, list[float]] = {method: [] for method in METHODS}
    per_query: list[dict[str, Any]] = []

    for query in queries:
        query_id = query["query_id"]
        if query_id not in retrieval_by_id:
            raise KeyError(f"Retrieval rankings are missing query: {query_id}")
        retrieval_row = retrieval_by_id[query_id]
        if retrieval_row["document"] != query["document"]:
            raise ValueError(f"Document mismatch in retrieval row for query: {query_id}")
        if retrieval_row["query"] != query["query"]:
            raise ValueError(f"Query text mismatch in retrieval row: {query_id}")
        if retrieval_row["relevant_pages"] != query["relevant_pages"]:
            raise ValueError(f"Relevance labels mismatch in retrieval row: {query_id}")
        source_ranking = retrieval_row["methods"]["hybrid_rrf"]["ranking"]
        candidate_ids = [item["page_id"] for item in source_ranking[:candidate_k]]
        if len(candidate_ids) < candidate_k:
            raise ValueError(
                f"Query {query_id} has only {len(candidate_ids)} candidates; "
                f"expected {candidate_k}."
            )

        results = benchmark.rerank(query["query"], candidate_ids)
        relevant = set(query["relevant_pages"])
        row: dict[str, Any] = {
            "query_id": query_id,
            "document": query["document"],
            "query": query["query"],
            "relevant_pages": query["relevant_pages"],
            "candidate_k": candidate_k,
            "methods": {},
        }
        for method in METHODS:
            ranked_pages = [
                item["page_number"] for item in results[method]["ranking"]
            ]
            metrics = _metrics(ranked_pages, relevant)
            for name, value in metrics.items():
                metric_values[method][name].append(value)
            latency = float(results[method]["latency_seconds"])
            latencies[method].append(latency)
            row["methods"][method] = {
                "metrics": metrics,
                **results[method],
            }
        per_query.append(row)

    aggregates: dict[str, dict[str, float]] = {}
    for method in METHODS:
        aggregates[method] = {
            name: round(mean(values), 6)
            for name, values in metric_values[method].items()
        }
        aggregates[method]["mean_query_latency_seconds"] = round(
            mean(latencies[method]), 6
        )
        aggregates[method]["max_query_latency_seconds"] = round(max(latencies[method]), 6)

    baseline = aggregates["hybrid_rrf_baseline"]
    rerankers = ("page_cross_encoder", "structural_cross_encoder")
    best_reranker = max(
        rerankers,
        key=lambda method: (
            aggregates[method]["recall@3"],
            aggregates[method]["mrr@5"],
            aggregates[method]["ndcg@5"],
            -aggregates[method]["mean_query_latency_seconds"],
        ),
    )
    best = aggregates[best_reranker]
    deltas = {
        metric: round(best[metric] - baseline[metric], 6)
        for metric in ("recall@1", "recall@3", "recall@5", "mrr@5", "ndcg@5")
    }
    quality_preserved = (
        best["recall@3"] >= baseline["recall@3"]
        and best["mrr@5"] >= baseline["mrr@5"]
    )
    materially_improved = max(deltas["recall@3"], deltas["mrr@5"], deltas["ndcg@5"]) >= 0.01

    return {
        "query_count": len(queries),
        "candidate_k": candidate_k,
        "candidate_pool_mean_recall@10": baseline["recall@10"],
        "methods": aggregates,
        "best_reranker_by_recall3_then_mrr": best_reranker,
        "best_reranker_delta_vs_hybrid": deltas,
        "quality_gate": {
            "recall@3_not_lower_than_hybrid": best["recall@3"] >= baseline["recall@3"],
            "mrr@5_not_lower_than_hybrid": best["mrr@5"] >= baseline["mrr@5"],
            "at_least_one_quality_metric_improves_by_0.01": materially_improved,
            "passed": quality_preserved and materially_improved,
        },
    }, per_query
