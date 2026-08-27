from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# Pydantic mirror of contracts/extraction_candidate_v1.schema.json, used for typed
# access to an already schema-validated LLM response. jsonschema_validation.py is the
# source of truth for validating the raw LLM output; these models are not re-validated
# against the schema themselves, only used to give the API response a typed shape.

Status = Literal["supported", "ambiguous", "not_found"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidateString(Model):
    status: Status
    raw: str | None
    value: str | None
    evidence_ids: list[str]
    conflict_evidence_ids: list[str]


class CandidateQuantity(Model):
    status: Status
    raw: str | None
    value: str | None
    unit: str | None
    evidence_ids: list[str]
    conflict_evidence_ids: list[str]


class CandidateMoney(Model):
    status: Status
    raw: str | None
    amount: str | None
    currency: str | None
    price_basis: str | None
    evidence_ids: list[str]
    conflict_evidence_ids: list[str]


class CandidateTolerance(Model):
    status: Status
    type: Literal["dimensional", "acceptance", "other"]
    target: str | None
    raw: str | None
    nominal: str | None
    lower_limit: str | None
    upper_limit: str | None
    unit: str | None
    standard: str | None
    evidence_ids: list[str]
    conflict_evidence_ids: list[str]


class CandidateDeadline(Model):
    status: Status
    type: Literal["bid_submission", "delivery", "performance_start", "performance_end", "other"]
    raw: str | None
    value: str | None
    timezone_source: Literal["explicit", "document_locale"] | None
    evidence_ids: list[str]
    conflict_evidence_ids: list[str]


class CandidateParty(Model):
    role: Literal["buyer", "supplier", "contractor", "other"]
    name: CandidateString | None


class CandidateLineItem(Model):
    source_row_ids: list[str]
    part_number: CandidateString | None
    description: CandidateString | None
    quantity: CandidateQuantity | None
    tolerances: list[CandidateTolerance]
    unit_price: CandidateMoney | None
    line_total: CandidateMoney | None
    delivery_deadline: CandidateDeadline | None


class ExtractionCandidateResponse(Model):
    schema_version: Literal["industrial-document-candidate/1.0"]
    document_number: CandidateString | None
    parties: list[CandidateParty]
    deadlines: list[CandidateDeadline]
    line_items: list[CandidateLineItem]
    abstained_field_paths: list[str]
