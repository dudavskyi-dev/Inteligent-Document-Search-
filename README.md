# Industrial Document Extraction — Architecture and Decision Spikes

This repository is a build-ready architecture, supported by focused,
user-run experiments. It is deliberately not a complete application.

## Demo

The local web app in [`workspace_local/`](workspace_local/) running one PDF end to end:
upload, hybrid parsing, table stitching, per-field-family retrieval and reranking,
context assembly, a single LLM call, and the validated result with a review-needed
badge per field.

https://github.com/user-attachments/assets/0f96ee77-5b90-4946-8b8c-004cfd434351

## Start Here
Here was made two architecture blueprints to consider all the avaliable possibilities of realization of this problem including the cost and perfomance.
1. Read the portable [`architecture_blueprint.md`](architecture_blueprint.md).
2. Compare the fully managed
   [`architecture_blueprint_google_cloud.md`](architecture_blueprint_google_cloud.md).
3. Inspect [`docs/decision_log.md`](docs/decision_log.md) to see which ideas were tested, rejected,
   selected, or remain unverified.
4. Inspect [`spike/results/README.md`](spike/results/README.md) for frozen runs and saved evidence.
5. Follow [`spike/README.md`](spike/README.md) only if you want to reproduce a spike locally.

## Architecture Variants

| Variant | Best fit | Primary parsing/search path | Main trade-off |
|---|---|---|---|
| Hybrid / local-first | Data/control portability and lower managed-service dependency | Docling native parsing, managed OCR only for rejected pages, PostgreSQL structural hybrid retrieval | More integration and operations work |
| Google Cloud native | Managed operations and fast elastic deployment | Document AI Layout Parser, Cloud Run, Agent Search, Vertex AI, Cloud SQL/Storage | Cloud dependency, data-residency review, and usage cost |

Both variants use the same strict ERP contract:

- [`contracts/extraction_candidate_v1.schema.json`](contracts/extraction_candidate_v1.schema.json)
- [`contracts/extraction_candidate_v1.example.json`](contracts/extraction_candidate_v1.example.json)
- [`contracts/industrial_document_v1.schema.json`](contracts/industrial_document_v1.schema.json)
- [`contracts/industrial_document_v1.example.json`](contracts/industrial_document_v1.example.json)

The retriever selects top-three seed pages per required field family and adds linked table
continuations. A configurable local or approved cloud LLM reads those pages and returns the complete
evidence-linked candidate JSON. Deterministic code validates the response; the LLM can abstain and
never approves or exports a document.

## Measured Conclusions

| Area | Result |
|---|---|
| Parsing | Docling processed seven native/mixed fixture pages in 33.08 s. Full-raster PaddleOCR took 211.80 s; corrected local hybrid took 112.83 s and 1.97 GB peak RSS. Select native Docling plus managed fallback, not local Paddle as default. |
| Table stitching | Deterministic rules classified six labelled boundaries with precision/recall/F1 1.0 in 0.008855 s and preserved all fragments/cells. Broader validation is still required. |
| Retrieval | Structural BM25 achieved Recall@3 0.893, Hit@3 1.0, MRR@5 0.964. Hybrid RRF produced the best candidate Recall@5, 0.964. |
| Reranking | Structural CrossEncoder improved Recall@3 to 0.929 at 1.301 s/query; whole-page reranking regressed. Keep it optional. |
| Extraction candidate | Zero-shot GLiNER failed: real relaxed F1 0.424, exact F1 0.303, peak memory 1.85 GB. It is not the final structured extractor. |

These are small decision spikes, not production-wide accuracy claims. Exact reports and limitations
are linked from [`spike/results/README.md`](spike/results/README.md).

## Reproduce Without Polluting the Machine

All scripts are intended to be run by the reviewer, not automatically by this repository. They use
the project-local `.venv/` and `.cache/`; generated logs remain under `spike/logs/`. The public input
sources, filenames, page counts, and SHA-256 hashes are documented in
[`spike/data/README.md`](spike/data/README.md).

Typical order:

```powershell
powershell -ExecutionPolicy Bypass -File .\spike\setup_parsing.ps1
powershell -ExecutionPolicy Bypass -File .\spike\build_parsing_fixtures.ps1
powershell -ExecutionPolicy Bypass -File .\spike\run_parsing_benchmark.ps1
powershell -ExecutionPolicy Bypass -File .\spike\run_table_stitching.ps1
powershell -ExecutionPolicy Bypass -File .\spike\setup_retrieval.ps1
powershell -ExecutionPolicy Bypass -File .\spike\run_retrieval.ps1
powershell -ExecutionPolicy Bypass -File .\spike\setup_reranking.ps1
powershell -ExecutionPolicy Bypass -File .\spike\run_reranking.ps1
powershell -ExecutionPolicy Bypass -File .\spike\setup_gliner.ps1
powershell -ExecutionPolicy Bypass -File .\spike\run_gliner.ps1
```

The scripts save their output even when a later stage fails. Model downloads stay in `.cache/` and
can be removed together with `.venv/` after review. Do not delete the frozen `spike/results/` if the
repository is being submitted as evidence.

## Local Web App

`workspace_local/` holds a small local web app (FastAPI backend + React frontend) that
uploads one PDF and runs it through the full pipeline — parsing, table stitching,
per-field-family retrieval and reranking, context assembly, and one OpenRouter LLM
call — then shows the extracted result with a review-needed badge per field. It lives
entirely in `workspace_local/` so it stays isolated from `spike/`. Each processing run
also saves its intermediate stage output (parsed document, stitching, retrieval
contexts, LLM request/response) as JSON files under
`workspace_local/backend/data/jobs/<job_id>/`, so a run can be inspected after the fact.

The API key is never entered in the UI: copy
`workspace_local/backend/.env.example` to `workspace_local/backend/.env` and set
`OPENROUTER_API_KEY` there. The OpenRouter model itself is set from the app's Settings
button, once it is running.

### Run locally (no Docker)

```powershell
# one shared environment for spike + the backend
python -m venv spike\.venv
spike\.venv\Scripts\pip install -e "spike[docling,paddle,retrieval,reranking]"
spike\.venv\Scripts\pip install -r workspace_local\backend\requirements.txt

copy workspace_local\backend\.env.example workspace_local\backend\.env
# edit workspace_local\backend\.env and set OPENROUTER_API_KEY

cd workspace_local\backend
..\..\spike\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```powershell
cd workspace_local\frontend
npm install
npm run dev
```

Open the Vite dev server URL it prints (proxies `/api` to `:8000`). Run the backend with
exactly one process/worker — job, upload, and settings state live in process memory
(see `workspace_local/backend/app/job_store.py`).

### Run via Docker

```powershell
copy workspace_local\backend\.env.example workspace_local\backend\.env
# edit workspace_local\backend\.env and set OPENROUTER_API_KEY

cd workspace_local
docker compose up --build
```

Open `http://localhost:8000`. The image bundles the full hybrid parser (Docling +
PaddleOCR), so it is large and the **first** run downloads several GB of models before
the first document can be processed — later runs reuse the `model-cache` volume and are
much faster.

## Repository Map

```text
architecture_blueprint.md               hybrid / local-first production design
architecture_blueprint_google_cloud.md  fully Google-managed alternative and economics
contracts/                              strict final JSON Schema and example
docs/decision_log.md                    tested / untested / selected history
spike/src/                              benchmark and normalization code
spike/data/README.md                    input manifest and public sources
spike/results/                          retained decisions and machine-readable runs
spike/*.ps1                             user-run setup and benchmark entry points
workspace_local/                        isolated local web app: FastAPI backend + React frontend + Docker
```

