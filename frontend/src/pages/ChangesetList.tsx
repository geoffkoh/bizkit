import { useQuery } from "@tanstack/react-query";
import { useState, type JSX } from "react";
import { Link } from "react-router-dom";
import { api, currentUser } from "../api";
import { DataTable, type DataColumn } from "../components/DataTable";
import { SkeletonTable } from "../components/Skeleton";
import { Deadline, StateBadge } from "../components/StateBadge";
import { describeError } from "../errors";
import { approveRightsByPath, awaitsMyReview } from "../queue";
import type { ChangesetOut } from "../types";

/** The Queue (UI_SPECIFICATION.md §4.2): filters, free-text search, and one
 * sentence + the next action for every empty state (§6). */

type Filter = "all" | "to-review" | "mine";

const COLUMNS: DataColumn<ChangesetOut>[] = [
  {
    id: "title",
    header: "Title",
    accessor: (cs) => cs.title.toLowerCase(),
    cell: (cs) => <Link to={`/changesets/${cs.id}`}>{cs.title}</Link>,
    size: 220,
  },
  {
    id: "table",
    header: "Table",
    accessor: (cs) => cs.table,
    cell: (cs) => <code>{cs.table}</code>,
    size: 180,
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
  {
    id: "items",
    header: "Items",
    accessor: (cs) => cs.item_count,
    size: 70,
    numeric: true,
  },
  {
    id: "maker",
    header: "Maker",
    accessor: (cs) => cs.maker,
    size: 100,
  },
  {
    id: "updated",
    header: "Updated",
    accessor: (cs) => cs.updated_at,
    cell: (cs) => (
      <span className="muted">{new Date(cs.updated_at).toLocaleString()}</span>
    ),
    size: 160,
  },
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

export function ChangesetList(): JSX.Element {
  const user = currentUser();
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["changesets"],
    queryFn: api.listChangesets,
  });
  // Same query the sidebar uses; drives the approve-right half of "to review".
  const { data: tables } = useQuery({
    queryKey: ["tables", user],
    queryFn: api.listTables,
  });
  const approveRights = approveRightsByPath(tables);

  if (error) {
    return (
      <p className="error">Could not load changesets: {describeError(error)}</p>
    );
  }

  const all = data ?? [];
  const q = search.trim().toLowerCase();
  const visible = all.filter((cs) => {
    if (filter === "to-review" && !awaitsMyReview(cs, user, approveRights))
      return false;
    if (filter === "mine" && cs.maker !== user) return false;
    if (
      q &&
      ![cs.title, cs.table, cs.maker, cs.state].some((v) =>
        v.toLowerCase().includes(q),
      )
    )
      return false;
    return true;
  });

  // §6 empty states: one sentence and the next action, specific to why the
  // list is empty.
  const emptyText = q
    ? `Nothing matches “${search.trim()}” — clear the search to see the rest.`
    : filter === "to-review"
      ? "Nothing is awaiting your review — you are clear."
      : filter === "mine"
        ? "You have not raised any changesets yet — open a table from the Tables section in the sidebar to draft one."
        : "No changesets yet — open a table from the Tables section in the sidebar to draft the first one.";

  return (
    <>
      <h1>Changesets</h1>
      <p className="filters">
        {(["all", "to-review", "mine"] as const).map((f) => (
          <button
            key={f}
            type="button"
            className={`chip ${filter === f ? "active" : ""}`}
            aria-pressed={filter === f}
            onClick={() => setFilter(f)}
          >
            {f === "to-review" ? `to review (as ${user})` : f}
          </button>
        ))}
        <input
          className="search"
          placeholder="Search title, table, maker, state…"
          aria-label="Search changesets"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </p>
      {isLoading ? (
        <SkeletonTable rows={6} cols={6} label="Loading changesets…" />
      ) : (
        <DataTable
          columns={COLUMNS}
          data={visible}
          rowKey={(cs) => cs.id}
          emptyText={emptyText}
        />
      )}
    </>
  );
}
