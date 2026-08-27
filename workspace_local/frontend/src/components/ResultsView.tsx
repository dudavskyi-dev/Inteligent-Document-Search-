import type { ExtractionCandidateResponse } from "../types/extraction";
import LineItemsTable from "./LineItemsTable";
import StatusBadge from "./StatusBadge";

interface ResultsViewProps {
  result: ExtractionCandidateResponse;
}

export default function ResultsView({ result }: ResultsViewProps) {
  return (
    <div style={{ marginTop: "1.5rem" }}>
      <h2>Extraction result</h2>

      <section style={{ marginBottom: "1rem" }}>
        <h3>Document number</h3>
        {result.document_number ? (
          <p>
            {result.document_number.value ?? <span style={{ color: "#999" }}>-</span>}{" "}
            <StatusBadge
              status={result.document_number.status}
              hasConflicts={result.document_number.conflict_evidence_ids.length > 0}
            />
          </p>
        ) : (
          <p>
            <span style={{ color: "#999" }}>-</span> <StatusBadge status="not_found" />
          </p>
        )}
      </section>

      <section style={{ marginBottom: "1rem" }}>
        <h3>Parties</h3>
        {result.parties.length === 0 ? (
          <p style={{ color: "#666" }}>No parties were extracted.</p>
        ) : (
          <ul>
            {result.parties.map((party, index) => (
              <li key={index}>
                <strong>{party.role}:</strong>{" "}
                {party.name?.value ?? <span style={{ color: "#999" }}>-</span>}{" "}
                <StatusBadge
                  status={party.name?.status ?? "not_found"}
                  hasConflicts={(party.name?.conflict_evidence_ids.length ?? 0) > 0}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginBottom: "1rem" }}>
        <h3>Deadlines</h3>
        {result.deadlines.length === 0 ? (
          <p style={{ color: "#666" }}>No deadlines were extracted.</p>
        ) : (
          <ul>
            {result.deadlines.map((deadline, index) => (
              <li key={index}>
                <strong>{deadline.type}:</strong>{" "}
                {deadline.value ?? deadline.raw ?? <span style={{ color: "#999" }}>-</span>}{" "}
                <StatusBadge
                  status={deadline.status}
                  hasConflicts={deadline.conflict_evidence_ids.length > 0}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginBottom: "1rem" }}>
        <h3>Line items</h3>
        <LineItemsTable lineItems={result.line_items} />
      </section>

      {result.abstained_field_paths.length > 0 && (
        <section>
          <h3>Fields the model could not fill in</h3>
          <ul>
            {result.abstained_field_paths.map((path) => (
              <li key={path} style={{ fontFamily: "monospace" }}>
                {path}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
