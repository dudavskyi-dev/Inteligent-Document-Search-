import type { CandidateStatus } from "../types/extraction";

interface StatusBadgeProps {
  status: CandidateStatus;
  hasConflicts?: boolean;
}

const STYLE: Record<"ok" | "review" | "missing", { background: string; color: string; label: string }> = {
  ok: { background: "#e6f4ea", color: "#1e7a34", label: "OK" },
  review: { background: "#fff4e0", color: "#8a5b00", label: "Needs review" },
  missing: { background: "#f1f1f1", color: "#5f5f5f", label: "Not found" },
};

export default function StatusBadge({ status, hasConflicts = false }: StatusBadgeProps) {
  const kind = status === "not_found" ? "missing" : status === "ambiguous" || hasConflicts ? "review" : "ok";
  const style = STYLE[kind];

  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "999px",
        fontSize: "0.75rem",
        fontWeight: 600,
        background: style.background,
        color: style.color,
        whiteSpace: "nowrap",
      }}
    >
      {style.label}
    </span>
  );
}
