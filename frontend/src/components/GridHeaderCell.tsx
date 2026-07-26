import type { JSX, MouseEvent, ReactNode, TouchEvent } from "react";
import { SortIndicator, type SortState } from "./SortIndicator";
import { Truncate } from "./Truncate";

/** One header cell for every grid (UI_SPECIFICATION.md §2.1, §4.1).
 *
 * Both the rows grid and the shared `DataTable` render their headers through
 * here, which is what makes the spec's "sort headers render identically
 * whether client- or server-backed" true by construction rather than by
 * convention:
 * - the sort control is a real `<button>` (focusable, Enter/Space, disabled
 *   state) inside the `<th>`, with `aria-sort` on the cell;
 * - the three-state affordance comes from the shared `SortIndicator`;
 * - `busy` swaps that icon for a spinner (a server sort in flight) and
 *   `inert` dims and ignores the *other* headers so a second request can't
 *   race the first;
 * - the label truncates via the shared `Truncate`, so a narrow column shows
 *   the full name in a tooltip instead of breaking the grid.
 */

export function GridHeaderCell({
  label,
  width,
  canSort,
  sorted,
  busy = false,
  inert = false,
  numeric = false,
  className,
  extras,
  aside,
  onSort,
  resizeHandler,
  resizing = false,
}: {
  label: string;
  width: number;
  canSort: boolean;
  sorted: SortState;
  /** This column's sort request is in flight. */
  busy?: boolean;
  /** Another column's sort request is in flight — ignore clicks. */
  inert?: boolean;
  numeric?: boolean;
  className?: string;
  /** Decorative markers inside the sort control (e.g. a primary-key icon). */
  extras?: ReactNode;
  /** Interactive markers beside it (e.g. the rule dot) — kept out of the
   * button so they don't become a nested tab stop inside it. */
  aside?: ReactNode;
  onSort?: (event: unknown) => void;
  resizeHandler?: (event: MouseEvent | TouchEvent) => void;
  resizing?: boolean;
}): JSX.Element {
  const classes = [
    canSort ? "sortable" : "",
    numeric ? "tabular" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <th
      className={classes || undefined}
      style={{ width }}
      aria-sort={
        sorted === "asc"
          ? "ascending"
          : sorted === "desc"
            ? "descending"
            : "none"
      }
      aria-disabled={canSort && inert ? true : undefined}
    >
      <span className="th-inner">
        {canSort ? (
          <button
            type="button"
            className="th-sort"
            onClick={inert ? undefined : onSort}
            disabled={inert}
          >
            <Truncate text={label} className="th-label" />
            {extras}
            <SortIndicator sorted={sorted} loading={busy} />
          </button>
        ) : (
          <span className="th-static">
            <Truncate text={label} className="th-label" />
            {extras}
          </span>
        )}
        {aside}
      </span>
      {resizeHandler && (
        <span
          className={`col-resizer ${resizing ? "resizing" : ""}`}
          onMouseDown={resizeHandler}
          onTouchStart={resizeHandler}
          onClick={(event) => event.stopPropagation()}
          aria-hidden="true"
        />
      )}
    </th>
  );
}
