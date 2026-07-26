import type { JSX } from "react";

/** Loading placeholders (UI_SPECIFICATION.md §6 Loading, §2.3 shimmer).
 *
 * Grids and lists get skeleton rows on the slow, low-contrast shimmer;
 * panels get an inline "Loading…" instead. Reduced-motion drops the shimmer
 * and leaves the flat blocks.
 */

export function SkeletonTable({
  rows = 6,
  cols = 4,
  label = "Loading rows…",
}: {
  rows?: number;
  cols?: number;
  label?: string;
}): JSX.Element {
  return (
    <div className="skeleton-table" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, row) => (
        <div className="skeleton-row" key={row}>
          {Array.from({ length: cols }, (_, col) => (
            <span className="skeleton skeleton-cell" key={col} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonLines({
  lines = 3,
  label = "Loading…",
}: {
  lines?: number;
  label?: string;
}): JSX.Element {
  return (
    <div role="status" aria-label={label}>
      {Array.from({ length: lines }, (_, line) => (
        <span className="skeleton skeleton-text" key={line} />
      ))}
    </div>
  );
}
