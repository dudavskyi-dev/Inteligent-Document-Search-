from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from benchmark.context_assembly import build_llm_context
from benchmark.reranking import RerankingBenchmark
from benchmark.table_stitching import stitch_document

from app.config import CACHE_DIR, PROJECT_ROOT, reranker_model_name
from app.pipeline import job_artifacts
from app.pipeline.contract_models import ExtractionCandidateResponse
from app.pipeline.evidence import collect_evidence_ids
from app.pipeline.field_families import FIELD_FAMILIES
from app.pipeline.openrouter_client import OpenRouterClient
from app.pipeline.prompt_builder import (
    build_repair_prompt,
    build_system_prompt,
    build_user_prompt,
)
from app.pipeline.schema_validation import load_schema, validate_candidate


class ExtractionValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("LLM response failed schema validation: " + "; ".join(errors))
        self.errors = errors


def run_extraction_pipeline(job_id: str, pdf_path: Path, model: str) -> dict[str, Any]:
    # Heavy import (pulls in the docling/paddle parsing stack); load lazily so the
    # FastAPI app itself starts quickly.
    from benchmark.parsers.hybrid_adapter import parse_hybrid

    document = parse_hybrid(pdf_path, PROJECT_ROOT)
    job_artifacts.save_stage(job_id, "01_canonical_document", document.model_dump(mode="json"))

    stitch_result = stitch_document(document)
    job_artifacts.save_stage(job_id, "02_stitch_result", stitch_result.model_dump(mode="json"))

    reranker = RerankingBenchmark(
        [document], cache_folder=str(CACHE_DIR / "sentence-transformers"), model_name=reranker_model_name()
    )
    candidate_ids = [page.page_id for page in reranker.pages]

    contexts: dict[str, str] = {}
    evidence_ids: set[str] = set()
    family_records: list[dict[str, Any]] = []
    for family in FIELD_FAMILIES:
        result = reranker.rerank(family.query, candidate_ids)
        top = result["structural_cross_encoder"]["ranking"][0]
        evidence = top["evidence"]
        record: dict[str, Any] = {
            "key": family.key,
            "label": family.label,
            "query": family.query,
            "top_page_number": top["page_number"],
            "evidence": evidence,
        }
        if evidence is not None:
            unit_id = evidence["unit_id"]
            context = build_llm_context(document, stitch_result, unit_id)
            unit_evidence_ids = collect_evidence_ids(document, stitch_result, unit_id)
            contexts[family.label] = context
            evidence_ids.update(unit_evidence_ids)
            record["context"] = context
            record["evidence_ids"] = unit_evidence_ids
        family_records.append(record)
    job_artifacts.save_stage(job_id, "03_field_family_contexts", family_records)

    schema = load_schema()
    messages = [
        {"role": "system", "content": build_system_prompt(schema)},
        {"role": "user", "content": build_user_prompt(contexts, sorted(evidence_ids))},
    ]
    job_artifacts.save_stage(job_id, "04_llm_request", {"model": model, "messages": messages})

    client = OpenRouterClient(api_key=os.environ["OPENROUTER_API_KEY"])
    attempts: list[str] = []
    validations: list[list[str]] = []

    content = client.chat_json(model=model, messages=messages)
    attempts.append(content)
    data = json.loads(content)
    errors = validate_candidate(data)
    validations.append(errors)

    if errors:
        repair_messages = [
            *messages,
            {"role": "assistant", "content": content},
            {"role": "user", "content": build_repair_prompt(errors)},
        ]
        content = client.chat_json(model=model, messages=repair_messages)
        attempts.append(content)
        data = json.loads(content)
        errors = validate_candidate(data)
        validations.append(errors)

    job_artifacts.save_stage(job_id, "05_llm_response_raw", {"attempts": attempts})
    job_artifacts.save_stage(job_id, "06_validation", {"attempts": validations})

    if errors:
        raise ExtractionValidationError(errors)

    result = ExtractionCandidateResponse.model_validate(data)
    result_dict = result.model_dump(mode="json")
    job_artifacts.save_stage(job_id, "07_result", result_dict)
    return result_dict
