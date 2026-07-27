import { useQuery } from "@tanstack/react-query";
import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router";
import { api, currentUser } from "../api";
import { tableRoute } from "../routes";
import { Icon, type IconName } from "./Icon";
import { StateBadge } from "./StateBadge";

/** The one command palette (UI_SPECIFICATION.md §3).
 *
 * A *second index* onto the same navigable set as the sidebar tree and the
 * queue — never a parallel feature. It reads the exact same TanStack Query
 * keys those surfaces already populate (`["tables", user]`,
 * `["changesets"]`), so opening it costs no new request and can never drift
 * from what the sidebar shows.
 *
 * Keyboard: ArrowDown/ArrowUp move (wrapping), Home/End jump, Enter
 * activates, Esc or a scrim click closes. Focus starts in the input and is
 * trapped there; the caller restores focus to the trigger on close.
 */

const GROUPS = ["Tables", "Changesets", "Actions"] as const;
type Group = (typeof GROUPS)[number];

interface PaletteItem {
  id: string;
  group: Group;
  /** Matched against the query, and the primary line of the row. */
  label: string;
  /** Secondary text (breadcrumb, table path); also matched. */
  secondary?: string;
  icon?: IconName;
  iconTitle?: string;
  badge?: ReactNode;
  run: () => void;
}

const PER_GROUP = 8;

/** 0 = label prefix, 1 = secondary prefix, 2 = substring anywhere, -1 = no
 * match. Prefix matches rank above substring matches, then alphabetical. */
function rank(item: PaletteItem, needle: string): number {
  if (!needle) return 0;
  const label = item.label.toLowerCase();
  const secondary = (item.secondary ?? "").toLowerCase();
  if (label.startsWith(needle)) return 0;
  if (secondary.startsWith(needle)) return 1;
  if (label.includes(needle) || secondary.includes(needle)) return 2;
  return -1;
}

export function CommandPalette({
  open,
  onClose,
  sidebarCollapsed,
  onToggleSidebar,
  /** True when the breakpoint forces the rail: the toggle is disabled there,
   * so the palette omits the entry rather than offering a dead command. */
  sidebarLockedByViewport,
}: {
  open: boolean;
  onClose: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  sidebarLockedByViewport: boolean;
}): JSX.Element | null {
  const navigate = useNavigate();
  const user = currentUser();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);

  // Same query keys as Sidebar / ChangesetList: one shared cache entry.
  const { data: tables } = useQuery({
    queryKey: ["tables", user],
    queryFn: api.listTables,
  });
  const { data: changesets } = useQuery({
    queryKey: ["changesets"],
    queryFn: api.listChangesets,
  });

  const items = useMemo<PaletteItem[]>(() => {
    const go = (to: string) => () => {
      onClose();
      void navigate(to);
    };
    const tableItems: PaletteItem[] = (tables ?? []).map((t) => ({
      id: `table:${t.path}`,
      group: "Tables",
      label: t.table,
      secondary: `${t.backend}${t.schema_name ? ` / ${t.schema_name}` : ""}`,
      icon: t.actions.submit ? "pencil" : "eye",
      iconTitle: t.actions.submit
        ? "you can raise changesets here"
        : "read-only for you",
      run: go(tableRoute(t)),
    }));
    const changesetItems: PaletteItem[] = (changesets ?? []).map((cs) => ({
      id: `changeset:${cs.id}`,
      group: "Changesets",
      label: cs.title,
      secondary: `${cs.table} · rev ${cs.revision} · ${cs.maker}`,
      badge: <StateBadge state={cs.state} />,
      run: go(`/changesets/${cs.id}`),
    }));
    const actionItems: PaletteItem[] = [
      {
        id: "action:queue",
        group: "Actions",
        label: "Go to Queue",
        secondary: "changesets awaiting review",
        icon: "sidebar",
        run: go("/"),
      },
      {
        id: "action:new-changeset",
        group: "Actions",
        label: "New changeset",
        secondary: "draft change items by hand",
        icon: "plus",
        run: go("/tables/new"),
      },
      ...(sidebarLockedByViewport
        ? []
        : [
            {
              id: "action:toggle-sidebar",
              group: "Actions" as const,
              label: sidebarCollapsed
                ? "Expand navigation"
                : "Collapse navigation",
              secondary: "sidebar width preference",
              icon: (sidebarCollapsed
                ? "chevron-right"
                : "chevron-left") as IconName,
              run: () => {
                onClose();
                onToggleSidebar();
              },
            },
          ]),
    ];
    return [...tableItems, ...changesetItems, ...actionItems];
  }, [
    tables,
    changesets,
    navigate,
    onClose,
    sidebarCollapsed,
    onToggleSidebar,
    sidebarLockedByViewport,
  ]);

  const needle = query.trim().toLowerCase();
  /** Per group: ranked, capped, plus how many were cut so the cap is visible. */
  const groups = useMemo(() => {
    return GROUPS.map((group) => {
      const ranked = items
        .filter((item) => item.group === group)
        .map((item) => ({ item, score: rank(item, needle) }))
        .filter(({ score }) => score >= 0)
        .sort(
          (a, b) =>
            a.score - b.score || a.item.label.localeCompare(b.item.label),
        )
        .map(({ item }) => item);
      return {
        group,
        items: ranked.slice(0, PER_GROUP),
        hidden: Math.max(0, ranked.length - PER_GROUP),
      };
    }).filter(({ items: found }) => found.length > 0);
  }, [items, needle]);
  const visible = useMemo(
    () => groups.flatMap(({ items: found }) => found),
    [groups],
  );

  // Reset when reopened, and keep the selection in range as results change.
  useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      inputRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    setSelected((current) => Math.min(current, Math.max(0, visible.length - 1)));
  }, [visible.length]);

  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>("[data-selected='true']")
      ?.scrollIntoView({ block: "nearest" });
  }, [selected, visible.length]);

  if (!open) return null;

  const activate = (index: number) => {
    visible[index]?.run();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case "Escape":
        event.preventDefault();
        onClose();
        break;
      case "ArrowDown":
        event.preventDefault();
        setSelected((i) => (visible.length ? (i + 1) % visible.length : 0));
        break;
      case "ArrowUp":
        event.preventDefault();
        setSelected((i) =>
          visible.length ? (i - 1 + visible.length) % visible.length : 0,
        );
        break;
      case "Home":
        event.preventDefault();
        setSelected(0);
        break;
      case "End":
        event.preventDefault();
        setSelected(Math.max(0, visible.length - 1));
        break;
      case "Enter":
        event.preventDefault();
        activate(selected);
        break;
      case "Tab":
        // Focus stays in the input: the list is driven by arrow keys.
        event.preventDefault();
        break;
      default:
        break;
    }
  };

  const selectedItem = visible[selected];
  let flatIndex = -1;

  return (
    <div
      className="palette-scrim"
      onMouseDown={onClose}
      role="presentation"
      onKeyDown={onKeyDown}
    >
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Search bizkit"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="palette-search">
          <Icon name="search" size={18} className="muted" />
          <input
            ref={inputRef}
            className="palette-input"
            type="text"
            role="combobox"
            aria-expanded
            aria-controls="palette-results"
            aria-activedescendant={
              selectedItem ? `palette-item-${selectedItem.id}` : undefined
            }
            aria-autocomplete="list"
            placeholder="Search tables, changesets, actions…"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setSelected(0);
            }}
          />
          <button type="button" className="icon-button" onClick={onClose}>
            <Icon name="close" size={16} title="Close search" />
          </button>
        </div>
        {visible.length === 0 ? (
          <p className="palette-empty muted">
            Nothing matches “{query.trim()}” — try a table name, a changeset
            title, or “queue”.
          </p>
        ) : (
          <ul className="palette-results" id="palette-results" role="listbox">
            {groups.map(({ group, items: found, hidden }) => (
              <Fragment key={group}>
                <li className="palette-group" role="presentation">
                  {group}
                </li>
                {found.map((item) => {
                  flatIndex += 1;
                  const index = flatIndex;
                  return (
                    <li role="presentation" key={item.id}>
                      <button
                        type="button"
                        id={`palette-item-${item.id}`}
                        className="palette-item"
                        role="option"
                        aria-selected={index === selected}
                        data-selected={index === selected}
                        tabIndex={-1}
                        onMouseMove={() => setSelected(index)}
                        onClick={() => activate(index)}
                      >
                        {item.icon && (
                          <Icon
                            name={item.icon}
                            size={16}
                            className="muted"
                            title={item.iconTitle}
                          />
                        )}
                        <span className="palette-label">{item.label}</span>
                        {item.badge}
                        {item.secondary && (
                          <span className="palette-secondary muted">
                            {item.secondary}
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
                {hidden > 0 && (
                  <li className="palette-more muted" role="presentation">
                    +{hidden} more — keep typing
                  </li>
                )}
              </Fragment>
            ))}
          </ul>
        )}
        <p className="palette-hint muted">
          <kbd>Up</kbd>/<kbd>Down</kbd> to move · <kbd>Enter</kbd> to open ·{" "}
          <kbd>Esc</kbd> to close
        </p>
      </div>
    </div>
  );
}
