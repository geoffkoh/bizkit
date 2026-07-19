import {
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useMemo, useState, type ReactNode } from "react";

/** Shared sortable + column-resizable table (UI_SPECIFICATION.md §2.1).
 *
 * Keeps every list table consistent with the rows grid: clickable
 * sort headers with ▲/▼, draggable column edges, card styling.
 */

export interface DataColumn<T> {
  id: string;
  header: string;
  accessor: (row: T) => unknown;
  cell?: (row: T) => ReactNode;
  size?: number;
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
    defaultColumn: { minSize: 60, maxSize: 600 },
  });

  if (data.length === 0 && emptyText) {
    return <p className="muted">{emptyText}</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {table.getHeaderGroups()[0]?.headers.map((header) => {
              const spec = columns.find((c) => c.id === header.column.id);
              const sorted = header.column.getIsSorted();
              return (
                <th
                  key={header.id}
                  className="sortable"
                  style={{ width: header.getSize() }}
                  onClick={header.column.getToggleSortingHandler()}
                  title="click to sort"
                >
                  {spec?.header}
                  {sorted && (
                    <span className="sort-ind">
                      {sorted === "asc" ? " ▲" : " ▼"}
                    </span>
                  )}
                  <span
                    className={`col-resizer ${
                      header.column.getIsResizing() ? "resizing" : ""
                    }`}
                    onMouseDown={header.getResizeHandler()}
                    onTouchStart={header.getResizeHandler()}
                    onClick={(e) => e.stopPropagation()}
                  />
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={rowKey(row.original)}>
              {columns.map((c) => (
                <td key={c.id}>
                  {c.cell
                    ? c.cell(row.original)
                    : String(c.accessor(row.original) ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
