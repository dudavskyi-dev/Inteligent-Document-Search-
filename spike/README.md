# User-Run Decision Spikes

This folder contains five focused experiments: parsing, cross-page table stitching, retrieval,
reranking, and GLiNER extraction candidacy. Saved runs are indexed in
[`results/README.md`](results/README.md); required public inputs and hashes are documented in
[`data/README.md`](data/README.md).

The assistant prepared the scripts but did not execute the benchmarks. The user ran each test and
the repository retains its machine-readable output. Results support architecture decisions; they do
not constitute a complete application acceptance test.

## Parsing question

## Question

Which parser strategy should the architecture blueprint select?

- **A — full raster:** render every PDF page and process it with PaddleOCR PP-StructureV3.
- **B — hybrid:** use native Docling parsing when a page has a usable text layer and OCR only when it does not.

Google Document AI is documented in the blueprint as a managed alternative, but is not required for this local benchmark.

## Folder contract

```text
spike/
  data/
    inputs/             representative PDFs (not committed if confidential)
    ground_truth/       manually verified JSON
  outputs/
    full_raster/        normalized parser output
    hybrid/             normalized parser output
  results/
    metrics.json        measured results
    decision.md         short conclusion copied into the blueprint
  src/
    benchmark/          runner, common schema, metrics, parser adapters
```

## Minimum dataset

Use 10–20 documents, including at least:

- two native PDFs;
- two scans;
- two mixed native/scanned PDFs;
- two multi-column documents;
- two documents with tables spanning pages.

Do not decide from one convenient PDF. The relevant documents should resemble the actual industrial tenders/specifications.

## Measurements

| Metric | How to measure |
|--------|----------------|
| Text quality | Character/word accuracy against checked text samples |
| Table quality | Exact cell match and row/column structure match |
| Reading order | Correct ordered block pairs / all checked pairs |
| Evidence | Percentage of checked text/table values with a usable page bounding box |
| Multi-page tables | Stitching precision and recall |
| Runtime | Wall-clock seconds and seconds/page |
| Resources | Peak process memory; GPU memory if applicable |

## Decision rule

Parsing quality is the primary criterion. Runtime decides only when the quality difference is small. A strategy cannot win if it loses source coordinates or corrupts multi-page tables, even if it is faster.

## Reproducibility

The eventual runner must record:

- input SHA-256;
- parser and model versions;
- rendering DPI;
- OCR language configuration;
- CPU/GPU device;
- elapsed time;
- normalized output schema version.

## User-run parsing benchmark

The assistant prepares the benchmark but does not execute it. From the repository root,
first create the project-local environment and generate the two fixtures:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\setup_parsing.ps1
powershell -ExecutionPolicy Bypass -File .\spike\build_parsing_fixtures.ps1
```

`setup_parsing.ps1` keeps the virtual environment and package/model caches inside the repository.
Fixture generation requires Poppler `pdftoppm`; pass `-PdftoppmPath` if it is not on `PATH`.
Then the user runs:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\run_parsing_benchmark.ps1
```

The benchmark runs the same seven visual pages through:

1. Docling-only on the mixed fixture as a diagnostic baseline;
2. full-raster PaddleOCR on the scan fixture;
3. page-routed Hybrid on the mixed fixture.

Paddle and Hybrid can take several minutes on CPU and may download models into the
project-local `.cache` during their first run.

Every run creates:

```text
spike/results/parsing/<UTC-run-id>/summary.json
spike/results/parsing/<UTC-run-id>/outputs/*.json
spike/logs/parsing/<UTC-run-id>.log
spike/results/parsing/latest.txt
```

`summary.json` is updated after each parser, so completed measurements survive a later
failure or interruption. A successful full run has top-level `"status": "success"`.
The content F1 values are cross-parser agreement diagnostics, not human-verified accuracy.
The runner also rejects a canonical output when page sequence, evidence provenance, or
the fixture's native source-page markers are inconsistent.
After the run, send the path stored in `spike/results/parsing/latest.txt` to the assistant.

To regenerate and validate only the Hybrid artifact after adapter changes, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\run_parsing_benchmark.ps1 -Only hybrid
```

## User-run table-stitching spike

The stitching spike consumes the successful Hybrid canonical output referenced by
`spike/results/parsing/latest.txt`. Run it from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\run_table_stitching.ps1
```

It evaluates the last table on page N against the first table on page N+1 for six
manually labelled boundaries. The precision-first rules use page-boundary position,
horizontal overlap, column alignment, header similarity, and meaningful content before
or after a fragment. The stitcher groups source fragments; it never invents missing OCR
cells and never removes source cells or repeated headers.

Artifacts are written to:

```text
spike/results/stitching/<UTC-run-id>/summary.json
spike/results/stitching/<UTC-run-id>/decisions.json
spike/results/stitching/<UTC-run-id>/logical_tables.json
spike/logs/stitching/<UTC-run-id>.log
spike/results/stitching/latest.txt
```

The top-level status is `success` only when precision, recall, and F1 are all 1.0 on the
small labelled fixture, every candidate is labelled, and every source fragment and cell
is preserved exactly once. This is a focused spike gate, not a production-wide quality
claim; more document families must be added before production rollout.

## User-run retrieval spike

The retrieval benchmark uses 14 manually checked queries across all three source PDFs.
Each query searches only inside its named document, matching the production workflow for
an uploaded PDF. It compares:

1. whole-page BM25;
2. whole-page dense vectors;
3. layout block/table-row BM25 aggregated back to pages;
4. layout block/table-row vectors aggregated back to pages;
5. reciprocal-rank fusion (RRF) over all four rankings.

Reranking is deliberately excluded here and is evaluated in the next spike.

First install the retrieval dependencies into the existing project-local `.venv`:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\setup_retrieval.ps1
```

Then run the benchmark:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\run_retrieval.ps1
```

The first run uses Docling to build canonical JSON for 104 pages and downloads
`sentence-transformers/all-MiniLM-L6-v2` into the project-local `.cache`; it can take
several minutes. Canonical documents are reused on later runs. Use `-RebuildCorpus` only
when the parser or source PDFs changed.

Artifacts are written to:

```text
spike/results/retrieval/runs/<UTC-run-id>/summary.json
spike/results/retrieval/runs/<UTC-run-id>/rankings.json
spike/results/retrieval/runs/<UTC-run-id>/corpus_manifest.json
spike/results/retrieval/corpus/*.docling.json
spike/logs/retrieval/<UTC-run-id>.log
spike/results/retrieval/latest.txt
```

`status: success` means the experiment completed. `quality_gate.passed` separately shows
whether the best method reached mean Recall@3 >= 0.80 and MRR@5 >= 0.85. The report also
contains Recall@1/2/3/5, Hit@K, nDCG@5, query latency, indexing time, peak memory, package
versions, and the top ten pages/evidence previews for every query and method.

### Retrieval result

Run `20260816T214507Z` completed successfully and passed the quality gate. Structural
BM25 was the best precision-oriented baseline (Recall@3 `0.893`, Hit@3 `1.0`, MRR@5
`0.964`). Hybrid RRF gave the highest candidate-pool Recall@5 (`0.964`). Whole-page dense
retrieval was weaker as a standalone method. The selected design and limitations are
recorded in `spike/results/retrieval_decision.md`; reranking remains a separate spike.

References:

- [Sentence Transformers semantic search](https://sbert.net/examples/sentence_transformer/applications/semantic-search/README.html)
- [all-MiniLM-L6-v2 model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- [rank-bm25](https://github.com/dorianbrown/rank_bm25)

## User-run reranking spike

This benchmark reuses the successful retrieval run, its cached canonical documents, and
the same 14 manually checked queries. It does not parse the PDFs or rebuild retrieval
embeddings. For the top ten `hybrid_rrf` candidates it compares:

1. the unchanged hybrid ranking;
2. a local CrossEncoder applied to the whole page;
3. the same CrossEncoder applied to the five most lexically relevant layout blocks or
   table rows per candidate page, with the best unit score aggregated to the page.

The whole-page and structural variants are separate because transformer input is finite:
whole-page scoring may truncate the useful passage, while structural scoring retains the
layout unit and evidence ID. The model is a non-generative local reranker, not an LLM API.

Install or confirm the dependencies inside the existing project-local `.venv`:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\setup_reranking.ps1
```

Run the benchmark with the frozen defaults:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\run_reranking.ps1
```

The first run downloads `cross-encoder/ms-marco-MiniLM-L6-v2` into the project-local
`.cache`. Outputs are saved to:

```text
spike/results/reranking/runs/<UTC-run-id>/summary.json
spike/results/reranking/runs/<UTC-run-id>/rankings.json
spike/results/reranking/latest.txt
spike/logs/reranking/<UTC-run-id>.log
```

The report includes candidate-pool Recall@10, Recall/Hit@1/2/3/5, MRR@5, nDCG@5,
per-query and maximum latency, peak memory, selected evidence units, and deltas against
the unchanged hybrid ranking. The quality gate passes only if the best reranker does not
lower Recall@3 or MRR@5 and improves at least one of Recall@3, MRR@5, or nDCG@5 by 0.01.

References:

- [Sentence Transformers: Retrieve & Re-Rank](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html)
- [Sentence Transformers: Cross-Encoders](https://www.sbert.net/examples/cross_encoder/applications/README.html)
- [ms-marco-MiniLM-L6-v2 model card](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2)

### Reranking result

Run `20260816T220643Z` completed successfully and passed the quality gate. Structural
CrossEncoder reranking improved Recall@3 from `0.893` to `0.929`, preserved Recall@5 at
`0.964` and MRR@5 at `0.881`, and required `1.301 s` mean CPU time per query with
`672.25 MB` peak memory. Whole-page reranking lowered Recall@3 to `0.857` and is rejected.
The conditional production decision and query-level regressions are documented in
`spike/results/reranking_decision.md`.

## User-run GLiNER extraction spike

This spike tests whether a local, non-generative zero-shot NER model can propose spans for
the five fields required by Task 9: parts/models, quantities, tolerances or acceptance
criteria, deadlines or performance periods, and prices or fees. It evaluates 10 exact
real-document excerpts, one row derived from a real NASA table, and three explicitly
synthetic industrial examples. Real, derived, and synthetic metrics remain separate.

The model runs once at threshold `0.2`; the saved scores are then evaluated at `0.2`,
`0.3`, `0.4`, and `0.5` without repeating inference. Reports include exact-span and
relaxed-span precision/recall/F1, per-label quality, latency, memory, and all predicted
spans with their source page and evidence ID.

This is deliberately an entity-candidate test. GLiNER does not by itself prove that a
quantity belongs to a particular part, assemble table rows into the final ERP schema, or
validate units and business constraints.

Install the dependency in the existing local `.venv`:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\setup_gliner.ps1
```

Run the frozen benchmark:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\run_gliner.ps1
```

The first run downloads `gliner-community/gliner_small-v2.5` into the project-local
`.cache`. Outputs are saved to:

```text
spike/results/gliner/runs/<UTC-run-id>/summary.json
spike/results/gliner/runs/<UTC-run-id>/predictions.json
spike/results/gliner/latest.txt
spike/logs/gliner/<UTC-run-id>.log
```

The quality gate requires real relaxed-span F1 >= `0.70`, overall exact-span F1 >=
`0.60`, and relaxed recall >= `0.50` for every required label. Passing the gate means the
model is useful as an extraction candidate generator, not that autonomous ERP export is
safe.

References:

- [Official GLiNER repository](https://github.com/urchade/GLiNER)
- [gliner_small-v2.5 model card](https://huggingface.co/gliner-community/gliner_small-v2.5)

### GLiNER result

Run `20260816T222224Z` completed successfully but failed the quality gate. At the best
threshold (`0.5`), real-document exact F1 was `0.303` and relaxed F1 was `0.424`; peak
memory was `1852.137 MB`. Synthetic relaxed F1 (`0.783`) substantially overstated the
performance observed on real source language. Zero-shot GLiNER is therefore rejected as
the final ERP-schema extractor. The error analysis and selected deterministic-first plus
schema-constrained-LLM alternative are documented in `spike/results/gliner_decision.md`.
