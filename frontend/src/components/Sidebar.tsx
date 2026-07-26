import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type JSX } from "react";
import { NavLink } from "react-router";
import { api, currentUser } from "../api";
import { approveRightsByPath, awaitsMyReview } from "../queue";
import { branchNodeIds, buildTableTree } from "../tableTree";
import { Icon } from "./Icon";
import { Tooltip } from "./Tooltip";
import { Tree } from "./Tree";

/** Sidebar navigation (UI_SPECIFICATION.md §3).
 *
 * The Tables section mirrors the `(backend, schema, table)` scope model
 * exactly: backend → schema → table, from `GET /api/v1/tables`. Progressive
 * disclosure — the schema level renders only when a backend exposes more than
 * one schema to this caller, so the common single-schema case never carries a
 * redundant middle node. Rendering is the shared generic `Tree`; expand state
 * persists per node in localStorage.
 */

const EXPANDED_KEY = "bizkit.sidebar.expanded";

function readExpanded(): Set<string> | null {
  try {
    const raw = localStorage.getItem(EXPANDED_KEY);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return new Set(parsed.filter((v): v is string => typeof v === "string"));
  } catch {
    return null;
  }
}

export function Sidebar({
  collapsed,
  onToggle,
  toggleDisabledReason,
}: {
  collapsed: boolean;
  onToggle: () => void;
  /** Non-empty when the toggle is disabled — §2.4 wants the reason on hover. */
  toggleDisabledReason?: string;
}): JSX.Element {
  const user = currentUser();
  const { data: tables } = useQuery({
    queryKey: ["tables", user],
    queryFn: api.listTables,
  });
  const { data: changesets } = useQuery({
    queryKey: ["changesets"],
    queryFn: api.listChangesets,
  });

  // null = the user has never touched the tree: default to fully expanded.
  const [expanded, setExpanded] = useState<Set<string> | null>(readExpanded);
  useEffect(() => {
    if (expanded) {
      localStorage.setItem(EXPANDED_KEY, JSON.stringify([...expanded]));
    }
  }, [expanded]);

  const approveRights = approveRightsByPath(tables);
  const toReview = (changesets ?? []).filter((cs) =>
    awaitsMyReview(cs, user, approveRights),
  ).length;

  const tree = useMemo(() => buildTableTree(tables ?? []), [tables]);
  const allBranches = useMemo(() => branchNodeIds(tree), [tree]);

  const isExpanded = (id: string) => (expanded ? expanded.has(id) : true);
  const toggleNode = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev ?? allBranches);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleDisabled = Boolean(toggleDisabledReason);

  return (
    <aside className="sidebar">
      <div className="side-scroll">
        <div className="side-section">
          <div className="side-title">Workbench</div>
          <NavLink to="/" end className="side-link">
            <span className="side-icon">
              <Icon name="sidebar" size={16} />
            </span>
            <span className="side-label">Queue</span>
            {toReview > 0 && (
              <span className="count" aria-label={`${toReview} awaiting you`}>
                {toReview}
              </span>
            )}
          </NavLink>
        </div>
        <div className="side-section">
          <div className="side-title">Tables</div>
          {tree.length === 0 ? (
            <p className="side-empty">none visible to {user}</p>
          ) : (
            <Tree
              nodes={tree}
              isExpanded={isExpanded}
              onToggle={toggleNode}
              label="Configuration tables"
              railed={collapsed}
            />
          )}
        </div>
      </div>
      <Tooltip
        content={
          toggleDisabledReason ??
          (collapsed ? "Expand navigation" : "Collapse navigation")
        }
        focusable={toggleDisabled}
        className="side-toggle-host"
      >
        <button
          type="button"
          className="side-toggle"
          onClick={onToggle}
          disabled={toggleDisabled}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          aria-expanded={!collapsed}
        >
          <Icon name={collapsed ? "chevron-right" : "chevron-left"} size={16} />
          <span className="side-label">collapse</span>
        </button>
      </Tooltip>
    </aside>
  );
}
