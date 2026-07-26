import type { JSX } from "react";
import { Icon } from "./Icon";

/** The one sort affordance (UI_SPECIFICATION.md §4.1).
 *
 * Three states, identical whether the sort runs client-side (TanStack
 * `sortingState`) or server-side (`sort`/`direction` params): neutral `sort`
 * → accent `arrow-up` → accent `arrow-down`. The only visible difference for
 * a server-backed table is `loading`, which swaps the icon for a spinner
 * while the request is in flight — a maker never needs to know which mode a
 * table is in.
 */

export type SortState = false | "asc" | "desc";

export function SortIndicator({
  sorted,
  loading = false,
}: {
  sorted: SortState;
  loading?: boolean;
}): JSX.Element {
  if (loading) {
    return (
      <span className="sort-ind">
        <Icon name="spinner" size={16} spin title="Sorting…" />
      </span>
    );
  }
  if (sorted === "asc") {
    return (
      <span className="sort-ind">
        <Icon name="arrow-up" size={16} title="sorted ascending" />
      </span>
    );
  }
  if (sorted === "desc") {
    return (
      <span className="sort-ind">
        <Icon name="arrow-down" size={16} title="sorted descending" />
      </span>
    );
  }
  return (
    <span className="sort-ind neutral">
      <Icon name="sort" size={16} />
    </span>
  );
}
