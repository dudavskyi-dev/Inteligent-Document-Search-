from __future__ import annotations

import argparse
from pathlib import Path

from benchmark.parsers.docling_adapter import parse_docling_native


def main() -> None:
    parser = argparse.ArgumentParser(description="Run native Docling and emit canonical JSON.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--pages", type=str, help="Inclusive range, for example 1-3")
    args = parser.parse_args()

    page_range = None
    if args.pages:
        first, last = args.pages.split("-", maxsplit=1)
        page_range = (int(first), int(last))
    document = parse_docling_native(args.input, args.project_root, page_range)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document.model_dump_json(indent=2), encoding="utf-8")
    print(
        f"pages={len(document.pages)} elapsed={document.parser_run.elapsed_seconds:.3f}s "
        f"peak_memory={document.parser_run.peak_memory_mb:.1f}MB"
    )


if __name__ == "__main__":
    main()
