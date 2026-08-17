from benchmark.parsers.docling_adapter import _bbox


def test_bottom_left_bbox_is_normalized_to_top_left() -> None:
    bbox = _bbox(
        {"l": 10, "t": 90, "r": 30, "b": 70, "coord_origin": "BOTTOMLEFT"},
        width=100,
        height=100,
    )
    assert bbox.model_dump() == {"x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.3}


def test_top_left_bbox_is_normalized() -> None:
    bbox = _bbox(
        {"l": 10, "t": 20, "r": 30, "b": 40, "coord_origin": "TOPLEFT"},
        width=100,
        height=100,
    )
    assert bbox.model_dump() == {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4}
