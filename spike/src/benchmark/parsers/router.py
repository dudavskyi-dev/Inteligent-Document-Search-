from __future__ import annotations

from pathlib import Path

import pymupdf
from pydantic import BaseModel, Field


class PageAssessment(BaseModel):
    page_number: int = Field(ge=1)
    characters: int = Field(ge=0)
    words: int = Field(ge=0)
    printable_ratio: float = Field(ge=0, le=1)
    route: str
    reason: str


def assess_text_layer(
    source: Path,
    minimum_characters: int = 50,
    minimum_words: int = 10,
    minimum_printable_ratio: float = 0.9,
) -> list[PageAssessment]:
    document = pymupdf.open(source)
    assessments: list[PageAssessment] = []
    for index, page in enumerate(document, start=1):
        text = page.get_text("text") or ""
        characters = len("".join(text.split()))
        words = len(text.split())
        non_space = [character for character in text if not character.isspace()]
        printable_ratio = (
            sum(character.isprintable() for character in non_space) / len(non_space)
            if non_space
            else 0.0
        )
        usable = (
            characters >= minimum_characters
            and words >= minimum_words
            and printable_ratio >= minimum_printable_ratio
        )
        if usable:
            route = "docling_native"
            reason = "usable_text_layer"
        elif not characters:
            route = "paddle_ppstructurev3"
            reason = "no_text_layer"
        else:
            route = "paddle_ppstructurev3"
            reason = "low_quality_text_layer"
        assessments.append(
            PageAssessment(
                page_number=index,
                characters=characters,
                words=words,
                printable_ratio=printable_ratio,
                route=route,
                reason=reason,
            )
        )
    document.close()
    return assessments
