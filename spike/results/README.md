# Saved Spike Results

These artifacts were produced by user-run scripts. They are retained so a reviewer can inspect the
evidence without re-running large OCR/model downloads. The three source PDFs are not committed;
their sources and hashes are documented in [`../data/README.md`](../data/README.md).

| Spike | Frozen run | Human-readable decision | Machine-readable evidence |
|---|---|---|---|
| Parsing | `20260816T181347Z`, corrected hybrid `20260816T183015Z` | [`decision.md`](decision.md) | `parsing/<run>/summary.json` and `outputs/*.json` |
| Table stitching | `20260816T183935Z` | [`stitching_decision.md`](stitching_decision.md) | `stitching/<run>/summary.json`, `decisions.json`, `logical_tables.json` |
| Retrieval | `20260816T214507Z` | [`retrieval_decision.md`](retrieval_decision.md) | `retrieval/runs/<run>/summary.json`, `rankings.json`, `corpus_manifest.json` |
| Reranking | `20260816T220643Z` | [`reranking_decision.md`](reranking_decision.md) | `reranking/runs/<run>/summary.json`, `rankings.json` |
| GLiNER | `20260816T222224Z` | [`gliner_decision.md`](gliner_decision.md) | `gliner/runs/<run>/summary.json`, `predictions.json` |

Important interpretation rules:

- A successful script means the experiment completed; it does not by itself mean the method won.
- Parsing cross-parser agreement is diagnostic, not human-labelled extraction accuracy.
- The stitching fixture has only six labelled boundaries from one document family.
- Retrieval and reranking use 14 labelled queries across three English public documents.
- GLiNER real, derived, and synthetic subsets are reported separately; the real-document failure is
  the reason it was rejected.
- No local or cloud LLM structured-extraction benchmark has been run.

Logs are deliberately not versioned because they may contain machine-specific paths and noisy
installation/runtime output. Each result records the relevant package/model versions and input
hashes needed for interpretation.

