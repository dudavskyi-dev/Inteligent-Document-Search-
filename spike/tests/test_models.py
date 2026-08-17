from benchmark.models import (
    Block,
    BoundingBox,
    CanonicalDocument,
    Page,
    ParserRun,
    Provenance,
)


def test_minimal_canonical_document_is_valid() -> None:
    provenance = Provenance(
        page_number=1,
        bbox=BoundingBox(x1=0.1, y1=0.1, x2=0.9, y2=0.2),
        parser="fixture",
        confidence=0.99,
    )
    document = CanonicalDocument(
        document_id="fixture",
        source_filename="fixture.pdf",
        sha256="0" * 64,
        parser_run=ParserRun(
            strategy="hybrid",
            parser_versions={"fixture": "1.0"},
            elapsed_seconds=0.1,
        ),
        pages=[
            Page(
                page_number=1,
                width=1000,
                height=1400,
                blocks=[
                    Block(
                        block_id="p1-b1",
                        type="paragraph",
                        text="Example",
                        reading_order=0,
                        provenance=[provenance],
                    )
                ],
                tables=[],
            )
        ],
    )

    assert document.pages[0].blocks[0].provenance[0].page_number == 1
