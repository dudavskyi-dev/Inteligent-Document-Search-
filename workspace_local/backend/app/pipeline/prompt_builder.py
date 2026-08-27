from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = """You are a document-extraction engine for industrial/technical/tender documents.
You will be given several excerpts of ONE document, each labelled with the field family
it was retrieved for, plus a list of allowed evidence ids.

Return ONLY a single JSON object matching EXACTLY this JSON Schema (no prose, no
markdown fences):

{schema}

Rules:
- Only use evidence ids from ALLOWED_EVIDENCE_IDS below; never invent an id.
- If a field is not supported by the given excerpts, set its status to "not_found" and
  add its JSON pointer path to abstained_field_paths instead of guessing a value.
- If two excerpts disagree on a value, set status to "ambiguous" and list every
  conflicting evidence id in conflict_evidence_ids.
- Do not return any field, table, or explanation outside the schema above."""


def build_user_prompt(contexts: dict[str, str], evidence_ids: list[str]) -> str:
    sections = "\n\n".join(
        f"--- {label} ---\n{context}" for label, context in contexts.items()
    )
    return (
        f"ALLOWED_EVIDENCE_IDS: {json.dumps(evidence_ids)}\n\n"
        f"DOCUMENT EXCERPTS:\n\n{sections}"
    )


def build_system_prompt(schema: dict[str, Any]) -> str:
    return SYSTEM_PROMPT.format(schema=json.dumps(schema))


def build_repair_prompt(errors: list[str]) -> str:
    joined = "\n".join(f"- {error}" for error in errors)
    return (
        "Your previous response did not validate against the schema. Fix it and "
        "return ONLY the corrected JSON object (no prose, no markdown fences). "
        f"Validation errors:\n{joined}"
    )
