import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, currentUser } from "../api";
import { DataTable, type DataColumn } from "../components/DataTable";
import { GridHeaderCell } from "../components/GridHeaderCell";
import { Icon } from "../components/Icon";
import { SkeletonTable } from "../components/Skeleton";
import { Deadline, StateBadge } from "../components/StateBadge";
import { showToast } from "../components/Toast";
import { Tooltip } from "../components/Tooltip";
import { Truncate } from "../components/Truncate";
import { describeError } from "../errors";
import type {
  ChangeItemIn,
  ChangesetOut,
  ColumnOut,
  Row,
  TableOut,
} from "../types";

const CHANGESET_TAB_COLUMNS: DataColumn<ChangesetOut>[] = [
  {
    id: "title",
    header: "Title",
    accessor: (cs) => cs.title.toLowerCase(),
    cell: (cs) => <Link to={`/changesets/${cs.id}`}>{cs.title}</Link>,
    size: 240,
  },
  {
    id: "state",
    header: "State",
    accessor: (cs) => cs.state,
    cell: (cs) => <StateBadge state={cs.state} />,
    size: 110,
  },
  {
    id: "revision",
    header: "Rev",
    accessor: (cs) => cs.revision,
    size: 60,
    numeric: true,
  },
  { id: "maker", header: "Maker", accessor: (cs) => cs.maker, size: 100 },
  {
    id: "deadline",
    header: "Deadline",
    accessor: (cs) => cs.review_deadline ?? cs.apply_deadline ?? "",
    cell: (cs) => (
      <>
        <Deadline label="review by" value={cs.review_deadline} />
        <Deadline label="apply by" value={cs.apply_deadline} />
      </>
    ),
    size: 180,
  },
];

/** Grid-to-basket drafting per UI_SPECIFICATION.md §4.1 (spec D39).
 *
 * The grid is built on TanStack Table (headless): client-side
 * sort/search/pagination at config-table scale, manual server paging beyond
 * the fetch cap. Editing requires a primary key — update/delete change items
 * must carry a row key (SPECIFICATION.md §3.1), so keyless tables are
 * insert-only.
 */

const FETCH_CAP = 500;
const PAGE_SIZE = 50;
/** Values this long get a textarea instead of a single-line input (§4.1). */
const LONG_TEXT_CHARS = 80;

function rowKey(row: Row, pkCols: string[]): string {
  return JSON.stringify(pkCols.map((c) => row[c]));
}

/** Route for a `backend/schema/table` path, inverting the param decoding
 * in `TableBrowser` (an absent schema travels as `-`). */
function tableHref(tablePath: string): string {
  const [backend, schema, table] = tablePath.split("/");
  return `/t/${backend}/${schema === "" ? "-" : schema}/${table}`;
}

/** Numeric/ID columns align their figures with `tabular-nums` (§2.1). */
function isNumericColumn(column: ColumnOut | undefined): boolean {
  if (!column) return false;
  return /int|dec|num|float|double|real|serial/.test(column.type.toLowerCase());
}

function coerce(column: ColumnOut, raw: string): unknown {
  if (raw === "") return null;
  if (column.type === "integer" || column.type === "decimal") {
    const n = Number(raw);
    return Number.isNaN(n) ? raw : n;
  }
  if (column.type === "boolean") return raw === "true" || raw === "1";
  return raw;
}

function cellText(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

interface Basket {
  /** The table these items belong to, as `backend/schema/table`.
   *
   * A changeset targets exactly one `TableRef` (SPECIFICATION.md §3.1), so the
   * basket is scoped to one table. Carrying the path makes that explicit: items
   * drafted on one table must never be filed against whichever table happens to
   * be on screen when Review is pressed.
   */
  path: string;
  updates: Map<string, { key: Row; before: Row; values: Row }>;
  deletes: Map<string, Row>;
  inserts: Row[];
}

function emptyBasket(path: string): Basket {
  return { path, updates: new Map(), deletes: new Map(), inserts: [] };
}

function basketSize(b: Basket): number {
  return b.updates.size + b.deletes.size + b.inserts.length;
}

function basketToItems(b: Basket): ChangeItemIn[] {
  return [
    ...b.inserts.map(
      (values): ChangeItemIn => ({ op: "insert", key: null, values }),
    ),
    ...[...b.updates.values()].map(
      ({ key, values }): ChangeItemIn => ({ op: "update", key, values }),
    ),
    ...[...b.deletes.values()].map(
      (key): ChangeItemIn => ({ op: "delete", key, values: null }),
    ),
  ];
}

function Pager({
  current,
  count,
  onGo,
}: {
  current: number;
  count: number;
  onGo: (page: number) => void;
}) {
  return (
    <span className="pager">
      <button
        type="button"
        className="chip"
        aria-label="Previous page"
        disabled={current <= 1}
        onClick={() => onGo(current - 1)}
      >
        <Icon name="chevron-left" size={16} />
      </button>
      <input
        key={current}
        type="number"
        min={1}
        max={count}
        defaultValue={current}
        aria-label="Page number"
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        onBlur={(e) => {
          const n = Math.min(
            count,
            Math.max(1, Number(e.target.value) || current),
          );
          if (n !== current) onGo(n);
        }}
      />
      <span className="muted tabular">/ {count}</span>
      <button
        type="button"
        className="chip"
        aria-label="Next page"
        disabled={current >= count}
        onClick={() => onGo(current + 1)}
      >
        <Icon name="chevron-right" size={16} />
      </button>
    </span>
  );
}

function RowEditor({
  columns,
  initial,
  onSave,
  onCancel,
  saveLabel,
}: {
  columns: ColumnOut[];
  initial: Row;
  onSave: (values: Row) => void;
  onCancel: () => void;
  saveLabel: string;
}) {
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      columns.map((c) => [
        c.name,
        initial[c.name] == null ? "" : String(initial[c.name]),
      ]),
    ),
  );
  return (
    <tr className="editing">
      <td className="col-marker" />
      {columns.map((c) => {
        const value = draft[c.name] ?? "";
        // §4.1's third tier: long text is edited in full, not through a
        // single-line window onto it.
        const longText = value.length >= LONG_TEXT_CHARS;
        const onEdit = (next: string) =>
          setDraft((d) => ({ ...d, [c.name]: next }));
        return (
          <td key={c.name}>
            {longText ? (
              <textarea
                rows={3}
                value={value}
                aria-label={c.name}
                placeholder={c.name}
                onChange={(e) => onEdit(e.target.value)}
              />
            ) : (
              <input
                value={value}
                aria-label={c.name}
                placeholder={c.name}
                onChange={(e) => onEdit(e.target.value)}
              />
            )}
          </td>
        );
      })}
      <td className="row-actions row-actions-open">
        <button
          type="button"
          className="chip"
          onClick={() =>
            onSave(
              Object.fromEntries(
                columns.map((c) => [c.name, coerce(c, draft[c.name] ?? "")]),
              ),
            )
          }
        >
          <Icon name="check" size={16} />
          {saveLabel}
        </button>
        <button type="button" className="chip" onClick={onCancel}>
          <Icon name="close" size={16} />
          cancel
        </button>
      </td>
    </tr>
  );
}

function ImportDialog({
  table,
  onClose,
  onDone,
}: {
  table: TableOut;
  onClose: () => void;
  onDone: (changesetId: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"append" | "diff">("append");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<
    { issues: { row: number; column: string | null; message: string }[] } | null
  >(null);
  const [draftId, setDraftId] = useState<string | null>(null);

  const run = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const text = await file.text();
      let changesetId = draftId;
      if (!changesetId) {
        const draft = await api.createChangeset({
          backend: table.backend,
          schema_name: table.schema_name,
          table: table.table,
          title: title.trim() || `Import ${file.name}`,
          description: `Bulk import from ${file.name} (${mode} mode)`,
          items: [],
          submit_now: false,
        });
        changesetId = draft.id;
        setDraftId(changesetId);
      }
      const result = await api.importCsv(changesetId, file.name, mode, text);
      if (result.ok) {
        showToast(
          `Imported ${result.items_added} change item${
            result.items_added === 1 ? "" : "s"
          } from ${file.name} into the draft`,
          "success",
        );
        onDone(changesetId);
      } else {
        // All-or-nothing (D36): the structured report is the actionable
        // channel; the toast is only the ambient signal.
        setReport(result);
        showToast(
          `CSV import rejected — ${result.issues.length} issue${
            result.issues.length === 1 ? "" : "s"
          }, nothing was added`,
          "error",
        );
      }
    } catch (e) {
      const message = describeError(e);
      setError(message);
      showToast(`CSV import failed: ${message}`, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="slideover-backdrop" onClick={onClose}>
      <div className="slideover" onClick={(e) => e.stopPropagation()}>
        <h2>Import CSV into a draft changeset</h2>
        <p className="muted">
          <strong>append</strong>: each row is a change (optional{" "}
          <code>_op</code> column: insert/update/delete; default insert).{" "}
          <strong>diff</strong>: the file is the desired end state — bizkit
          compares it to the current rows and drafts the delta.
        </p>
        <label>
          CSV file
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          Mode
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as "append" | "diff")}
          >
            <option value="append">append — rows are changes</option>
            <option value="diff">diff — file is the desired end state</option>
          </select>
        </label>
        <label>
          Draft title
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={file ? `Import ${file.name}` : "Import…"}
          />
        </label>
        {error && <p className="error">{error}</p>}
        {report && (
          <div className="panel">
            <p className="error">
              Import failed — nothing was added (all-or-nothing). Fix the file
              and retry into the same draft.
            </p>
            {report.issues.slice(0, 20).map((issue, i) => (
              <p key={i} className="muted">
                row {issue.row}
                {issue.column ? ` [${issue.column}]` : ""}: {issue.message}
              </p>
            ))}
            {report.issues.length > 20 && (
              <p className="muted">…and {report.issues.length - 20} more</p>
            )}
          </div>
        )}
        <p className="actions">
          <button
            type="button"
            className="primary"
            disabled={!file || busy}
            onClick={() => void run()}
          >
            {busy ? "Importing…" : "Import"}
          </button>
          <button type="button" onClick={onClose}>
            Cancel
          </button>
        </p>
      </div>
    </div>
  );
}

function ReviewSlideOver({
  table,
  basket,
  onClose,
  onDone,
}: {
  table: TableOut;
  basket: Basket;
  onClose: () => void;
  onDone: (changesetId: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const count = basketSize(basket);

  const create = useMutation({
    mutationFn: async (submitNow: boolean) => {
      const cs = await api.createChangeset({
        backend: table.backend,
        schema_name: table.schema_name,
        table: table.table,
        title,
        description,
        items: basketToItems(basket),
        submit_now: submitNow,
      });
      return { cs, submitNow };
    },
    onSuccess: ({ cs, submitNow }) => {
      showToast(
        submitNow
          ? `Submitted for review: “${cs.title}” — ${count} change${
              count === 1 ? "" : "s"
            } on ${table.path}`
          : `Draft saved: “${cs.title}” — ${count} change${
              count === 1 ? "" : "s"
            } on ${table.path}`,
        "success",
      );
      onDone(cs.id);
    },
    onError: (e) => {
      // Inline first (§6): the toast never replaces the message next to the
      // control that failed.
      const message = describeError(e);
      setError(message);
      showToast(message, "error");
    },
  });

  const overCap = count > table.max_changeset_items;

  return (
    <div className="slideover-backdrop" onClick={onClose}>
      <div className="slideover" onClick={(e) => e.stopPropagation()}>
        <h2>
          Review draft — {count} change{count === 1 ? "" : "s"}
        </h2>
        <p className={`muted ${overCap ? "error" : ""}`}>
          {count} / {table.max_changeset_items} items (effective cap)
        </p>

        {basket.inserts.map((values, i) => (
          <div className="diff-item" key={`i${i}`}>
            <span className="op op-insert" aria-label="operation: insert">
              insert
            </span>
            <code>{JSON.stringify(values)}</code>
          </div>
        ))}
        {[...basket.updates.values()].map(({ key, before, values }, i) => (
          <div className="diff-item" key={`u${i}`}>
            <span className="op op-update" aria-label="operation: update">
              update
            </span>
            <code>{JSON.stringify(key)}</code>
            <div className="diff-cols">
              {Object.entries(values).map(([col, after]) => (
                <div key={col}>
                  <strong>{col}</strong>:{" "}
                  <span className="before">{cellText(before[col])}</span> →{" "}
                  <span className="after">{cellText(after)}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
        {[...basket.deletes.values()].map((key, i) => (
          <div className="diff-item" key={`d${i}`}>
            <span className="op op-delete" aria-label="operation: delete">
              delete
            </span>
            <code>{JSON.stringify(key)}</code>
          </div>
        ))}

        <label>
          Title
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="What is changing?"
          />
        </label>
        <label>
          Description
          <textarea
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Why is it changing?"
          />
        </label>
        {error && <p className="error">{error}</p>}
        <p className="actions">
          <button
            type="button"
            disabled={!title.trim() || overCap || create.isPending}
            onClick={() => create.mutate(false)}
          >
            Save draft
          </button>
          <button
            type="button"
            className="primary"
            disabled={!title.trim() || overCap || create.isPending}
            onClick={() => create.mutate(true)}
          >
            Save &amp; submit for review
          </button>
          <button type="button" onClick={onClose}>
            Keep editing
          </button>
        </p>
      </div>
    </div>
  );
}

export function TableBrowser() {
  const params = useParams<{
    backend: string;
    schema: string;
    table: string;
  }>();
  const backend = params.backend!;
  const schema = params.schema === "-" ? null : (params.schema ?? null);
  const tableName = params.table!;
  const path = `${backend}/${schema ?? ""}/${tableName}`;
  const user = currentUser();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [tab, setTab] = useState<"rows" | "changesets" | "rules">("rows");
  const [serverPage, setServerPage] = useState(1);
  const [search, setSearch] = useState("");
  const [sorting, setSorting] = useState<SortingState>([]);
  const deferredSearch = useDeferredValue(search);
  const [basket, setBasket] = useState<Basket>(() => emptyBasket(path));
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const { data: tables } = useQuery({
    queryKey: ["tables", user],
    queryFn: api.listTables,
  });
  const tableConfig = tables?.find((t) => t.path === path);
  const canView = tableConfig?.actions.view ?? true;

  const { data: columns } = useQuery({
    queryKey: ["columns", path],
    queryFn: () => api.listColumns(backend, schema, tableName),
    enabled: canView,
  });
  const { data: probe, error: rowsError } = useQuery({
    queryKey: ["rows", path],
    queryFn: () => api.listRows(backend, schema, tableName, 1, FETCH_CAP),
    enabled: canView,
  });
  const serverMode = (probe?.total ?? 0) > FETCH_CAP;
  const serverSort = sorting[0]?.id ?? "";
  const serverDir: "asc" | "desc" = sorting[0]?.desc ? "desc" : "asc";
  const { data: serverRows, isFetching: serverFetching } = useQuery({
    queryKey: [
      "rows",
      path,
      "page",
      serverPage,
      deferredSearch,
      serverSort,
      serverDir,
    ],
    queryFn: () =>
      api.listRows(
        backend,
        schema,
        tableName,
        serverPage,
        PAGE_SIZE,
        deferredSearch,
        serverSort,
        serverDir,
      ),
    enabled: canView && serverMode,
  });
  useEffect(() => {
    if (serverMode) setServerPage(1);
  }, [serverMode, deferredSearch, serverSort, serverDir]);
  const { data: changesets } = useQuery({
    queryKey: ["changesets"],
    queryFn: api.listChangesets,
  });

  // React Router reuses this component when only the :table param changes, so
  // every piece of per-table state below has to be retargeted by hand.
  //
  // An empty basket just adopts the new table. A non-empty one cannot be moved
  // (its items are rows of the *old* table), so it is left alone here and §4.1's
  // keep-draft/discard prompt takes over — see `staleBasket`.
  useEffect(() => {
    if (basket.path !== path && basketSize(basket) === 0) {
      setBasket(emptyBasket(path));
    }
  }, [basket, path]);

  // Sort/search/paging/edit state is per-table too: a sort column or row key
  // from the previous table is meaningless against this one.
  useEffect(() => {
    setSearch("");
    setSorting([]);
    setServerPage(1);
    setEditingKey(null);
    setAdding(false);
    setConfirmDiscard(false);
  }, [path]);

  const pkCols = useMemo(
    () => (columns ?? []).filter((c) => c.primary_key).map((c) => c.name),
    [columns],
  );
  const hasKey = pkCols.length > 0;
  const canSubmit = tableConfig?.actions.submit ?? false;
  const canEditRows = canSubmit && hasKey;
  const tableChangesets = (changesets ?? []).filter((c) => c.table === path);

  const rulesByColumn = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const rule of tableConfig?.rules ?? []) {
      const cols = rule.column
        ? [rule.column]
        : ((rule.params.columns as string[] | undefined) ?? []);
      for (const col of cols) {
        map.set(col, [
          ...(map.get(col) ?? []),
          rule.description || rule.rule_id,
        ]);
      }
    }
    return map;
  }, [tableConfig]);

  const data = useMemo(
    () => (serverMode ? (serverRows?.rows ?? []) : (probe?.rows ?? [])),
    [serverMode, serverRows, probe],
  );
  const columnDefs = useMemo<ColumnDef<Row>[]>(
    () =>
      (columns ?? []).map((c) => ({
        id: c.name,
        accessorFn: (row: Row) => row[c.name],
        enableSorting: true,
        enableGlobalFilter: !serverMode,
      })),
    [columns, serverMode],
  );

  const grid = useReactTable({
    data,
    columns: columnDefs,
    state: { globalFilter: serverMode ? "" : search, sorting },
    onGlobalFilterChange: setSearch,
    onSortingChange: setSorting,
    globalFilterFn: (row, columnId, filterValue) =>
      String(row.getValue(columnId) ?? "")
        .toLowerCase()
        .includes(String(filterValue).toLowerCase()),
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: PAGE_SIZE } },
    manualPagination: serverMode,
    manualSorting: serverMode,
    manualFiltering: serverMode,
    enableColumnResizing: true,
    columnResizeMode: "onChange",
    defaultColumn: { minSize: 70, size: 150, maxSize: 600 },
  });

  if (tableConfig === undefined && tables !== undefined) {
    return (
      <p className="error">
        Table {path} is not visible to {user}.
      </p>
    );
  }

  const saveEdit = (row: Row, values: Row) => {
    const key = Object.fromEntries(pkCols.map((c) => [c, row[c]]));
    const changed: Row = {};
    for (const [col, after] of Object.entries(values)) {
      if (!pkCols.includes(col) && String(after) !== String(row[col])) {
        changed[col] = after;
      }
    }
    setBasket((b) => {
      const updates = new Map(b.updates);
      const k = rowKey(row, pkCols);
      if (Object.keys(changed).length === 0) updates.delete(k);
      else updates.set(k, { key, before: row, values: changed });
      return { ...b, updates };
    });
    setEditingKey(null);
  };

  const toggleDelete = (row: Row) => {
    const k = rowKey(row, pkCols);
    setBasket((b) => {
      const deletes = new Map(b.deletes);
      if (deletes.has(k)) deletes.delete(k);
      else deletes.set(k, Object.fromEntries(pkCols.map((c) => [c, row[c]])));
      return { ...b, deletes };
    });
  };

  const count = basketSize(basket);
  // A draft left behind on another table: the basket bar and review step stay
  // hidden while this holds, so items can never be filed against `path`.
  const staleBasket = count > 0 && basket.path !== path;
  const totalRows = probe?.total ?? 0;
  const filteredCount = serverMode
    ? (serverRows?.total ?? totalRows)
    : grid.getFilteredRowModel().rows.length;
  const pageCount = serverMode
    ? Math.max(1, Math.ceil((serverRows?.total ?? totalRows) / PAGE_SIZE))
    : Math.max(1, grid.getPageCount());
  const currentPage = serverMode
    ? Math.min(serverPage, pageCount)
    : grid.getState().pagination.pageIndex + 1;
  const goToPage = (page: number) => {
    const clamped = Math.min(pageCount, Math.max(1, page));
    if (serverMode) setServerPage(clamped);
    else grid.setPageIndex(clamped - 1);
  };
  // A server-backed sort is the only case where the affordance changes at all
  // (§4.1): spinner on the active header, the others inert until it resolves.
  const sortBusy = serverMode && serverFetching;
  const activeSort = sorting[0]?.id ?? null;

  const discard = () => {
    showToast(
      `Draft discarded — ${count} unsaved change${
        count === 1 ? "" : "s"
      } on ${basket.path}`,
      "info",
    );
    setBasket(emptyBasket(path));
    setEditingKey(null);
    setAdding(false);
    setConfirmDiscard(false);
  };

  return (
    <>
      <h1>
        <code>{path}</code>
      </h1>
      <p className="chips">
        {tableConfig && (
          <>
            <span className="chip-static">{tableConfig.rule_count} rules</span>
            {tableConfig.review_ttl_seconds !== null && (
              <span className="chip-static">
                review {Math.round(tableConfig.review_ttl_seconds / 86400)}d
              </span>
            )}
            {tableConfig.allow_self_approval && (
              <span className="badge-self">SELF-APPROVAL LIVE</span>
            )}
            <span className="chip-static">
              you:{" "}
              {[
                tableConfig.actions.submit && "maker",
                tableConfig.actions.approve && "checker",
                !tableConfig.actions.submit &&
                  !tableConfig.actions.approve &&
                  "reader",
              ]
                .filter(Boolean)
                .join(" + ")}
            </span>
          </>
        )}
      </p>

      <p className="filters">
        <button
          type="button"
          className={`chip ${tab === "rows" ? "active" : ""}`}
          aria-pressed={tab === "rows"}
          onClick={() => setTab("rows")}
        >
          Rows
        </button>
        <button
          type="button"
          className={`chip ${tab === "changesets" ? "active" : ""}`}
          aria-pressed={tab === "changesets"}
          onClick={() => setTab("changesets")}
        >
          Changesets ({tableChangesets.length})
        </button>
        <button
          type="button"
          className={`chip ${tab === "rules" ? "active" : ""}`}
          aria-pressed={tab === "rules"}
          onClick={() => setTab("rules")}
        >
          Rules &amp; policy ({tableConfig?.rules.length ?? 0})
        </button>
      </p>

      {tab === "rows" && (
        <>
          {rowsError ? (
            <p className="error">
              Could not load rows: {describeError(rowsError)}
            </p>
          ) : !columns || !probe ? (
            <SkeletonTable rows={8} cols={5} />
          ) : (
            <>
              {serverMode && (
                <p className="muted">
                  Large table ({totalRows.toLocaleString()} rows) — paging,
                  search, and sort run server-side.
                </p>
              )}
              <p className="actions toolbar">
                <input
                  className="search"
                  placeholder="Search rows…"
                  aria-label="Search rows"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                {canSubmit && (
                  <>
                    <button
                      type="button"
                      className="chip"
                      onClick={() => setAdding(true)}
                      disabled={adding}
                    >
                      <Icon name="plus" size={16} />
                      Add row
                    </button>
                    <button
                      type="button"
                      className="chip"
                      onClick={() => setImporting(true)}
                    >
                      <Icon name="upload" size={16} />
                      Import CSV…
                    </button>
                    {!hasKey && (
                      <Tooltip
                        content="This table has no primary key. Updates and deletes need a row key to target a row, so only inserts can be drafted here."
                        focusable
                      >
                        <span className="chip-static">
                          <Icon name="info" size={16} /> insert-only
                        </span>
                      </Tooltip>
                    )}
                    <Link
                      className="muted"
                      to={`/tables/new?backend=${encodeURIComponent(backend)}&schema=${encodeURIComponent(schema ?? "")}&table=${encodeURIComponent(tableName)}`}
                    >
                      manual draft…
                    </Link>
                  </>
                )}
                <span className="spacer" />
                <Pager
                  current={currentPage}
                  count={pageCount}
                  onGo={goToPage}
                />
              </p>
              <div className="table-wrap">
                <table className="grid">
                  <thead>
                    <tr>
                      <th className="col-marker" />
                      {grid.getHeaderGroups()[0]?.headers.map((header) => {
                        const name = header.column.id;
                        const spec = columns.find((c) => c.name === name);
                        const columnRules = rulesByColumn.get(name);
                        return (
                          <GridHeaderCell
                            key={header.id}
                            label={name}
                            width={header.getSize()}
                            canSort={header.column.getCanSort()}
                            sorted={header.column.getIsSorted()}
                            busy={sortBusy && activeSort === name}
                            inert={sortBusy && activeSort !== name}
                            numeric={isNumericColumn(spec)}
                            onSort={header.column.getToggleSortingHandler()}
                            resizeHandler={header.getResizeHandler()}
                            resizing={header.column.getIsResizing()}
                            extras={
                              spec?.primary_key ? (
                                <Icon
                                  name="key"
                                  size={16}
                                  className="muted"
                                  title="primary key"
                                />
                              ) : undefined
                            }
                            aside={
                              columnRules ? (
                                <Tooltip
                                  content={`Validation rules:\n• ${columnRules.join("\n• ")}`}
                                  focusable
                                  hoverOnly
                                >
                                  <span
                                    className="rule-dot"
                                    role="img"
                                    aria-label={`${columnRules.length} validation rule(s) on ${name}`}
                                  />
                                </Tooltip>
                              ) : undefined
                            }
                          />
                        );
                      })}
                      {canSubmit && <th className="actions-col" />}
                    </tr>
                  </thead>
                  <tbody>
                    {adding && (
                      <RowEditor
                        columns={columns}
                        initial={{}}
                        saveLabel="add"
                        onCancel={() => setAdding(false)}
                        onSave={(values) => {
                          setBasket((b) => ({
                            ...b,
                            inserts: [...b.inserts, values],
                          }));
                          setAdding(false);
                        }}
                      />
                    )}
                    {basket.inserts.map((values, i) => (
                      <tr key={`new${i}`} className="row-insert">
                        <td className="col-marker">
                          <span
                            className="op op-insert"
                            aria-label="operation: insert"
                          >
                            new
                          </span>
                        </td>
                        {columns.map((c) => (
                          <td
                            key={c.name}
                            className={
                              isNumericColumn(c) ? "tabular" : undefined
                            }
                          >
                            <Truncate text={cellText(values[c.name])} />
                          </td>
                        ))}
                        {canSubmit && (
                          <td className="row-actions">
                            <Tooltip content="Remove this pending insert">
                              <button
                                type="button"
                                className="icon-button"
                                onClick={() =>
                                  setBasket((b) => ({
                                    ...b,
                                    inserts: b.inserts.filter(
                                      (_, j) => j !== i,
                                    ),
                                  }))
                                }
                                aria-label="Undo this pending insert"
                              >
                                <Icon name="undo" size={16} />
                              </button>
                            </Tooltip>
                          </td>
                        )}
                      </tr>
                    ))}
                    {grid.getRowModel().rows.map((gridRow) => {
                      const row = gridRow.original;
                      const k = hasKey ? rowKey(row, pkCols) : gridRow.id;
                      if (canEditRows && editingKey === k) {
                        return (
                          <RowEditor
                            key={k}
                            columns={columns}
                            initial={{
                              ...row,
                              ...(basket.updates.get(k)?.values ?? {}),
                            }}
                            saveLabel="apply"
                            onCancel={() => setEditingKey(null)}
                            onSave={(values) => saveEdit(row, values)}
                          />
                        );
                      }
                      const pendingUpdate = hasKey
                        ? basket.updates.get(k)
                        : undefined;
                      const pendingDelete = hasKey && basket.deletes.has(k);
                      return (
                        <tr
                          key={k}
                          className={
                            pendingDelete
                              ? "row-delete"
                              : pendingUpdate
                                ? "row-update"
                                : ""
                          }
                        >
                          <td className="col-marker">
                            {pendingUpdate && (
                              <span
                                className="op op-update"
                                aria-label="operation: update"
                              >
                                edit
                              </span>
                            )}
                            {pendingDelete && (
                              <span
                                className="op op-delete"
                                aria-label="operation: delete"
                              >
                                del
                              </span>
                            )}
                          </td>
                          {columns.map((c) => {
                            const changed =
                              pendingUpdate && c.name in pendingUpdate.values;
                            return (
                              <td
                                key={c.name}
                                className={[
                                  changed ? "changed" : "",
                                  isNumericColumn(c) ? "tabular" : "",
                                ]
                                  .filter(Boolean)
                                  .join(" ")}
                              >
                                <Truncate
                                  text={cellText(
                                    changed
                                      ? pendingUpdate.values[c.name]
                                      : row[c.name],
                                  )}
                                />
                              </td>
                            );
                          })}
                          {canSubmit && (
                            <td className="row-actions">
                              {canEditRows && (
                                <>
                              <Tooltip
                                content={
                                  pendingDelete
                                    ? "Undo the delete before editing this row"
                                    : "Edit this row"
                                }
                                focusable={pendingDelete}
                              >
                                <button
                                  type="button"
                                  className="icon-button"
                                  onClick={() => setEditingKey(k)}
                                  disabled={pendingDelete}
                                  aria-label="Edit this row"
                                >
                                  <Icon name="pencil" size={16} />
                                </button>
                              </Tooltip>
                              <Tooltip
                                content={
                                  pendingDelete
                                    ? "Keep this row after all"
                                    : "Draft a delete for this row"
                                }
                              >
                                <button
                                  type="button"
                                  className="icon-button"
                                  onClick={() => toggleDelete(row)}
                                  aria-label={
                                    pendingDelete
                                      ? "Undo the drafted delete"
                                      : "Draft a delete for this row"
                                  }
                                >
                                  <Icon
                                    name={pendingDelete ? "undo" : "trash"}
                                    size={16}
                                  />
                                </button>
                              </Tooltip>
                                </>
                              )}
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="muted tabular">
                {filteredCount.toLocaleString()}
                {search && filteredCount !== totalRows
                  ? ` of ${totalRows.toLocaleString()}`
                  : ""}{" "}
                rows
              </p>
            </>
          )}
        </>
      )}

      {tab === "changesets" && (
        <DataTable
          columns={CHANGESET_TAB_COLUMNS}
          data={tableChangesets}
          rowKey={(cs) => cs.id}
          emptyText="No changesets touch this table yet — draft one from the Rows tab."
        />
      )}

      {tab === "rules" && tableConfig && (
        <>
          <div className="panel">
            <h2>Workflow policy</h2>
            <dl>
              <dt>Review window</dt>
              <dd>
                {tableConfig.review_ttl_seconds === null
                  ? "no expiry"
                  : tableConfig.review_ttl_seconds <= 0
                    ? "lapses immediately (demo)"
                    : `${Math.round(tableConfig.review_ttl_seconds / 86400)} day(s)`}
              </dd>
              <dt>Apply window</dt>
              <dd>
                {tableConfig.apply_ttl_seconds === null
                  ? "no expiry"
                  : `${Math.round(tableConfig.apply_ttl_seconds / 86400)} day(s)`}
              </dd>
              <dt>Self-approval</dt>
              <dd>
                {tableConfig.allow_self_approval ? (
                  <span className="badge-self">LIVE</span>
                ) : (
                  "four-eyes enforced"
                )}
              </dd>
              <dt>Max changeset items</dt>
              <dd className="tabular">{tableConfig.max_changeset_items}</dd>
            </dl>
          </div>
          <div className="panel">
            <h2>Validation rules</h2>
            {tableConfig.rules.length === 0 && (
              <p className="muted">
                No validation rules declared for this table.
              </p>
            )}
            {tableConfig.rules.map((rule) => (
              <div className="rule-card" key={rule.rule_id}>
                <div className="rule-head">
                  <span className={`rule-kind kind-${rule.kind}`}>
                    {rule.kind.replace("_", " ")}
                  </span>
                  <code>{rule.rule_id}</code>
                  {rule.column && (
                    <span className="muted">on {rule.column}</span>
                  )}
                </div>
                {rule.description && <p>{rule.description}</p>}
                <div className="rule-params">
                  {Object.entries(rule.params).map(([k, v]) => (
                    <span className="chip-static" key={k}>
                      {k}: {JSON.stringify(v)}
                    </span>
                  ))}
                </div>
              </div>
            ))}
            <p className="muted">
              Rules are declarative workspace configuration (spec D11/D22) —
              change them via a config-file PR, not in the app.
            </p>
          </div>
        </>
      )}

      {count > 0 && !staleBasket && (
        <div className="basket-bar">
          <span>
            Draft: {count} change{count === 1 ? "" : "s"} (
            {basket.updates.size} update · {basket.inserts.length} insert ·{" "}
            {basket.deletes.size} delete)
          </span>
          <span className="spacer" />
          {confirmDiscard ? (
            <>
              <span className="muted">Discard all of it?</span>
              <button type="button" className="danger" onClick={discard}>
                Yes, discard
              </button>
              <button type="button" onClick={() => setConfirmDiscard(false)}>
                Keep editing
              </button>
            </>
          ) : (
            <button type="button" onClick={() => setConfirmDiscard(true)}>
              <Icon name="trash" size={16} />
              Discard
            </button>
          )}
          <button
            type="button"
            className="primary"
            onClick={() => setReviewing(true)}
          >
            Review &amp; submit
          </button>
        </div>
      )}

      {/* Switching tables with unsaved edits prompts (UI_SPECIFICATION.md
          §4.1). Deliberately not dismissable by clicking the scrim: the draft
          either comes with you or is discarded on the record. */}
      {staleBasket && (
        <div className="slideover-backdrop">
          <div className="slideover" onClick={(e) => e.stopPropagation()}>
            <h2>Unsaved draft on another table</h2>
            <p>
              You have {count} unsaved change{count === 1 ? "" : "s"} on{" "}
              <code>{basket.path}</code>. A changeset covers a single table, so
              they cannot move to <code>{path}</code>.
            </p>
            <p className="actions">
              <button
                type="button"
                className="primary"
                onClick={() => void navigate(tableHref(basket.path))}
              >
                Keep draft — back to {basket.path}
              </button>
              <button type="button" className="danger" onClick={discard}>
                Discard {count} change{count === 1 ? "" : "s"}
              </button>
            </p>
          </div>
        </div>
      )}

      {importing && tableConfig && (
        <ImportDialog
          table={tableConfig}
          onClose={() => setImporting(false)}
          onDone={(id) => {
            setImporting(false);
            void queryClient.invalidateQueries();
            void navigate(`/changesets/${id}`);
          }}
        />
      )}

      {reviewing && tableConfig && !staleBasket && (
        <ReviewSlideOver
          table={tableConfig}
          basket={basket}
          onClose={() => setReviewing(false)}
          onDone={(id) => {
            setBasket(emptyBasket(path));
            setReviewing(false);
            void queryClient.invalidateQueries();
            void navigate(`/changesets/${id}`);
          }}
        />
      )}
    </>
  );
}
