from __future__ import annotations

import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from benchmark.models import CanonicalDocument, Page, TableFragment


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
METHODS = (
    "page_bm25",
    "page_vector",
    "structural_bm25",
    "structural_vector",
    "hybrid_rrf",
)


@dataclass(frozen=True)
class PageRecord:
    page_id: str
    document: str
    page_number: int
    text: str


@dataclass(frozen=True)
class StructuralUnit:
    unit_id: str
    page_id: str
    document: str
    page_number: int
    kind: str
    text: str


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE)


def _table_header(table: TableFragment) -> str:
    headers = [cell.text.strip() for cell in table.cells if cell.is_column_header and cell.text.strip()]
    return " | ".join(headers)


def _table_rows(table: TableFragment) -> list[tuple[int, str]]:
    by_row: dict[int, list[Any]] = defaultdict(list)
    for cell in table.cells:
        by_row[cell.row].append(cell)
    return [
        (
            row_number,
            " | ".join(
                cell.text.strip()
                for cell in sorted(cells, key=lambda item: item.column)
                if cell.text.strip()
            ),
        )
        for row_number, cells in sorted(by_row.items())
    ]


def _nearest_heading(page: Page, y: float) -> str:
    candidates: list[tuple[float, str]] = []
    for block in page.blocks:
        if block.type not in {"title", "heading"} or not block.text.strip():
            continue
        for provenance in block.provenance:
            if provenance.page_number == page.page_number and provenance.bbox.y2 <= y + 0.01:
                candidates.append((provenance.bbox.y2, block.text.strip()))
    return max(candidates, default=(0.0, ""))[1]


def build_records(documents: list[CanonicalDocument]) -> tuple[list[PageRecord], list[StructuralUnit]]:
    pages: list[PageRecord] = []
    units: list[StructuralUnit] = []
    for document in documents:
        for page in document.pages:
            page_id = f"{document.source_filename}::p{page.page_number}"
            page_parts = [f"Document: {document.source_filename}", f"Page: {page.page_number}"]
            current_heading = ""
            for block in sorted(page.blocks, key=lambda item: item.reading_order):
                text = block.text.strip()
                if not text:
                    continue
                if block.type in {"title", "heading"}:
                    current_heading = text
                section = " > ".join(block.section_path) or current_heading
                context = [f"Document: {document.source_filename}", f"Page: {page.page_number}"]
                if section and section != text:
                    context.append(f"Section: {section}")
                context.append(f"{block.type}: {text}")
                unit_text = "\n".join(context)
                units.append(
                    StructuralUnit(
                        unit_id=f"{document.document_id}:{block.block_id}",
                        page_id=page_id,
                        document=document.source_filename,
                        page_number=page.page_number,
                        kind=f"block:{block.type}",
                        text=unit_text,
                    )
                )
                page_parts.append(text)

            for table in page.tables:
                table_y = min(provenance.bbox.y1 for provenance in table.provenance)
                heading = _nearest_heading(page, table_y)
                header = _table_header(table)
                caption = (table.caption or "").strip()
                for row_number, row_text in _table_rows(table):
                    if not row_text:
                        continue
                    context = [
                        f"Document: {document.source_filename}",
                        f"Page: {page.page_number}",
                    ]
                    if heading:
                        context.append(f"Section: {heading}")
                    if caption:
                        context.append(f"Table caption: {caption}")
                    if header and header != row_text:
                        context.append(f"Table columns: {header}")
                    context.append(f"Table row: {row_text}")
                    units.append(
                        StructuralUnit(
                            unit_id=f"{document.document_id}:{table.table_id}-r{row_number}",
                            page_id=page_id,
                            document=document.source_filename,
                            page_number=page.page_number,
                            kind="table_row",
                            text="\n".join(context),
                        )
                    )
                    page_parts.append(row_text)

            pages.append(
                PageRecord(
                    page_id=page_id,
                    document=document.source_filename,
                    page_number=page.page_number,
                    text="\n".join(page_parts),
                )
            )
    return pages, units


def _rank_indices(scores: np.ndarray, allowed: list[int]) -> list[int]:
    return sorted(allowed, key=lambda index: (-float(scores[index]), index))


def _aggregate_units(
    scores: np.ndarray,
    units: list[StructuralUnit],
    allowed: list[int],
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    ranked_units = _rank_indices(scores, allowed)
    page_scores: dict[str, float] = {}
    evidence: dict[str, dict[str, Any]] = {}
    for unit_index in ranked_units:
        unit = units[unit_index]
        score = float(scores[unit_index])
        if unit.page_id not in page_scores or score > page_scores[unit.page_id]:
            page_scores[unit.page_id] = score
            evidence[unit.page_id] = {
                "unit_id": unit.unit_id,
                "kind": unit.kind,
                "score": score,
                "preview": unit.text[:500],
            }
    ranking = sorted(page_scores, key=lambda page_id: (-page_scores[page_id], page_id))
    return ranking, evidence


def _rrf(rankings: list[list[str]], k: int = 60) -> tuple[list[str], dict[str, float]]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, page_id in enumerate(ranking, start=1):
            scores[page_id] += 1.0 / (k + rank)
    return sorted(scores, key=lambda page_id: (-scores[page_id], page_id)), dict(scores)


class RetrievalBenchmark:
    def __init__(
        self,
        documents: list[CanonicalDocument],
        cache_folder: str,
        model_name: str = MODEL_NAME,
    ) -> None:
        self.timings: dict[str, float] = {}
        started = time.perf_counter()
        self.pages, self.units = build_records(documents)
        self.timings["record_building"] = time.perf_counter() - started

        self.page_by_id = {page.page_id: page for page in self.pages}
        self.page_indices_by_document: dict[str, list[int]] = defaultdict(list)
        for index, page in enumerate(self.pages):
            self.page_indices_by_document[page.document].append(index)
        self.unit_indices_by_document: dict[str, list[int]] = defaultdict(list)
        for index, unit in enumerate(self.units):
            self.unit_indices_by_document[unit.document].append(index)

        started = time.perf_counter()
        self.page_bm25 = BM25Okapi([tokenize(page.text) for page in self.pages])
        self.unit_bm25 = BM25Okapi([tokenize(unit.text) for unit in self.units])
        self.timings["bm25_indexing"] = time.perf_counter() - started

        started = time.perf_counter()
        self.model = SentenceTransformer(model_name, device="cpu", cache_folder=cache_folder)
        self.model_name = model_name
        self.timings["model_loading"] = time.perf_counter() - started

        started = time.perf_counter()
        self.page_embeddings = self.model.encode_document(
            [page.text for page in self.pages],
            batch_size=16,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        self.unit_embeddings = self.model.encode_document(
            [unit.text for unit in self.units],
            batch_size=32,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        self.timings["embedding_indexing"] = time.perf_counter() - started

    def search(self, query: str, document: str, top_k: int = 10) -> dict[str, Any]:
        if document not in self.page_indices_by_document:
            raise KeyError(f"Document is not indexed: {document}")
        page_indices = self.page_indices_by_document[document]
        unit_indices = self.unit_indices_by_document[document]
        query_tokens = tokenize(query)

        method_timings: dict[str, float] = {}
        started = time.perf_counter()
        page_bm25_scores = np.asarray(self.page_bm25.get_scores(query_tokens))
        page_bm25_indices = _rank_indices(page_bm25_scores, page_indices)
        page_bm25_ranking = [self.pages[index].page_id for index in page_bm25_indices]
        method_timings["page_bm25"] = time.perf_counter() - started

        started = time.perf_counter()
        query_embedding = self.model.encode_query(
            query,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        page_vector_scores = self.page_embeddings @ query_embedding
        page_vector_indices = _rank_indices(page_vector_scores, page_indices)
        page_vector_ranking = [self.pages[index].page_id for index in page_vector_indices]
        method_timings["page_vector"] = time.perf_counter() - started

        started = time.perf_counter()
        unit_bm25_scores = np.asarray(self.unit_bm25.get_scores(query_tokens))
        structural_bm25_ranking, bm25_evidence = _aggregate_units(
            unit_bm25_scores, self.units, unit_indices
        )
        method_timings["structural_bm25"] = time.perf_counter() - started

        started = time.perf_counter()
        unit_vector_scores = self.unit_embeddings @ query_embedding
        structural_vector_ranking, vector_evidence = _aggregate_units(
            unit_vector_scores, self.units, unit_indices
        )
        method_timings["structural_vector"] = time.perf_counter() - started

        started = time.perf_counter()
        hybrid_ranking, hybrid_scores = _rrf(
            [
                page_bm25_ranking,
                page_vector_ranking,
                structural_bm25_ranking,
                structural_vector_ranking,
            ]
        )
        method_timings["hybrid_rrf"] = time.perf_counter() - started

        rankings = {
            "page_bm25": page_bm25_ranking,
            "page_vector": page_vector_ranking,
            "structural_bm25": structural_bm25_ranking,
            "structural_vector": structural_vector_ranking,
            "hybrid_rrf": hybrid_ranking,
        }
        score_maps = {
            "page_bm25": {
                self.pages[index].page_id: float(page_bm25_scores[index])
                for index in page_bm25_indices
            },
            "page_vector": {
                self.pages[index].page_id: float(page_vector_scores[index])
                for index in page_vector_indices
            },
            "structural_bm25": {
                page_id: details["score"] for page_id, details in bm25_evidence.items()
            },
            "structural_vector": {
                page_id: details["score"] for page_id, details in vector_evidence.items()
            },
            "hybrid_rrf": hybrid_scores,
        }
        evidence_maps = {
            "structural_bm25": bm25_evidence,
            "structural_vector": vector_evidence,
        }

        results: dict[str, Any] = {}
        for method, ranking in rankings.items():
            results[method] = {
                "latency_seconds": round(method_timings[method], 6),
                "pages": [
                    {
                        "page_id": page_id,
                        "page_number": self.page_by_id[page_id].page_number,
                        "score": score_maps[method].get(page_id),
                        "evidence": evidence_maps.get(method, {}).get(page_id),
                        "preview": self.page_by_id[page_id].text[:500],
                    }
                    for page_id in ranking[:top_k]
                ],
            }
        return results


def _metrics_for_ranking(ranked_pages: list[int], relevant_pages: set[int]) -> dict[str, float]:
    values: dict[str, float] = {}
    for k in (1, 2, 3, 5):
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
        (1.0 / math.log2(rank + 1))
        for rank, page_number in enumerate(ranked_pages[:5], start=1)
        if page_number in relevant_pages
    )
    ideal_hits = min(5, len(relevant_pages))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    values["ndcg@5"] = dcg / idcg if idcg else 0.0
    return values


def evaluate_queries(
    index: RetrievalBenchmark,
    queries: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    per_query: list[dict[str, Any]] = []
    metric_values: dict[str, dict[str, list[float]]] = {
        method: defaultdict(list) for method in METHODS
    }
    latencies: dict[str, list[float]] = {method: [] for method in METHODS}

    for query in queries:
        results = index.search(query["query"], query["document"], top_k=10)
        row = {
            "query_id": query["query_id"],
            "document": query["document"],
            "query": query["query"],
            "relevant_pages": query["relevant_pages"],
            "methods": {},
        }
        relevant = set(query["relevant_pages"])
        for method in METHODS:
            ranked_pages = [item["page_number"] for item in results[method]["pages"]]
            metrics = _metrics_for_ranking(ranked_pages, relevant)
            for name, value in metrics.items():
                metric_values[method][name].append(value)
            latencies[method].append(results[method]["latency_seconds"])
            row["methods"][method] = {
                "metrics": metrics,
                "latency_seconds": results[method]["latency_seconds"],
                "ranking": results[method]["pages"],
            }
        per_query.append(row)

    aggregates: dict[str, Any] = {}
    for method in METHODS:
        aggregates[method] = {
            name: round(mean(values), 6)
            for name, values in metric_values[method].items()
        }
        aggregates[method]["mean_query_latency_seconds"] = round(mean(latencies[method]), 6)
        aggregates[method]["max_query_latency_seconds"] = round(max(latencies[method]), 6)

    best_method = max(
        METHODS,
        key=lambda method: (
            aggregates[method]["recall@3"],
            aggregates[method]["mrr@5"],
            aggregates[method]["ndcg@5"],
            -aggregates[method]["mean_query_latency_seconds"],
        ),
    )
    return {
        "query_count": len(queries),
        "methods": aggregates,
        "best_method_by_recall3_then_mrr": best_method,
    }, per_query
