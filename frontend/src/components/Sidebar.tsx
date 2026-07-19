import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { api, currentUser } from "../api";
import type { TableOut } from "../types";

function tableRoute(t: TableOut): string {
  return `/t/${encodeURIComponent(t.backend)}/${encodeURIComponent(
    t.schema_name ?? "-",
  )}/${encodeURIComponent(t.table)}`;
}

export function Sidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const user = currentUser();
  const { data: tables } = useQuery({
    queryKey: ["tables", user],
    queryFn: api.listTables,
  });
  const { data: changesets } = useQuery({
    queryKey: ["changesets"],
    queryFn: api.listChangesets,
  });

  const approveByPath = new Map(
    (tables ?? []).map((t) => [t.path, t.actions.approve]),
  );
  const toReview = (changesets ?? []).filter(
    (cs) =>
      cs.state === "submitted" &&
      cs.maker !== user &&
      approveByPath.get(cs.table),
  ).length;

  const byTarget = new Map<string, TableOut[]>();
  for (const t of tables ?? []) {
    const group = byTarget.get(t.backend) ?? [];
    group.push(t);
    byTarget.set(t.backend, group);
  }

  return (
    <aside className="sidebar">
      <div className="side-scroll">
        <div className="side-section">
          <div className="side-title">Workbench</div>
          <NavLink to="/" end className="side-link" title="Queue">
            <span className="side-icon">☰</span>
            <span className="side-label">Queue</span>
            {toReview > 0 && <span className="count">{toReview}</span>}
          </NavLink>
        </div>
        <div className="side-section">
          <div className="side-title">Tables</div>
          {byTarget.size === 0 && (
            <p className="side-empty">none visible to {user}</p>
          )}
          {[...byTarget.entries()].map(([target, group]) => (
            <div key={target}>
              <div className="side-group">{target}</div>
              {group.map((t) => (
                <NavLink
                  key={t.path}
                  to={tableRoute(t)}
                  className="side-link table-link"
                  title={`${t.table} — ${
                    t.actions.submit
                      ? "you can raise changesets here"
                      : "read-only for you"
                  }`}
                >
                  <span className="side-icon affordance">
                    {t.actions.submit ? "✎" : "👁"}
                  </span>
                  <span className="side-label table-name">{t.table}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </div>
      </div>
      <button
        type="button"
        className="side-toggle"
        onClick={onToggle}
        title={collapsed ? "Expand navigation" : "Collapse navigation"}
      >
        {collapsed ? "»" : "«"}
        <span className="side-label"> collapse</span>
      </button>
    </aside>
  );
}
