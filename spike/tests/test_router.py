from pathlib import Path

from benchmark.parsers.router import assess_text_layer


def test_mixed_fixture_routes_native_and_raster_pages() -> None:
    source = Path("spike/data/inputs/05_GSA_Mixed_Table_Fixture.pdf")
    if not source.exists():
        return
    assessments = assess_text_layer(source)
    assert [item.page_number for item in assessments if item.route == "paddle_ppstructurev3"] == [
        2,
        5,
        7,
    ]
