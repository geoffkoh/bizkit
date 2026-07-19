import type { ChangesetState } from "../types";

export function StateBadge({ state }: { state: ChangesetState }) {
  return <span className={`state state-${state}`}>{state}</span>;
}

export function Deadline({
  label,
  value,
}: {
  label: string;
  value: string | null;
}) {
  if (!value) return null;
  const due = new Date(value);
  const overdue = due.getTime() < Date.now();
  return (
    <span className={`deadline ${overdue ? "overdue" : ""}`}>
      {label} {due.toLocaleString()}
      {overdue ? " (overdue)" : ""}
    </span>
  );
}
