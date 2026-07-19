import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api, currentUser, setCurrentUser } from "./api";
import { Sidebar } from "./components/Sidebar";
import { ChangesetDetail } from "./pages/ChangesetDetail";
import { ChangesetList } from "./pages/ChangesetList";
import { NewChangeset } from "./pages/NewChangeset";
import { TableBrowser } from "./pages/TableBrowser";

function ReadyBadge() {
  const { data } = useQuery({ queryKey: ["ready"], queryFn: api.ready });
  if (!data) return <span className="ready unknown">connecting…</span>;
  return (
    <span
      className={`ready ${data.store ? "ok" : "bad"}`}
      title={
        data.config_fingerprint
          ? `config sha256:${data.config_fingerprint.slice(0, 12)}…`
          : "no workspace config loaded"
      }
    >
      {data.status}
    </span>
  );
}

function UserPicker() {
  const queryClient = useQueryClient();
  const switchTo = (user: string) => {
    setCurrentUser(user);
    void queryClient.invalidateQueries();
  };
  return (
    <span className="user-picker" title="Dev identity — sent as X-Bizkit-User">
      acting as
      <input
        defaultValue={currentUser()}
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

const MIN_SIDEBAR = 170;
const MAX_SIDEBAR = 420;

export function App() {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("bizkit.sidebar") === "collapsed",
  );
  const [width, setWidth] = useState(() => {
    const stored = Number(localStorage.getItem("bizkit.sidebar.width"));
    return stored >= MIN_SIDEBAR && stored <= MAX_SIDEBAR ? stored : 240;
  });
  const toggle = () => {
    setCollapsed((c) => {
      localStorage.setItem("bizkit.sidebar", c ? "open" : "collapsed");
      return !c;
    });
  };
  const startResize = (e: React.MouseEvent) => {
    if (collapsed) return;
    e.preventDefault();
    const onMove = (move: MouseEvent) => {
      const next = Math.min(MAX_SIDEBAR, Math.max(MIN_SIDEBAR, move.clientX));
      setWidth(next);
    };
    const onUp = (up: MouseEvent) => {
      const next = Math.min(MAX_SIDEBAR, Math.max(MIN_SIDEBAR, up.clientX));
      localStorage.setItem("bizkit.sidebar.width", String(next));
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.classList.remove("resizing");
    };
    document.body.classList.add("resizing");
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };
  return (
    <div
      className={`shell ${collapsed ? "collapsed" : ""}`}
      style={{ "--sidebar-w": `${collapsed ? 64 : width}px` } as React.CSSProperties}
    >
      <header>
        <NavLink to="/" className="brand">
          bizkit
        </NavLink>
        <span className="spacer" />
        <UserPicker />
        <ReadyBadge />
      </header>
      <div className="body">
        <Sidebar collapsed={collapsed} onToggle={toggle} />
        <div
          className="resize-handle"
          onMouseDown={startResize}
          title="Drag to resize navigation"
        />
        <main>
          <Routes>
            <Route path="/" element={<ChangesetList />} />
            <Route path="/t/:backend/:schema/:table" element={<TableBrowser />} />
            <Route path="/tables/new" element={<NewChangeset />} />
            <Route path="/changesets/:id" element={<ChangesetDetail />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
