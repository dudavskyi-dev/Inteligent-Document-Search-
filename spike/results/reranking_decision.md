# Reranking decision

Status: **conditionally selected after local spike**

Benchmark run: `20260816T220643Z` (`status: success`, quality gate passed)

## Decision

For the accuracy-first path, rerank the top ten hybrid retrieval candidates with
`cross-encoder/ms-marco-MiniLM-L6-v2` over structural units rather than whole pages:

1. take top-10 pages from hybrid RRF;
2. expand that pool with every page explicitly linked to a candidate through a stitched
   logical table;
3. for each candidate page, preselect five layout blocks or table rows with BM25;
4. score each `(query, structural unit)` pair with the local CrossEncoder;
5. use the best unit score as the page score and retain that unit as evidence;
6. send the best three seed pages to extraction and retain every continuation page linked
   through any selected stitched table.

Preserve the original hybrid rank and score in the result for audit and fallback. The
reranker must never discard an explicitly linked fragment of a logical table. For a
latency-sensitive deployment, hybrid RRF without reranking remains a valid fallback.

Whole-page CrossEncoder reranking is rejected: it lowered Recall@3 and nDCG@5, added
latency, and is vulnerable to truncation of long pages at the model's 512-token limit.

## Measured evidence

| Method | Recall@1 | Recall@3 | Recall@5 | MRR@5 | nDCG@5 | Mean latency/query |
|---|---:|---:|---:|---:|---:|---:|
| Hybrid RRF baseline | **0.571** | 0.893 | **0.964** | **0.881** | **0.867** | already retrieved |
| Whole-page CrossEncoder | **0.571** | 0.857 | 0.893 | **0.881** | 0.830 | 0.952 s |
| Structural CrossEncoder | 0.536 | **0.929** | **0.964** | **0.881** | 0.864 | 1.301 s |

The structural reranker improved Recall@3 by `0.035714`, preserved Recall@5 and MRR@5,
and lowered nDCG@5 by `0.003324`. Its maximum measured query latency was 1.648 seconds.
Model loading took 7.118 seconds and peak process memory was 672.25 MB.

The top-10 candidate pool had mean Recall@10 of 0.964. The only candidate-pool miss was
GSA price-schedule page 25: page 24 was present, but page 25 was absent even at top ten.
No reranker can recover a page outside its candidate pool. The existing table-stitching
link between pages 24 and 25 must therefore expand the candidate set before final
selection.

## Query-level observations

- Structural reranking moved both relevant pages into top three for DOE cost/fee and DOE
  due-date rules.
- It moved one DOE resume page out of top three.
- It corrected top one for GSA price schedule, DOE submission volumes, and NASA packaging.
- It worsened top one for GSA period of performance, NASA traceability, and NASA sampling.

This mixed behavior is why the choice is conditional rather than a claim that reranking
always improves ranking quality.

## Limitations

- The evaluation contains 14 English queries across three government documents.
- The net Recall@3 gain represents a small number of page movements and needs a larger
  frozen evaluation set before production rollout.
- The test used five BM25-preselected units per page and one English MS MARCO model; other
  unit counts, languages, or domain-specific models may change the result.
- Sequential per-query CPU latency was measured. Batched multi-field production latency
  was not measured.
- Page relevance does not yet prove correct field extraction or bounding-box evidence.

## Blueprint text

Use a local structural CrossEncoder as an optional accuracy-first reranker over the top
ten hybrid candidates. Score five BM25-preselected layout blocks or table rows per page,
aggregate the best unit score to the page, retain the unit ID as evidence, and select top
three pages plus all explicitly stitched table continuations. The spike improved Recall@3
from 0.893 to 0.929 while preserving Recall@5 and MRR@5, at 1.301 seconds mean CPU latency
per query and 672.25 MB peak memory. Keep hybrid RRF as the latency-first fallback and do
not use whole-page CrossEncoder reranking.
