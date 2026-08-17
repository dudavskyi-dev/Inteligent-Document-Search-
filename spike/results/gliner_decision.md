# GLiNER extraction decision

Status: **rejected as the production structured extractor after local spike**

Benchmark run: `20260816T222224Z` (`status: success`, quality gate failed)

## Decision

Do not use zero-shot GLiNER as the component that creates the final ERP extraction JSON.
Use a deterministic-first, schema-constrained hybrid instead:

1. map already structured table headers and rows directly into candidate schema fields;
2. detect numeric/date/currency/unit candidates with deterministic parsers and regexes;
3. send only ambiguous retrieved paragraphs or unresolved column meanings to a
   schema-constrained LLM API;
4. require every proposed value to reference existing block IDs or cell IDs;
5. validate types, units, ranges, arithmetic, and evidence IDs deterministically;
6. route low-confidence or conflicting values to human review.

GLiNER can remain an optional developer experiment or non-authoritative highlighter for
part/model and quantity candidates, but the measured accuracy and memory do not justify
adding it to the default production path.

## Measured evidence

Best evaluated threshold: `0.5`.

| Subset / matching | Precision | Recall | F1 |
|---|---:|---:|---:|
| Real, exact spans | 0.278 | 0.333 | 0.303 |
| Real, relaxed spans | 0.389 | 0.467 | 0.424 |
| All, exact spans | 0.359 | 0.467 | 0.406 |
| All, relaxed spans | 0.487 | 0.633 | 0.551 |
| Synthetic, relaxed spans | 0.692 | 0.900 | 0.783 |

The quality gate failed all three requirements: real relaxed F1 was below `0.70`, overall
exact F1 was below `0.60`, and not every required field reached relaxed recall `0.50`.

At threshold `0.5`, real-document relaxed per-field results were:

| Field | Precision | Recall | F1 |
|---|---:|---:|---:|
| Part/model | 0.400 | 1.000 | 0.571 |
| Quantity | 0.429 | 0.750 | 0.545 |
| Price/fee | 0.333 | 0.250 | 0.286 |
| Tolerance/acceptance | 1.000 | 0.250 | 0.400 |
| Deadline/period | 0.000 | 0.000 | 0.000 |

## Error analysis

Representative label errors:

- `one year` was classified as quantity instead of performance period;
- `zero failures` was classified as quantity instead of acceptance criterion;
- `25.00 ± 0.02 mm` was classified as quantity instead of tolerance;
- numeric fee caps `1.0 %` and `0.5%` were missed while the words `fixed fee` and
  `award fee` were returned as price spans;
- the price range `$2,500- $15,0000` was returned as one span rather than two values;
- `System 22 criteria` was found, but the full applicable standard was truncated.

These are not merely formatting differences. They affect field type, normalization, and
the relationship between values, which makes autonomous schema assembly unsafe.

## Runtime and resource observations

- peak process memory: `1852.137 MB`;
- first-run model loading: `49.474 s` (may include initial cache/download work);
- total inference for 14 cases: `9.674 s`;
- mean latency: `0.691 s/case`, including a `6.712 s` first-inference outlier;
- median latency: `0.207 s/case`;
- mean excluding the maximum outlier: `0.228 s/case`.

The steady per-fragment latency is acceptable, but memory is high for a component whose
real-document quality is insufficient.

## Limitations

- The frozen set has only 14 cases and 30 expected spans.
- The selected model is a general zero-shot GLiNER model, not a model fine-tuned on the
  organization's documents.
- Better label wording, fine-tuning, or a larger model could improve results, but would add
  more evaluation and operational cost. The current spike does not justify that path.
- GLiNER evaluates entity spans, not relations such as which quantity or price belongs to
  which part. Final industrial extraction requires those relations.
- A schema-constrained LLM alternative still requires its own field/evidence evaluation
  before production; it was not tested locally because no LLM API was available.

## Blueprint text

Do not use zero-shot GLiNER as the final structured extractor. On ten real excerpts it
reached only 0.424 relaxed-span F1 at the best threshold and consumed 1.85 GB peak memory.
Map parsed table rows deterministically, detect numeric candidates with rules, and use a
schema-constrained LLM API only for ambiguous text or column meaning. Require existing
block/cell evidence IDs for every value, validate deterministically, and send uncertain
or conflicting results to review.
