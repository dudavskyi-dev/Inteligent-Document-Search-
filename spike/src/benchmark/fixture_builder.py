from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas


def render_page(pdftoppm: Path, source: Path, page_number: int, output: Path, dpi: int) -> None:
    prefix = output.with_suffix("")
    subprocess.run(
        [
            str(pdftoppm),
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-singlefile",
            "-r",
            str(dpi),
            "-png",
            str(source),
            str(prefix),
        ],
        check=True,
    )


def image_pdf(image_path: Path, output: Path, width: float, height: float) -> None:
    canvas = Canvas(str(output), pagesize=(width, height), pageCompression=1)
    canvas.drawImage(ImageReader(str(image_path)), 0, 0, width=width, height=height)
    canvas.showPage()
    canvas.save()


def build_fixtures(
    source: Path,
    scan_output: Path,
    mixed_output: Path,
    pdftoppm: Path,
    pages: list[int],
    rasterized_in_mixed: set[int],
    dpi: int,
) -> None:
    source_reader = PdfReader(source)
    scan_writer = PdfWriter()
    mixed_writer = PdfWriter()

    scan_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pdf-fixtures-") as temp_name:
        temp_dir = Path(temp_name)
        raster_pages: dict[int, Path] = {}
        for page_number in pages:
            source_page = source_reader.pages[page_number - 1]
            width = float(source_page.mediabox.width)
            height = float(source_page.mediabox.height)
            image_path = temp_dir / f"page-{page_number}.png"
            raster_pdf = temp_dir / f"page-{page_number}.pdf"
            render_page(pdftoppm, source, page_number, image_path, dpi)
            image_pdf(image_path, raster_pdf, width, height)
            raster_pages[page_number] = raster_pdf
            scan_writer.add_page(PdfReader(raster_pdf).pages[0])

            if page_number in rasterized_in_mixed:
                mixed_writer.add_page(PdfReader(raster_pdf).pages[0])
            else:
                mixed_writer.add_page(source_page)

        with scan_output.open("wb") as stream:
            scan_writer.write(stream)
        with mixed_output.open("wb") as stream:
            mixed_writer.write(stream)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local scan and mixed-PDF test fixtures.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--scan-output", type=Path, required=True)
    parser.add_argument("--mixed-output", type=Path, required=True)
    parser.add_argument("--pdftoppm", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args()

    build_fixtures(
        source=args.source,
        scan_output=args.scan_output,
        mixed_output=args.mixed_output,
        pdftoppm=args.pdftoppm,
        pages=[13, 14, 15, 24, 25, 26, 27],
        rasterized_in_mixed={14, 25, 27},
        dpi=args.dpi,
    )


if __name__ == "__main__":
    main()
