import type { CandidateLineItem, CandidateMoney, CandidateQuantity, CandidateString } from "../types/extraction";
import StatusBadge from "./StatusBadge";

function cell(value: CandidateString | CandidateQuantity | CandidateMoney | null, text: string | null) {
  if (value === null) {
    return (
      <td>
        <span style={{ color: "#999" }}>-</span> <StatusBadge status="not_found" />
      </td>
    );
  }
  return (
    <td>
      {text ?? <span style={{ color: "#999" }}>-</span>}{" "}
      <StatusBadge status={value.status} hasConflicts={value.conflict_evidence_ids.length > 0} />
    </td>
  );
}

function tolerancesSummary(item: CandidateLineItem): string | null {
  if (item.tolerances.length === 0) return null;
  return item.tolerances
    .map((tolerance) => tolerance.raw ?? `${tolerance.nominal ?? "?"} ${tolerance.unit ?? ""}`.trim())
    .join("; ");
}

interface LineItemsTableProps {
  lineItems: CandidateLineItem[];
}

export default function LineItemsTable({ lineItems }: LineItemsTableProps) {
  if (lineItems.length === 0) {
    return <p style={{ color: "#666" }}>No line items were extracted.</p>;
  }

  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "2px solid #ddd" }}>
          <th>Part number</th>
          <th>Description</th>
          <th>Quantity</th>
          <th>Tolerances</th>
          <th>Unit price</th>
          <th>Line total</th>
          <th>Delivery deadline</th>
        </tr>
      </thead>
      <tbody>
        {lineItems.map((item, index) => (
          <tr key={index} style={{ borderBottom: "1px solid #eee" }}>
            {cell(item.part_number, item.part_number?.value ?? null)}
            {cell(item.description, item.description?.value ?? null)}
            {cell(item.quantity, item.quantity ? `${item.quantity.value ?? "?"} ${item.quantity.unit ?? ""}` : null)}
            <td>
              {tolerancesSummary(item) ?? <span style={{ color: "#999" }}>-</span>}
            </td>
            {cell(
              item.unit_price,
              item.unit_price ? `${item.unit_price.amount ?? "?"} ${item.unit_price.currency ?? ""}` : null
            )}
            {cell(
              item.line_total,
              item.line_total ? `${item.line_total.amount ?? "?"} ${item.line_total.currency ?? ""}` : null
            )}
            {cell(item.delivery_deadline, item.delivery_deadline?.value ?? null)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
