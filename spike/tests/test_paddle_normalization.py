from benchmark.parsers.paddle_adapter import _html_cells


def test_html_cells_preserve_spans_and_coordinates() -> None:
    cells = _html_cells(
        "<table><tr><th>A</th><th>B</th></tr>"
        "<tr><td rowspan='2'>x</td><td>y</td></tr><tr><td>z</td></tr></table>"
    )
    assert [(cell["row"], cell["column"]) for cell in cells] == [
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
        (2, 1),
    ]
    assert cells[2]["row_span"] == 2
