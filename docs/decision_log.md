# Decision Log

This log separates ideas from measurements. “Tested” means the user ran the repository spike and
the saved artifact exists under `spike/results/`. “Designed” or “researched” is not an accuracy
claim. The source column distinguishes the earlier attached blueprint from the later discussion and
the implemented spikes.

| # | Decision point | Options considered | Status and result | Current decision | Source |
|---:|---|---|---|---|---|
| 1 | Duplicate processing | SHA-256; document business key; no deduplication | **Designed, not end-to-end tested.** | Stream SHA-256 before expensive work. Reuse only a compatible parser/pipeline/schema result; store changed bytes as a new file version. | Earlier blueprint + discussion |
| 2 | Native PDF parsing | PyMuPDF; Docling; pdfplumber; pypdf | **Docling tested.** Seven pages: 33.08 s, 4.73 s/page, 1.63 GB peak RSS. PyMuPDF was used for inspection/routing, not benchmarked as the final layout parser. | Docling is the local native/layout parser. PyMuPDF-style checks may route pages. | Earlier blueprint + parsing spike |
| 3 | Rasterize every page | PaddleOCR/PP-StructureV3 on full-page images | **Tested and rejected as default.** Seven pages: 211.80 s, 30.26 s/page, 1.23 GB peak RSS; about 6.4× slower than Docling. | Keep only as a documented offline alternative, not the normal production path. | Discussion + parsing spike |
| 4 | Hybrid parsing | Native parser for usable text; OCR for scan/broken pages | **Tested locally.** Four Docling + three Paddle pages: 112.83 s, 16.12 s/page, 1.97 GB peak RSS. Provenance/source-page checks passed. | Route per page, but use a managed OCR/layout fallback instead of local Paddle by default. | Discussion + parsing spike |
| 5 | Managed parsing | Document AI OCR, Form Parser, Layout Parser | **Researched, not tested against the PDFs.** | Local-first blueprint uses managed parsing only for rejected pages. Google-native blueprint uses Layout Parser once for all content. Choose the exact processor through a cloud bake-off. | Discussion + official Google docs |
| 6 | One parser-neutral document structure | Keep separate parser outputs; canonical collector with page/block/table/cell evidence | **Implemented in the spikes and structurally validated.** It preserved page sequence and provenance; it is not yet a production database contract. | One canonical evidence model is mandatory before stitching, search, extraction, and review. | Discussion + parsing spike |
| 7 | Tables across pages | Keep separate; LLM judges continuation; deterministic geometry/header rules | **Deterministic spike tested.** Six labelled boundaries: TP 3, TN 3, precision/recall/F1 1.0, 0.008855 s; 7/7 fragments and 189/189 cells preserved. | Precision-first deterministic stitching. Ambiguous cases remain separate for review; optional LLM advice is non-authoritative. | Earlier blueprint + discussion + stitching spike |
| 8 | Storage/search granularity | Whole document; whole page; fixed chunks; layout blocks/table rows; headings/table titles | **Partially tested.** The retrieval corpus contained 104 pages and 1,877 structural units. A production PostgreSQL/pgvector or Agent Search datastore was not built. | Store canonical evidence once. Index structural units with page, section path, table context, and evidence IDs; aggregate results to pages and expand linked table fragments. | Discussion + retrieval spike |
| 9 | Lexical retrieval | Page BM25; structural BM25 | **Tested.** Structural BM25: Recall@3 0.893, Hit@3 1.0, MRR@5 0.964; better than page BM25. | Structural BM25 is the strong local fallback. | Discussion + retrieval spike |
| 10 | Dense retrieval | Whole-page vectors; structural vectors | **Tested.** Whole-page vectors were weak standalone (Recall@3 0.571). Structural vectors reached Recall@3 0.857. | Do not use whole-page vector search alone. Dense structural search can add candidate diversity. | Discussion + retrieval spike |
| 11 | Retrieval fusion | One retriever; reciprocal-rank fusion (RRF) | **Tested.** Hybrid RRF had Recall@3 0.893 and the best Recall@5 0.964. | Use RRF as a high-recall candidate pool; preserve component rankings for audit. | Discussion + retrieval spike |
| 12 | Search by document structure | Compare query with headings, section paths, table titles, table rows | **Partially tested.** Structural BM25/vector units included layout/table context. A separate title-only or section-tree router was not isolated. | Include structure as fields/features; do not claim a separate heading-router benchmark. | Discussion + retrieval spike |
| 13 | Reranking | No reranker; whole-page CrossEncoder; structural CrossEncoder | **Tested.** Structural reranking improved Recall@3 0.893→0.929, kept Recall@5 0.964, cost 1.301 s/query and 672 MB. Whole-page reranking regressed. | Optional structural CrossEncoder for accuracy-first local deployments; use base hybrid retrieval when latency matters. | Discussion + reranking spike |
| 14 | GLiNER entity extraction | Zero-shot GLiNER as final extractor or candidate highlighter | **Tested and rejected as final extractor.** Best real relaxed F1 0.424, exact F1 0.303, peak memory 1.85 GB. | Do not use GLiNER in the default production path. Synthetic quality must not be treated as real-document quality. | Discussion + GLiNER spike |
| 15 | Final structured extraction | Regex only; GLiNER; whole-document LLM; retrieved pages + local/cloud LLM; *(under evaluation, not yet tested here)* chunk + immediate neighbor chunk for non-table content, whole stitched table for table content | **Designed, not tested end-to-end.** No LLM/API was available locally. | Retrieve top-three pages per field family, add linked table continuations, and let a configurable LLM read those pages and return the complete strict candidate JSON with evidence IDs and abstention. Deterministic code validates the response; it is not the principal extractor. The chunk+neighbor/stitched-table alternative is recorded as a candidate to compare against this on the same frozen evaluation set; this row will be updated with the result and a decision once it is tested (see `architecture_blueprint.md`, "Alternative under evaluation"). | Earlier blueprint + discussion |
| 16 | Validation | Put checks in prompt; Python only; typed schema + normalizers + versioned rules | **Designed, not end-to-end tested.** | JSON Schema/Pydantic boundary, deterministic decimal/date/unit/tolerance rules, part-master lookups, arithmetic/conflict checks. LLM output is never trusted directly. | Earlier blueprint |
| 17 | Human review | Straight-through by confidence; review failures only; review every document | **Designed, UI not built.** | Mandatory review for every document. Show exact page/bbox evidence; log every edit and explicit approval. | Earlier blueprint + task requirement |
| 18 | ERP hand-off | Direct database write; staging API; downloadable JSON | **Contract specified, integration not tested.** | Export only the approved versioned JSON contract to a staging adapter or file. | Earlier blueprint + current blueprint |
| 19 | Local deployment | One process; Docker Compose services; Kubernetes | **Designed, not deployed.** | Containerize API/workers and dependencies; choose Compose for a small company-hosted installation and scale only when required. | Earlier blueprint |
| 20 | Google-native deployment | Cloud Run, Cloud Storage, Cloud SQL, Workflows/Pub/Sub, Document AI, Agent Search, Vertex AI | **Researched, not cloud-tested.** | Maintain as a complete alternative blueprint with its own cost and security/residency gates. | Discussion + official Google docs |
| 21 | Earlier model/parser shortlist | PaddleOCR-VL 1.6; PP-StructureV3; Tesseract; Qwen3-14B/vLLM; Docling | **Only Docling and PP-StructureV3 were exercised in the current spikes.** PaddleOCR-VL, Tesseract, Qwen3-14B, and vLLM were earlier proposals, not measured here. | Do not present untested proposals as selected based on benchmark evidence. | Attached earlier blueprint |

## Measured Decision Records

- Parsing: [`../spike/results/decision.md`](../spike/results/decision.md)
- Table stitching: [`../spike/results/stitching_decision.md`](../spike/results/stitching_decision.md)
- Retrieval: [`../spike/results/retrieval_decision.md`](../spike/results/retrieval_decision.md)
- Reranking: [`../spike/results/reranking_decision.md`](../spike/results/reranking_decision.md)
- GLiNER: [`../spike/results/gliner_decision.md`](../spike/results/gliner_decision.md)

## What Still Requires a Real Pilot

The repository has answered focused component questions, not proved the complete product. The next
release gates need representative company documents and labelled final fields:

1. Compare the selected local/managed parser path and Google Layout Parser on the same frozen set.
2. Expand table-stitch labels across suppliers and hard negatives.
3. Evaluate complete field and relation extraction, including line-row exact match and evidence
   accuracy, with at least one allowed local/cloud LLM.
4. Test validation, reviewer correction rate, review time, audit replay, and ERP staging idempotency.
5. Load/security/residency/cost test whichever architecture is selected.
