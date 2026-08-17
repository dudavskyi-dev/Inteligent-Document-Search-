from __future__ import annotations

import argparse
from pathlib import Path

from benchmark.parsers.hybrid_adapter import parse_hybrid


def main() -> None:
    parser = argparse.ArgumentParser(description="Run page-routed hybrid canonical parser.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args()

    document = parse_hybrid(args.input, args.project_root, dpi=args.dpi)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document.model_dump_json(indent=2), encoding="utf-8")
    run = document.parser_run
    print(
        f"pages={len(document.pages)} elapsed={run.elapsed_seconds:.3f}s "
        f"routes={run.page_routes} peak_memory={run.peak_memory_mb:.1f}MB"
    )


if __name__ == "__main__":
    main()
