import type { JSX } from "react";
import type { ChangesetState } from "../types";

/** State badge (UI_SPECIFICATION.md §2.5: on every changeset surface). */
export function StateBadge({ state }: { state: ChangesetState }): JSX.Element {
  return (
    <span className={`state state-${state}`} aria-label={`state: ${state}`}>
      {state}
    </span>
  );
}

/** Deadline with the §2.5 overdue treatment (state-warning + "(overdue)"). */
export function Deadline({
  label,
  value,
}: {
  label: string;
  value: string | null;
}): JSX.Element | null {
  if (!value) return null;
  const due = new Date(value);
  const overdue = due.getTime() < Date.now();
  return (
    <span
      className={`deadline ${overdue ? "overdue" : ""}`}
      aria-label={`${label} ${due.toLocaleString()}${overdue ? " (overdue)" : ""}`}
    >
      {label} {due.toLocaleString()}
      {overdue ? " (overdue)" : ""}
    </span>
  );
}
