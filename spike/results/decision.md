# Parser decision

Status: **selected after local benchmark**

Benchmark runs: `20260816T181347Z` (complete comparison) and `20260816T183015Z`
(corrected Hybrid rerun; both `status: success`)

## Compared

- Docling 2.120.1 without OCR on the mixed seven-page fixture.
- Full rasterization at 180 DPI followed by PaddleOCR 3.7.0 / PP-StructureV3.
- Page-level routing between Docling and local PaddleOCR.

## Result

Select a **page-routed parser**:

1. inspect the actual text-layer quality of every page;
2. parse pages with a usable native text layer locally with **Docling**;
3. send only scanned pages or pages with an unusable text layer to
   **Google Cloud Document AI Form Parser**;
4. normalize both responses into the same `CanonicalDocument` schema.

Do not rasterize the complete document and do not keep PaddleOCR in the selected
production path. PaddleOCR remains a documented local/offline alternative.

## Measured evidence

| Run | Routed pages | Parser elapsed | Seconds/page | Peak RSS |
|---|---:|---:|---:|---:|
| Docling-only | 7 Docling | 33.08 s | 4.73 s | 1,632.7 MB |
| Full-raster PaddleOCR | 7 Paddle | 211.80 s | 30.26 s | 1,227.0 MB |
| Local hybrid, corrected | 4 Docling + 3 Paddle | 112.83 s | 16.12 s | 1,966.1 MB |

Full-raster PaddleOCR was approximately **6.4 times slower** than Docling on the
seven-page fixture. In the corrected page-mapping rerun, adding local PaddleOCR fallback
made the hybrid run approximately **3.4 times slower** than Docling-only and raised the
measured hybrid peak RSS to about **1.97 GB**. Most corrected hybrid time was spent in the
Paddle child process (84.09 seconds). The corrected run also passed canonical page-sequence,
provenance consistency, and all seven source-page marker checks.

The benchmark also confirms that Docling-only is insufficient for mixed documents:
the three raster pages contained no usable text/cells without OCR. Therefore the
decision is not pure Docling; it is Docling plus a managed OCR/table fallback.

The original automated cross-parser content comparison is not used as accuracy evidence:
a page-remapping defect was found in the first hybrid artifact while preparing the table
stitching spike. The latency/resource measurements remain valid because all seven pages
were processed; the corrected runner additionally validates source-page markers and
provenance before reporting success.

## Why Document AI Form Parser for fallback pages

Form Parser provides OCR text, layout information, tables, and bounding boxes in one
managed response. That is a closer replacement for PP-StructureV3 than text-only OCR.
Only pages rejected by the native-text router are sent to Google, limiting cost and data
transfer. The Google output must still be normalized into the local canonical schema;
the rest of the pipeline stays cloud-independent.

Enterprise Document OCR is a possible cheaper optimization for a page already known to
contain no relevant table. The baseline design uses Form Parser because the target
documents contain tables and must preserve cell-level evidence.

Official references:

- [Document AI Form Parser](https://docs.cloud.google.com/document-ai/docs/form-parser)
- [Document AI processor list](https://docs.cloud.google.com/document-ai/docs/processors-list)
- [Document AI pricing](https://cloud.google.com/document-ai/pricing)

## Blueprint text

Use Docling for pages with a usable native text layer and Google Cloud Document AI Form
Parser only for scanned or broken-text pages. Local PaddleOCR was retained as a tested
offline alternative but rejected for the primary production path because full-raster
processing was about 6.4 times slower than Docling in the spike and the local hybrid
increased runtime and operational footprint. Both parser outputs are normalized into one
canonical schema with page and bounding-box provenance.
