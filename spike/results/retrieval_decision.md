# Retrieval decision

Status: **selected after local spike**

Benchmark run: `20260816T214507Z` (`status: success`, quality gate passed)

## Decision

Use layout-aware hybrid retrieval inside the uploaded document:

1. retrieve and score canonical layout blocks and table rows with BM25;
2. aggregate unit scores to their source pages;
3. build a high-recall candidate pool with RRF over page and structural BM25/vector
   rankings;
4. expand a retrieved page with explicitly stitched table fragments and other linked
   continuation pages before extraction;
5. pass the candidate pool to the separately evaluated reranker, then keep the best
   pages with their block/cell provenance.

If no reranker is available, use structural BM25 as the local fallback. It had the best
first-relevant-page ranking and found at least one relevant page in the top three for all
14 queries. Dense whole-page retrieval is not selected as a standalone method because it
was less accurate than the lexical and structure-aware alternatives on this dataset.

## Measured evidence

| Method | Recall@3 | Hit@3 | Recall@5 | MRR@5 | nDCG@5 | Mean query latency |
|---|---:|---:|---:|---:|---:|---:|
| Page BM25 | 0.821 | 0.929 | 0.857 | 0.857 | 0.812 | 0.000673 s |
| Page vector | 0.571 | 0.786 | 0.679 | 0.717 | 0.618 | 0.016848 s |
| Structural BM25 | **0.893** | **1.000** | 0.893 | **0.964** | **0.891** | 0.006886 s |
| Structural vector | 0.857 | 0.929 | 0.893 | 0.893 | 0.858 | 0.000710 s |
| Hybrid RRF | **0.893** | **1.000** | **0.964** | 0.881 | 0.867 | 0.000051 s fusion only |

The benchmark covered 14 manually checked queries, 3 documents, 104 pages, and 1,877
structural units. Index construction used 735.496 MB peak memory. Excluding the reusable
document parsing cache, model loading took 8.913 seconds and embedding indexing took
28.296 seconds.

## Interpretation

Structural BM25 is the strongest precision-oriented baseline: it tied for best Recall@3,
had Hit@3 of 1.0, and achieved the best MRR@5 and nDCG@5. Hybrid RRF is the strongest
candidate generator because it retained the greatest share of all labelled pages by
top five. This distinction matters for multi-page answers: finding one correct page is
not the same as collecting every page needed for extraction.

The remaining misses were predominantly continuation pages in multi-page answers. For
example, the GSA price-schedule query found page 24 but not page 25 in the hybrid top five.
Therefore stitched-table links and explicit document-structure links must expand the
candidate set; adjacency expansion must not be inferred blindly for every page.

## Limitations

- The evaluation has only 14 queries and three English-language government documents.
- Relevance is page-level. It does not yet measure whether the final field value and its
  exact bounding box were extracted correctly.
- The RRF latency above measures fusion only; the component retriever latencies and index
  creation costs still apply.
- The proposed linked-page expansion and reranking are design decisions to test next,
  not accuracy claims from this run.
- Embedding performance is specific to `all-MiniLM-L6-v2`; a domain model may behave
  differently, but this spike does not justify the extra vector-only complexity.

## Blueprint text

Retrieve canonical layout blocks and table rows with BM25 and aggregate them to source
pages. Use hybrid RRF as a high-recall candidate pool for reranking, retain structural
BM25 as the no-reranker fallback, and expand candidates through explicit stitched-table
links before extraction. In the local spike, structural BM25 achieved Recall@3 0.893,
Hit@3 1.0, and MRR@5 0.964; hybrid RRF achieved the best Recall@5 at 0.964. Whole-page
dense retrieval was not competitive as a standalone method.
