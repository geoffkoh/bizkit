import { type CSSProperties, type JSX, type KeyboardEvent } from "react";
import { NavLink } from "react-router";
import { Icon, type IconName } from "./Icon";
import { useTooltip } from "./Tooltip";
import { Truncate } from "./Truncate";

/** One generic, recursive tree renderer (UI_SPECIFICATION.md §3).
 *
 * Depth-agnostic on purpose: the sidebar's backend → schema → table tree is
 * data, not three bespoke components. Branches are native disclosure widgets
 * (`<button aria-expanded>`), leaves are router links, and both use the shared
 * `Truncate` label so long names never overflow the rail.
 *
 * In the collapsed 64px rail the label is hidden, so each row carries the
 * shared tooltip with its full identity (`hint`) instead — a rail you cannot
 * read would be worse than no rail.
 *
 * Keyboard (on top of the buttons' native Enter/Space):
 *   ArrowDown/ArrowUp  move between visible rows
 *   ArrowRight         expand a collapsed branch, else step into it
 *   ArrowLeft          collapse an expanded branch, else step out to its parent
 *   Home/End           first/last visible row
 */

export interface TreeNode {
  /** Stable id — also the key used to persist expand/collapse state. */
  id: string;
  label: string;
  /** Full identity for the rail tooltip (e.g. `backend / schema / table`). */
  hint?: string;
  /** Leading icon after the disclosure chevron (branches) or first (leaves). */
  icon?: IconName;
  /** Accessible name/tooltip for that icon (e.g. the affordance meaning). */
  iconTitle?: string;
  /** Branch: children. A node with `children` is always a branch. */
  children?: TreeNode[];
  /** Leaf: router destination. */
  to?: string;
}

export interface TreeProps {
  nodes: TreeNode[];
  isExpanded: (id: string) => boolean;
  onToggle: (id: string) => void;
  /** Accessible name for the whole tree. */
  label: string;
  /** True in the icons-only rail: labels are hidden, so rows get tooltips. */
  railed?: boolean;
}

function rows(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>("[data-tree-row]"));
}

function depthOf(row: HTMLElement): number {
  return Number(row.dataset.treeDepth ?? "0");
}

function BranchRow({
  node,
  depth,
  expanded,
  railed,
  onToggle,
}: {
  node: TreeNode;
  depth: number;
  expanded: boolean;
  railed: boolean;
  onToggle: (id: string) => void;
}): JSX.Element {
  const { ref, hostProps, bubble } = useTooltip<HTMLButtonElement>(
    node.hint ?? node.label,
    railed,
  );
  return (
    <>
      <button
        ref={ref}
        type="button"
        className="side-link tree-branch"
        style={{ "--tree-depth": depth } as CSSProperties}
        aria-expanded={expanded}
        onClick={() => onToggle(node.id)}
        data-tree-row
        data-tree-depth={depth}
        data-tree-branch={node.id}
        {...hostProps}
      >
        <span className="side-icon tree-chevron">
          <Icon name={expanded ? "chevron-down" : "chevron-right"} />
        </span>
        {node.icon && (
          <span className="side-icon affordance">
            <Icon
              name={node.icon}
              title={railed ? undefined : node.iconTitle}
            />
          </span>
        )}
        <Truncate text={node.label} className="side-label tree-label" />
      </button>
      {bubble}
    </>
  );
}

function LeafRow({
  node,
  depth,
  railed,
}: {
  node: TreeNode;
  depth: number;
  railed: boolean;
}): JSX.Element {
  const { ref, hostProps, bubble } = useTooltip<HTMLAnchorElement>(
    node.hint ?? node.label,
    railed,
  );
  return (
    <>
      <NavLink
        ref={ref}
        to={node.to ?? "#"}
        className="side-link tree-leaf"
        style={{ "--tree-depth": depth } as CSSProperties}
        data-tree-row
        data-tree-depth={depth}
        {...hostProps}
      >
        {node.icon && (
          <span className="side-icon affordance">
            <Icon
              name={node.icon}
              title={railed ? undefined : node.iconTitle}
            />
          </span>
        )}
        <Truncate text={node.label} className="side-label tree-label" />
      </NavLink>
      {bubble}
    </>
  );
}

function TreeRows({
  nodes,
  depth,
  railed,
  isExpanded,
  onToggle,
}: {
  nodes: TreeNode[];
  depth: number;
  railed: boolean;
  isExpanded: (id: string) => boolean;
  onToggle: (id: string) => void;
}): JSX.Element[] {
  return nodes.map((node) => {
    if (node.children) {
      const expanded = isExpanded(node.id);
      return (
        <li className="tree-item" key={node.id}>
          <BranchRow
            node={node}
            depth={depth}
            expanded={expanded}
            railed={railed}
            onToggle={onToggle}
          />
          {expanded && node.children.length > 0 && (
            <ul className="tree-group">
              <TreeRows
                nodes={node.children}
                depth={depth + 1}
                railed={railed}
                isExpanded={isExpanded}
                onToggle={onToggle}
              />
            </ul>
          )}
        </li>
      );
    }
    return (
      <li className="tree-item" key={node.id}>
        <LeafRow node={node} depth={depth} railed={railed} />
      </li>
    );
  });
}

export function Tree({
  nodes,
  isExpanded,
  onToggle,
  label,
  railed = false,
}: TreeProps): JSX.Element {
  const onKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    const root = event.currentTarget;
    const current = (event.target as HTMLElement).closest<HTMLElement>(
      "[data-tree-row]",
    );
    if (!current) return;
    const visible = rows(root);
    const index = visible.indexOf(current);
    const branchId = current.dataset.treeBranch;
    const expanded = current.getAttribute("aria-expanded") === "true";

    const focusAt = (next: number) => {
      const target = visible[Math.max(0, Math.min(visible.length - 1, next))];
      if (target) {
        event.preventDefault();
        target.focus();
      }
    };

    switch (event.key) {
      case "ArrowDown":
        focusAt(index + 1);
        break;
      case "ArrowUp":
        focusAt(index - 1);
        break;
      case "Home":
        focusAt(0);
        break;
      case "End":
        focusAt(visible.length - 1);
        break;
      case "ArrowRight":
        if (branchId && !expanded) {
          event.preventDefault();
          onToggle(branchId);
        } else if (branchId) {
          focusAt(index + 1);
        }
        break;
      case "ArrowLeft":
        if (branchId && expanded) {
          event.preventDefault();
          onToggle(branchId);
        } else {
          // Step out: the nearest row above with a smaller depth.
          const depth = depthOf(current);
          for (let i = index - 1; i >= 0; i -= 1) {
            const candidate = visible[i];
            if (candidate && depthOf(candidate) < depth) {
              focusAt(i);
              break;
            }
          }
        }
        break;
      default:
        break;
    }
  };

  return (
    <ul className="tree" aria-label={label} onKeyDown={onKeyDown}>
      <TreeRows
        nodes={nodes}
        depth={0}
        railed={railed}
        isExpanded={isExpanded}
        onToggle={onToggle}
      />
    </ul>
  );
}
