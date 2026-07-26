import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type JSX,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type RefObject,
} from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api, currentUser, setCurrentUser } from "./api";
import { CommandPalette } from "./components/CommandPalette";
import { ErrorBannerHost } from "./components/ErrorBanner";
import { Icon, IconSprite } from "./components/Icon";
import { Sidebar } from "./components/Sidebar";
import { ToastHost } from "./components/Toast";
import { Tooltip } from "./components/Tooltip";
import { ChangesetDetail } from "./pages/ChangesetDetail";
import { ChangesetList } from "./pages/ChangesetList";
import { NewChangeset } from "./pages/NewChangeset";
import { TableBrowser } from "./pages/TableBrowser";

const MIN_SIDEBAR = 170;
const MAX_SIDEBAR = 420;
const DEFAULT_SIDEBAR = 240;
/** Keyboard resize step for the sidebar separator. */
const SIDEBAR_NUDGE = 16;
/** Mirrors the `--sidebar-collapsed` token; needed numerically for ARIA. */
const SIDEBAR_COLLAPSED = 64;
/** §3: below this width the sidebar auto-collapses to the icon rail. */
const NARROW_VIEWPORT = "(max-width: 900px)";

const COLLAPSE_KEY = "bizkit.sidebar";
const WIDTH_KEY = "bizkit.sidebar.width";

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => window.matchMedia(query).matches,
  );
  useEffect(() => {
    const mql = window.matchMedia(query);
    setMatches(mql.matches);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

function clampWidth(value: number): number {
  return Math.min(MAX_SIDEBAR, Math.max(MIN_SIDEBAR, Math.round(value)));
}

function ReadyBadge(): JSX.Element {
  const { data } = useQuery({ queryKey: ["ready"], queryFn: api.ready });
  if (!data) return <span className="ready unknown">connecting…</span>;
  return (
    <Tooltip
      content={
        data.config_fingerprint
          ? `Workspace config sha256:${data.config_fingerprint.slice(0, 12)}…`
          : "No workspace config loaded"
      }
      focusable
    >
      <span className={`ready ${data.store ? "ok" : "bad"}`}>{data.status}</span>
    </Tooltip>
  );
}

/** Dev-only, editable identity — rendered ONLY under `auth.provider: none`
 * (spec D42). Every other provider gets the read-only display below. */
function UserPicker(): JSX.Element {
  const queryClient = useQueryClient();
  const switchTo = (user: string) => {
    setCurrentUser(user);
    void queryClient.invalidateQueries();
  };
  return (
    <span className="user-picker">
      <Tooltip
        content="Dev identity only (auth.provider: none) — sent as the X-Bizkit-User header. Roles are affordances; the server still enforces."
        focusable
      >
        <span>acting as</span>
      </Tooltip>
      <input
        defaultValue={currentUser()}
        aria-label="Acting-as user (dev only)"
        onBlur={(e) => switchTo(e.target.value.trim() || "anonymous")}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
      />
      {["alice", "bob", "carol", "dave"].map((name) => (
        <button
          key={name}
          type="button"
          className="chip"
          onClick={(e) => {
            const input = e.currentTarget.parentElement?.querySelector("input");
            if (input) input.value = name;
            switchTo(name);
          }}
        >
          {name}
        </button>
      ))}
    </span>
  );
}

/** Read-only identity: what the server asserts. No client-editable control,
 * and the SPA never holds a token for oidc/ldap sessions (D42). */
function IdentityDisplay({
  user,
  provider,
}: {
  user: string;
  provider: string;
}): JSX.Element {
  return (
    <Tooltip content={`Signed in via ${provider} — identity is server-asserted`} focusable>
      <span className="identity">
        <Icon name="user" size={16} className="muted" />
        <span>{user}</span>
      </span>
    </Tooltip>
  );
}

function Identity(): JSX.Element {
  const { data } = useQuery({ queryKey: ["me"], queryFn: api.me });
  // No `auth` block yet (the D42 module isn't built) — that is today's dev
  // posture, i.e. provider `none`. This gate flips on its own the day the
  // server starts reporting a provider; no frontend change needed.
  const provider = data?.auth?.provider ?? "none";
  if (provider === "none") return <UserPicker />;
  return <IdentityDisplay user={data?.user ?? "…"} provider={provider} />;
}

function PaletteTrigger({
  onOpen,
  open,
  triggerRef,
}: {
  onOpen: () => void;
  open: boolean;
  triggerRef: RefObject<HTMLButtonElement | null>;
}): JSX.Element {
  const isMac = /mac|iphone|ipad/i.test(navigator.userAgent);
  return (
    <button
      ref={triggerRef}
      type="button"
      className="palette-trigger"
      onClick={onOpen}
      aria-haspopup="dialog"
      aria-expanded={open}
    >
      <Icon name="search" size={16} className="muted" />
      <span className="palette-trigger-label">Search…</span>
      <kbd>{isMac ? "⌘K" : "Ctrl+K"}</kbd>
    </button>
  );
}

export function App(): JSX.Element {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === "collapsed",
  );
  const [width, setWidth] = useState(() => {
    const stored = Number(localStorage.getItem(WIDTH_KEY));
    return stored >= MIN_SIDEBAR && stored <= MAX_SIDEBAR
      ? stored
      : DEFAULT_SIDEBAR;
  });
  const [dragging, setDragging] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const paletteTriggerRef = useRef<HTMLButtonElement | null>(null);

  // §3: auto-collapse below 900px. Presentation only — the stored width and
  // collapse preferences survive for when the viewport grows back.
  const narrow = useMediaQuery(NARROW_VIEWPORT);
  const railed = collapsed || narrow;

  const toggle = () => {
    setCollapsed((current) => {
      localStorage.setItem(COLLAPSE_KEY, current ? "open" : "collapsed");
      return !current;
    });
  };

  const commitWidth = useCallback((next: number) => {
    const clamped = clampWidth(next);
    setWidth(clamped);
    localStorage.setItem(WIDTH_KEY, String(clamped));
  }, []);

  const startResize = (event: ReactMouseEvent) => {
    if (railed) return;
    event.preventDefault();
    setDragging(true);
    const onMove = (move: MouseEvent) => setWidth(clampWidth(move.clientX));
    const onUp = (up: MouseEvent) => {
      commitWidth(up.clientX);
      setDragging(false);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.classList.remove("resizing");
    };
    document.body.classList.add("resizing");
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const onSeparatorKeys = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (railed) return;
    switch (event.key) {
      case "ArrowLeft":
        event.preventDefault();
        commitWidth(width - SIDEBAR_NUDGE);
        break;
      case "ArrowRight":
        event.preventDefault();
        commitWidth(width + SIDEBAR_NUDGE);
        break;
      case "Home":
        event.preventDefault();
        commitWidth(MIN_SIDEBAR);
        break;
      case "End":
        event.preventDefault();
        commitWidth(MAX_SIDEBAR);
        break;
      default:
        break;
    }
  };

  const closePalette = useCallback(() => {
    setPaletteOpen(false);
    paletteTriggerRef.current?.focus();
  }, []);

  // ⌘K / Ctrl+K from anywhere — but not while typing in a field, and never
  // stacked on top of an open slide-over/modal (§3).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "k") return;
      if (!event.metaKey && !event.ctrlKey) return;
      if (paletteOpen) {
        event.preventDefault();
        closePalette();
        return;
      }
      const target = event.target as HTMLElement | null;
      const typing = target?.closest(
        "input, textarea, select, [contenteditable='true']",
      );
      const overlayOpen = document.querySelector(".slideover-backdrop");
      if (typing || overlayOpen) return;
      event.preventDefault();
      setPaletteOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen, closePalette]);

  return (
    <div
      className={`shell ${railed ? "collapsed" : ""}`}
      style={
        {
          "--sidebar-w": railed ? "var(--sidebar-collapsed)" : `${width}px`,
        } as CSSProperties
      }
    >
      {/* One inline SVG symbol set for the whole app (§2.1 Iconography). */}
      <IconSprite />
      {/* Global fetch-failure banner (§6) — queries only, dismissible. */}
      <ErrorBannerHost />
      <header>
        <NavLink to="/" className="brand">
          bizkit
        </NavLink>
        <PaletteTrigger
          onOpen={() => setPaletteOpen(true)}
          open={paletteOpen}
          triggerRef={paletteTriggerRef}
        />
        <span className="spacer" />
        <Identity />
        <ReadyBadge />
      </header>
      <div className="body">
        <Sidebar
          collapsed={railed}
          onToggle={toggle}
          toggleDisabledReason={
            narrow
              ? "The window is too narrow — navigation stays collapsed below 900px."
              : undefined
          }
        />
        <Tooltip
          className="resize-host"
          content={
            railed
              ? ""
              : "Drag, or focus and use Left/Right arrows, to resize navigation"
          }
        >
          <div
            className={`resize-handle ${dragging ? "dragging" : ""}`}
            role="separator"
            aria-orientation="vertical"
            aria-label="Navigation width"
            aria-valuenow={railed ? SIDEBAR_COLLAPSED : width}
            aria-valuemin={MIN_SIDEBAR}
            aria-valuemax={MAX_SIDEBAR}
            tabIndex={railed ? -1 : 0}
            onMouseDown={startResize}
            onKeyDown={onSeparatorKeys}
          />
        </Tooltip>
        <main>
          <Routes>
            <Route path="/" element={<ChangesetList />} />
            <Route
              path="/t/:backend/:schema/:table"
              element={<TableBrowser />}
            />
            <Route path="/tables/new" element={<NewChangeset />} />
            <Route path="/changesets/:id" element={<ChangesetDetail />} />
          </Routes>
        </main>
      </div>
      <CommandPalette
        open={paletteOpen}
        onClose={closePalette}
        sidebarCollapsed={collapsed}
        onToggleSidebar={toggle}
        sidebarLockedByViewport={narrow}
      />
      {/* The one toast stack (§6) — fed by showToast() from mutations. */}
      <ToastHost />
    </div>
  );
}
