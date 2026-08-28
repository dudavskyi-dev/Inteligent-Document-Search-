from app.pipeline.run_pipeline import EXCERPT_SEPARATOR, select_family_seeds


def _hit(page_number: int, unit_id: str | None) -> dict:
    evidence = None if unit_id is None else {"unit_id": unit_id}
    return {"page_number": page_number, "evidence": evidence}


def _contexts(mapping: dict[str, str]):
    return lambda unit_id: mapping[unit_id]


def _ids(mapping: dict[str, list[str]]):
    return lambda unit_id: mapping[unit_id]


def test_keeps_three_seeds_instead_of_only_the_top_hit() -> None:
    ranking = [_hit(1, "doc:b1"), _hit(4, "doc:b2"), _hit(9, "doc:b3"), _hit(12, "doc:b4")]
    build = _contexts({"doc:b1": "first", "doc:b2": "second", "doc:b3": "third", "doc:b4": "fourth"})
    collect = _ids({"doc:b1": ["b1"], "doc:b2": ["b2"], "doc:b3": ["b3"], "doc:b4": ["b4"]})

    seeds = select_family_seeds(ranking, build, collect)

    assert seeds.context == EXCERPT_SEPARATOR.join(["first", "second", "third"])
    assert seeds.evidence_ids == ["b1", "b2", "b3"]
    assert [hit["rank"] for hit in seeds.hits] == [1, 2, 3]
    assert [hit["page_number"] for hit in seeds.hits] == [1, 4, 9]


def test_rows_of_one_stitched_table_collapse_to_a_single_excerpt() -> None:
    # Two rows of the same logical table render to identical context text; keeping both
    # would send the table twice and waste one of the three seed slots.
    ranking = [_hit(4, "doc:t2-r0"), _hit(5, "doc:t2-r7"), _hit(11, "doc:b9")]
    build = _contexts({"doc:t2-r0": "table", "doc:t2-r7": "table", "doc:b9": "prose"})
    collect = _ids({"doc:t2-r0": ["t2-c1", "t2-c2"], "doc:t2-r7": ["t2-c1", "t2-c2"], "doc:b9": ["b9"]})

    seeds = select_family_seeds(ranking, build, collect)

    assert seeds.context == EXCERPT_SEPARATOR.join(["table", "prose"])
    assert seeds.evidence_ids == ["t2-c1", "t2-c2", "b9"]
    assert seeds.hits[1]["duplicate_of_earlier_seed"] is True
    assert "context" not in seeds.hits[1]


def test_hits_without_evidence_are_recorded_but_contribute_nothing() -> None:
    ranking = [_hit(1, None), _hit(3, "doc:b5")]
    build = _contexts({"doc:b5": "only real excerpt"})
    collect = _ids({"doc:b5": ["b5"]})

    seeds = select_family_seeds(ranking, build, collect)

    assert seeds.context == "only real excerpt"
    assert seeds.evidence_ids == ["b5"]
    assert seeds.hits[0]["evidence"] is None
    assert "context" not in seeds.hits[0]


def test_a_family_with_no_usable_hits_yields_an_empty_context() -> None:
    seeds = select_family_seeds([_hit(1, None)], _contexts({}), _ids({}))

    assert seeds.context == ""
    assert seeds.evidence_ids == []
