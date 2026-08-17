from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_area_ratio(page: Any) -> float:
    page_area = float(page.width * page.height)
    if not page_area:
        return 0.0
    area = 0.0
    for image in page.images:
        width = max(0.0, float(image["x1"]) - float(image["x0"]))
        height = max(0.0, float(image["bottom"]) - float(image["top"]))
        area += width * height
    return min(1.0, area / page_area)


def _table_summary(page: Any) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for table in page.find_tables():
        data = table.extract()
        column_count = max((len(row) for row in data), default=0)
        preview = [
            [str(value or "").strip()[:80] for value in row]
            for row in data[:3]
        ]
        summaries.append(
            {
                "rows": len(data),
                "columns": column_count,
                "bbox": [round(float(value), 2) for value in table.bbox],
                "preview": preview,
            }
        )
    return summaries


def inspect_pdf(path: Path, detect_tables: bool) -> dict[str, Any]:
    reader = PdfReader(path)
    pages: list[dict[str, Any]] = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(layout=False) or ""
            compact_text = " ".join(text.split())
            words = page.extract_words() or []
            tables = _table_summary(page) if detect_tables else []
            pages.append(
                {
                    "page": number,
                    "characters": len(text),
                    "words": len(words),
                    "images": len(page.images),
                    "image_area_ratio": round(_image_area_ratio(page), 4),
                    "lines": len(page.lines),
                    "rectangles": len(page.rects),
                    "tables": tables,
                    "text_preview": compact_text[:240],
                }
            )

    page_count = len(pages)
    low_text_pages = [p["page"] for p in pages if p["characters"] < 50]
    image_dominant_pages = [p["page"] for p in pages if p["image_area_ratio"] >= 0.8]
    table_pages = [p["page"] for p in pages if p["tables"]]
    return {
        "file": path.name,
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "pages": page_count,
        "tagged": "/MarkInfo" in reader.trailer["/Root"],
        "form_fields": len(reader.get_fields() or {}),
        "summary": {
            "total_characters": sum(p["characters"] for p in pages),
            "median_characters_per_page": sorted(p["characters"] for p in pages)[
                page_count // 2
            ],
            "low_text_pages": low_text_pages,
            "image_dominant_pages": image_dominant_pages,
            "table_pages": table_pages,
        },
        "page_details": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory PDFs before parser benchmarking.")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--detect-tables", action="store_true")
    args = parser.parse_args()

    inventory = [inspect_pdf(path, args.detect_tables) for path in args.inputs]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
