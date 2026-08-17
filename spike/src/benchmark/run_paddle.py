from __future__ import annotations

import argparse
from pathlib import Path

from benchmark.parsers.paddle_adapter import parse_paddle_full_raster


def parse_pages(value: str | None) -> list[int] | None:
    if not value:
        return None
    pages: list[int] = []
    for part in value.split(","):
        if "-" in part:
            first, last = part.split("-", maxsplit=1)
            pages.extend(range(int(first), int(last) + 1))
        else:
            pages.append(int(part))
    return sorted(set(pages))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Paddle full-raster canonical parser.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--pages", help="Comma-separated pages/ranges, for example 1,3-5")
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args()

    document = parse_paddle_full_raster(
        args.input,
        args.project_root,
        page_numbers=parse_pages(args.pages),
        dpi=args.dpi,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document.model_dump_json(indent=2), encoding="utf-8")
    run = document.parser_run
    print(
        f"pages={len(document.pages)} elapsed={run.elapsed_seconds:.3f}s "
        f"timings={run.timings} peak_memory={run.peak_memory_mb:.1f}MB"
    )


if __name__ == "__main__":
    main()
