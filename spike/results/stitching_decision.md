# Table-stitching decision

Status: **selected after local spike**

Benchmark run: `20260816T183935Z` (`status: success`)

## Decision

Use deterministic, precision-first stitching between the last table fragment on page N
and the first table fragment on page N+1. Auto-merge only when both fragments satisfy
the page-boundary gates and the weighted score reaches `0.72`.

The score uses:

- proximity of the left table to the bottom of its page;
- proximity of the right table to the top of the next page;
- horizontal overlap;
- column-count similarity and shifted column alignment;
- repeated-header similarity as a positive signal only;
- guards for meaningful content after the left fragment or before the right fragment.

The result is a logical group of source fragments. Source cells, repeated headers, table
IDs, page numbers, and bounding boxes are preserved. The stitcher does not invent an OCR
cell, remove a header, or rewrite parser output.

## Measured evidence

| Metric | Result |
|---|---:|
| Labelled adjacent-page pairs | 6 |
| True positives / true negatives | 3 / 3 |
| False positives / false negatives | 0 / 0 |
| Precision | 1.0 |
| Recall | 1.0 |
| F1 / accuracy | 1.0 / 1.0 |
| Stitching runtime | 0.008855 s |
| Source fragments preserved | 7 / 7 |
| Source cells preserved | 189 / 189 |

Detected logical multi-page tables:

- equipment inventory: fixture pages 1-2 (source pages 13-14), score `0.916731`;
- price/cost schedule: fixture pages 4-5 (source pages 24-25), score `0.848253`;
- delivery schedule: fixture pages 6-7 (source pages 26-27), score `0.908167`.

## Limitations

This is a focused spike with six labelled boundaries from one document family. Perfect
fixture metrics are not a production-wide accuracy claim. Add more positive and hard
negative examples before calibrating the production threshold.

Stitching cannot recover a fragment that the parser failed to emit. On source page 25,
the parser did not create a separate fragment for the delivery table beginning near the
bottom of the page, so the stitcher correctly did not join the extracted price fragment
to the delivery fragment on page 26. Parser coverage and stitching accuracy must be
measured separately.

## Blueprint text

Group adjacent table fragments with deterministic page-boundary, geometry, column, and
header signals. Auto-merge only high-confidence pairs, preserve all source fragments and
cell provenance, and leave ambiguous pairs separate for review. The local spike achieved
precision/recall/F1 of 1.0 on six labelled boundaries in 0.008855 seconds, while preserving
all 7 fragments and 189 source cells. The result is promising but must be validated on
additional document families.
