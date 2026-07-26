import {
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useMemo, useState, type ReactNode } from "react";
import { GridHeaderCell } from "./GridHeaderCell";
import { Truncate } from "./Truncate";

/** Shared sortable + column-resizable table (UI_SPECIFICATION.md §2.1).
 *
 * Every list table is this component — the Queue and the table browser's
 * Changesets tab included — so they all get the same card treatment, the same
 * focusable three-state sort headers (via `GridHeaderCell`) and the same
 * truncate-with-tooltip overflow behaviour as the rows grid.
 */

export interface DataColumn<T> {
  id: string;
  header: string;
  accessor: (row: T) => unknown;
  cell?: (row: T) => ReactNode;
  size?: number;
  /** Numeric/ID column: aligns figures with `tabular-nums` (§2.1). */
  numeric?: boolean;
}

export function DataTable<T>({
  columns,
  data,
  rowKey,
  emptyText,
}: {
  columns: DataColumn<T>[];
  data: T[];
  rowKey: (row: T) => string;
  emptyText?: string;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const defs = useMemo<ColumnDef<T>[]>(
    () =>
      columns.map((c) => ({
        id: c.id,
        accessorFn: c.accessor,
        enableSorting: true,
        size: c.size ?? 150,
      })),
    [columns],
  );
  const table = useReactTable({
    data,
    columns: defs,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    enableColumnResizing: true,
    columnResizeMode: "onChange",
    defaultColumn: { minSize: 70, maxSize: 600 },
  });

  if (data.length === 0 && emptyText) {
    return <p className="muted empty-state">{emptyText}</p>;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {table.getHeaderGroups()[0]?.headers.map((header) => {
              const spec = columns.find((c) => c.id === header.column.id);
              return (
                <GridHeaderCell
                  key={header.id}
                  label={spec?.header ?? header.column.id}
                  width={header.getSize()}
                  canSort
                  sorted={header.column.getIsSorted()}
                  numeric={spec?.numeric}
                  onSort={header.column.getToggleSortingHandler()}
                  resizeHandler={header.getResizeHandler()}
                  resizing={header.column.getIsResizing()}
                />
              );
            })}
          </tr>
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={rowKey(row.original)}>
              {columns.map((c) => (
                <td key={c.id} className={c.numeric ? "tabular" : undefined}>
                  {c.cell ? (
                    c.cell(row.original)
                  ) : (
                    <Truncate text={String(c.accessor(row.original) ?? "")} />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
