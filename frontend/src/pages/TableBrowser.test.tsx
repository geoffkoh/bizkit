/** The draft basket is scoped to exactly one table (UI_SPECIFICATION.md §4.1).
 *
 * Regression cover for the defect these tests were written against: React Router
 * reuses `TableBrowser` when only the `:table` param changes, so a basket left
 * in component state survived the switch and `ReviewSlideOver` filed it against
 * whichever table was on screen — silently misattributing rows to a table whose
 * schema they don't match. A changeset targets a single `TableRef`
 * (SPECIFICATION.md §3.1), so that must be unreachable, not merely discouraged.
 *
 * Navigation goes through `MemoryRouter` and real links rather than a data
 * router: `router.navigate()` builds a `Request` whose `AbortSignal` jsdom does
 * not satisfy, and clicking a link is what the sidebar actually does anyway.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ColumnOut, RowsOut, TableOut } from "../types";

vi.mock("../api", () => ({
  currentUser: () => "alice",
  tableUrlPart: (backend: string, schema: string | null) =>
    `${backend}/${schema || "-"}`,
  ApiError: class extends Error {},
  api: {
    listTables: vi.fn(),
    listColumns: vi.fn(),
    listRows: vi.fn(),
    listChangesets: vi.fn(),
    createChangeset: vi.fn(),
  },
}));

// Imported after the mock so the component binds to the mocked module.
const { api } = await import("../api");
const { TableBrowser } = await import("./TableBrowser");

function tableOut(name: string): TableOut {
  return {
    backend: "sample",
    schema_name: null,
    table: name,
    path: `sample//${name}`,
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
}

const COLUMNS: Record<string, ColumnOut[]> = {
  fx_rates: [
    { name: "pair", type: "string", nullable: false, primary_key: true },
    { name: "rate", type: "decimal", nullable: false, primary_key: false },
  ],
  holidays: [
    { name: "market", type: "string", nullable: false, primary_key: true },
    { name: "day", type: "string", nullable: false, primary_key: false },
  ],
};

const ROWS: Record<string, RowsOut> = {
  fx_rates: {
    rows: [{ pair: "EURUSD", rate: 1.08 }],
    total: 1,
    page: 1,
    page_size: 500,
  },
  holidays: {
    rows: [{ market: "SG", day: "2027-01-01" }],
    total: 1,
    page: 1,
    page_size: 500,
  },
};

function Pathname() {
  return <span data-testid="pathname">{useLocation().pathname}</span>;
}

function renderAt(table: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/t/sample/-/${table}`]}>
        <Pathname />
        <nav>
          <Link to="/t/sample/-/fx_rates">nav-fx_rates</Link>
          <Link to="/t/sample/-/holidays">nav-holidays</Link>
        </nav>
        <Routes>
          <Route path="/t/:backend/:schema/:table" element={<TableBrowser />} />
          {/* Saving a draft navigates here; stubbed so the router stays quiet. */}
          <Route path="/changesets/:id" element={<span>changeset</span>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

type User = ReturnType<typeof userEvent.setup>;

/** Draft one insert via "+ Add row", leaving it in the basket. */
async function addRow(user: User, table: string) {
  await user.click(await screen.findByRole("button", { name: /add row/i }));
  const [pk, other] = COLUMNS[table];
  await user.type(screen.getByLabelText(pk.name), "XXXYYY");
  await user.type(screen.getByLabelText(other.name), "1.5");
  await user.click(screen.getByRole("button", { name: /^add$/i }));
}

async function switchTo(user: User, table: string) {
  await user.click(screen.getByRole("link", { name: `nav-${table}` }));
}

function basketBar(): HTMLElement | null {
  return screen.queryByText(/^Draft: \d+ change/);
}

function pathname(): string {
  return screen.getByTestId("pathname").textContent ?? "";
}

describe("TableBrowser draft basket scoping", () => {
  beforeEach(() => {
    vi.mocked(api.listTables).mockResolvedValue([
      tableOut("fx_rates"),
      tableOut("holidays"),
    ]);
    vi.mocked(api.listChangesets).mockResolvedValue([]);
    vi.mocked(api.listColumns).mockImplementation((_b, _s, table) =>
      Promise.resolve(COLUMNS[table]),
    );
    vi.mocked(api.listRows).mockImplementation((_b, _s, table) =>
      Promise.resolve(ROWS[table]),
    );
  });

  it("shows the basket bar for a draft on its own table", async () => {
    const user = userEvent.setup();
    renderAt("fx_rates");
    await addRow(user, "fx_rates");

    expect(basketBar()).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /review & submit/i }),
    ).toBeInTheDocument();
  });

  it("prompts instead of carrying the draft to another table", async () => {
    const user = userEvent.setup();
    renderAt("fx_rates");
    await addRow(user, "fx_rates");

    await switchTo(user, "holidays");

    // The prompt names the basket's table, not the one now on screen.
    expect(
      await screen.findByText(/unsaved draft on another table/i),
    ).toBeInTheDocument();
    expect(screen.getByText("sample//fx_rates")).toBeInTheDocument();

    // The route through which misattribution happened is simply not rendered.
    expect(basketBar()).toBeNull();
    expect(
      screen.queryByRole("button", { name: /review & submit/i }),
    ).toBeNull();
    expect(api.createChangeset).not.toHaveBeenCalled();
  });

  it("returns to the draft's own table on Keep draft", async () => {
    const user = userEvent.setup();
    renderAt("fx_rates");
    await addRow(user, "fx_rates");
    await switchTo(user, "holidays");

    await user.click(
      await screen.findByRole("button", { name: /keep draft/i }),
    );

    await waitFor(() => expect(pathname()).toBe("/t/sample/-/fx_rates"));
    // Draft survived the round trip and is actionable again.
    expect(basketBar()).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /review & submit/i }),
    ).toBeInTheDocument();
  });

  it("drops the draft on Discard and adopts the new table", async () => {
    const user = userEvent.setup();
    renderAt("fx_rates");
    await addRow(user, "fx_rates");
    await switchTo(user, "holidays");

    await user.click(await screen.findByRole("button", { name: /^discard/i }));

    await waitFor(() =>
      expect(screen.queryByText(/unsaved draft on another table/i)).toBeNull(),
    );
    expect(basketBar()).toBeNull();
    expect(pathname()).toBe("/t/sample/-/holidays");
  });

  it("files a later draft against the table it was actually drafted on", async () => {
    const user = userEvent.setup();
    vi.mocked(api.createChangeset).mockResolvedValue({
      id: "cs-new",
      table: "sample//holidays",
      maker: "alice",
      title: "Holiday tweak",
      description: "",
      state: "draft",
      revision: 0,
      item_count: 1,
      review_deadline: null,
      apply_deadline: null,
      created_at: "2026-07-26T00:00:00Z",
      updated_at: "2026-07-26T00:00:00Z",
      items: [],
    });
    renderAt("fx_rates");
    await addRow(user, "fx_rates");
    await switchTo(user, "holidays");
    await user.click(await screen.findByRole("button", { name: /^discard/i }));

    // Draft afresh on holidays and take it through review.
    await addRow(user, "holidays");
    await user.click(screen.getByRole("button", { name: /review & submit/i }));
    await user.type(
      screen.getByPlaceholderText(/what is changing/i),
      "Holiday tweak",
    );
    await user.click(screen.getByRole("button", { name: /^save draft$/i }));

    await waitFor(() => expect(api.createChangeset).toHaveBeenCalled());
    const body = vi.mocked(api.createChangeset).mock.calls[0][0];
    expect(body.table).toBe("holidays");
    expect(body.items).toHaveLength(1);
    // The decisive assertion: no fx_rates column rides along.
    expect(Object.keys(body.items[0].values ?? {})).toEqual(["market", "day"]);
  });
});
