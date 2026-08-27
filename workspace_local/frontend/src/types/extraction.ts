// TypeScript mirror of contracts/extraction_candidate_v1.schema.json
// (ExtractionCandidateResponse). Keep in sync with that file and with
// workspace_local/backend/app/pipeline/contract_models.py.

export type CandidateStatus = "supported" | "ambiguous" | "not_found";

interface CandidateBase {
  status: CandidateStatus;
  evidence_ids: string[];
  conflict_evidence_ids: string[];
}

export interface CandidateString extends CandidateBase {
  raw: string | null;
  value: string | null;
}

export interface CandidateQuantity extends CandidateBase {
  raw: string | null;
  value: string | null;
  unit: string | null;
}

export interface CandidateMoney extends CandidateBase {
  raw: string | null;
  amount: string | null;
  currency: string | null;
  price_basis: string | null;
}

export interface CandidateTolerance extends CandidateBase {
  type: "dimensional" | "acceptance" | "other";
  target: string | null;
  raw: string | null;
  nominal: string | null;
  lower_limit: string | null;
  upper_limit: string | null;
  unit: string | null;
  standard: string | null;
}

export interface CandidateDeadline extends CandidateBase {
  type: "bid_submission" | "delivery" | "performance_start" | "performance_end" | "other";
  raw: string | null;
  value: string | null;
  timezone_source: "explicit" | "document_locale" | null;
}

export interface CandidateParty {
  role: "buyer" | "supplier" | "contractor" | "other";
  name: CandidateString | null;
}

export interface CandidateLineItem {
  source_row_ids: string[];
  part_number: CandidateString | null;
  description: CandidateString | null;
  quantity: CandidateQuantity | null;
  tolerances: CandidateTolerance[];
  unit_price: CandidateMoney | null;
  line_total: CandidateMoney | null;
  delivery_deadline: CandidateDeadline | null;
}

export interface ExtractionCandidateResponse {
  schema_version: "industrial-document-candidate/1.0";
  document_number: CandidateString | null;
  parties: CandidateParty[];
  deadlines: CandidateDeadline[];
  line_items: CandidateLineItem[];
  abstained_field_paths: string[];
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  filename: string;
  created_at: string;
  result: ExtractionCandidateResponse | null;
  error: string | null;
}
