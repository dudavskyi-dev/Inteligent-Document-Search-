import json

from app.pipeline.prompt_builder import (
    build_repair_prompt,
    build_system_prompt,
    build_user_prompt,
)


def test_system_prompt_embeds_the_schema() -> None:
    schema = {"title": "ExtractionCandidateResponse", "type": "object"}

    prompt = build_system_prompt(schema)

    assert json.dumps(schema) in prompt
    assert "ONLY a single JSON object" in prompt


def test_user_prompt_includes_every_context_and_allowed_ids() -> None:
    contexts = {
        "Document identity / parties": "Document: doc.pdf\nPage: 1\nparagraph: Buyer is Acme.",
        "Prices / fees": "[Stitched table across pages [4, 5]]\nItem | Price\nA | 10",
    }

    prompt = build_user_prompt(contexts, ["p1-b1", "p4-t2-r0"])

    assert "--- Document identity / parties ---" in prompt
    assert "Buyer is Acme." in prompt
    assert "--- Prices / fees ---" in prompt
    assert "Item | Price" in prompt
    assert '["p1-b1", "p4-t2-r0"]' in prompt


def test_repair_prompt_lists_every_validation_error() -> None:
    prompt = build_repair_prompt(["document_number: 'status' is a required property", "parties: too short"])

    assert "document_number: 'status' is a required property" in prompt
    assert "parties: too short" in prompt
