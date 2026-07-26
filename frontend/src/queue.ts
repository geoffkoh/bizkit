// One definition of "awaiting my review", shared by the sidebar's Queue count
// (UI_SPECIFICATION.md §3) and the queue's "to review (as me)" filter (§4.2).
//
// They must agree: a badge saying 3 next to a filter that lists 5 is a bug, and
// the spec defines the count as "submitted ∧ maker ≠ me ∧ approve right".

import type { ChangesetOut, TableOut } from "./types";

export function approveRightsByPath(
  tables: readonly TableOut[] | undefined,
): Map<string, boolean> {
  return new Map((tables ?? []).map((t) => [t.path, t.actions.approve]));
}

export function awaitsMyReview(
  changeset: ChangesetOut,
  user: string,
  approveRights: Map<string, boolean>,
): boolean {
  return (
    changeset.state === "submitted" &&
    changeset.maker !== user &&
    (approveRights.get(changeset.table) ?? false)
  );
}
