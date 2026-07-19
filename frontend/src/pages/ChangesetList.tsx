import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, currentUser } from "../api";
import { DataTable, type DataColumn } from "../components/DataTable";
import { Deadline, StateBadge } from "../components/StateBadge";
import type { ChangesetOut } from "../types";

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
  },
  {
    id: "items",
    header: "Items",
    accessor: (cs) => cs.item_count,
    size: 70,
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

export function ChangesetList() {
  const user = currentUser();
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["changesets"],
    queryFn: api.listChangesets,
  });

  if (isLoading) return <p className="muted">Loading changesets…</p>;
  if (error) return <p className="error">Failed to load: {String(error)}</p>;
  if (!data || data.length === 0) {
    return (
      <p className="muted">
        No changesets yet. Seed a demo with{" "}
        <code>bizkit init-store --seed-sample</code>, or start one from a
        table in the sidebar.
      </p>
    );
  }

  const q = search.trim().toLowerCase();
  const visible = data.filter((cs) => {
    if (
      filter === "to-review" &&
      !(cs.state === "submitted" && cs.maker !== user)
    )
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

  return (
    <>
      <h1>Changesets</h1>
      <p className="filters">
        {(["all", "to-review", "mine"] as const).map((f) => (
          <button
            key={f}
            type="button"
            className={`chip ${filter === f ? "active" : ""}`}
            onClick={() => setFilter(f)}
          >
            {f === "to-review" ? `to review (as ${user})` : f}
          </button>
        ))}
        <input
          className="search"
          placeholder="Search title, table, maker, state…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </p>
      <DataTable
        columns={COLUMNS}
        data={visible}
        rowKey={(cs) => cs.id}
        emptyText="Nothing in this view."
      />
    </>
  );
}
