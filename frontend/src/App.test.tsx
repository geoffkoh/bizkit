/** Shell smoke test — mounts `App` under the router production actually uses.
 *
 * The rest of the suite drives `MemoryRouter`, which is right for asserting
 * navigation behaviour but leaves `main.tsx`'s `BrowserRouter` untested. That
 * gap mattered when react-router went to v8 (the `react-router-dom` package
 * has no v8 line, so every import moved to `react-router`): a type-clean
 * migration could still fail at mount. This mounts the real composition —
 * BrowserRouter + QueryClientProvider + App — so a router major bump has to
 * survive an actual render, not just `tsc`.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeOut, TableOut } from "./types";

vi.mock("./api", () => ({
  currentUser: () => "alice",
  setCurrentUser: vi.fn(),
  tableUrlPart: (backend: string, schema: string | null) =>
    `${backend}/${schema || "-"}`,
  ApiError: class extends Error {},
  api: {
    me: vi.fn(),
    ready: vi.fn(),
    listTables: vi.fn(),
    listChangesets: vi.fn(),
  },
}));

const { api } = await import("./api");
const { App } = await import("./App");

const TABLE: TableOut = {
  backend: "sample",
  schema_name: null,
  table: "fx_rates",
  path: "sample//fx_rates",
  rule_count: 0,
  review_ttl_seconds: null,
  apply_ttl_seconds: null,
  allow_self_approval: false,
  max_changeset_items: 10000,
  rules: [],
  actions: {
    submit: true,
    approve: false,
    reject: false,
    apply: false,
    comment: true,
    view: true,
  },
};

describe("App shell under BrowserRouter", () => {
  beforeEach(() => {
    vi.mocked(api.me).mockResolvedValue({ user: "alice" } as MeOut);
    vi.mocked(api.ready).mockResolvedValue({
      status: "ready",
      store: true,
      config_fingerprint: "abc",
    });
    vi.mocked(api.listTables).mockResolvedValue([TABLE]);
    vi.mocked(api.listChangesets).mockResolvedValue([]);
  });

  it("mounts and renders the sidebar's table tree", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    render(
      <QueryClientProvider client={client}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>,
    );

    // The backend node comes from GET /api/v1/tables via the real router's
    // NavLink/Routes tree, so reaching it proves the shell composed.
    expect(await screen.findByText("sample")).toBeInTheDocument();
  });
});
