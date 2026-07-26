/** The Apply action on the changeset detail page (spec §5, D12).
 *
 * Apply is the one irreversible step in the workflow, so the surface has three
 * obligations: it appears only for a principal the server says holds `apply`
 * (fail-closed per D25), it takes two clicks, and when the target refuses — a
 * 200 with `ok: false` — the reason is rendered rather than swallowed.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ApplyResultOut,
  ChangesetDetailOut,
  ChangesetState,
  TableOut,
} from "../types";

vi.mock("../api", () => ({
  currentUser: () => "bob",
  tableUrlPart: (backend: string, schema: string | null) =>
    `${backend}/${schema || "-"}`,
  ApiError: class extends Error {},
  api: {
    getChangeset: vi.fn(),
    listTables: vi.fn(),
    listComments: vi.fn(),
    listDecisions: vi.fn(),
    listAudit: vi.fn(),
    apply: vi.fn(),
    rework: vi.fn(),
    addComment: vi.fn(),
  },
}));

const { api } = await import("../api");
const { ChangesetDetail } = await import("./ChangesetDetail");

function tableOut(canApply: boolean): TableOut {
  return {
    backend: "sample",
    schema_name: null,
    table: "fx_rates",
    path: "sample//fx_rates",
    rule_count: 1,
    review_ttl_seconds: null,
    apply_ttl_seconds: null,
    allow_self_approval: false,
    max_changeset_items: 10000,
    rules: [],
    actions: {
      submit: false,
      approve: canApply,
      reject: canApply,
      apply: canApply,
      comment: true,
      view: true,
    },
  };
}

function changeset(state: ChangesetState): ChangesetDetailOut {
  return {
    id: "cs1",
    table: "sample//fx_rates",
    maker: "alice",
    title: "Add JPY rate",
    description: "",
    state,
    revision: 1,
    item_count: 1,
    review_deadline: null,
    apply_deadline: null,
    created_at: "2026-07-26T00:00:00Z",
    updated_at: "2026-07-26T00:00:00Z",
    items: [{ op: "insert", key: null, values: { pair: "USDJPY", rate: 155.2 } }],
  };
}

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/changesets/cs1"]}>
        <Routes>
          <Route path="/changesets/:id" element={<ChangesetDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function applyButton() {
  return screen.queryByRole("button", { name: /^apply to target$/i });
}

describe("ChangesetDetail apply action", () => {
  beforeEach(() => {
    vi.mocked(api.listComments).mockResolvedValue([]);
    vi.mocked(api.listDecisions).mockResolvedValue([]);
    vi.mocked(api.listAudit).mockResolvedValue([]);
    vi.mocked(api.listTables).mockResolvedValue([tableOut(true)]);
    vi.mocked(api.getChangeset).mockResolvedValue(changeset("approved"));
  });

  it("offers Apply on an approved changeset to a principal holding the right", async () => {
    renderDetail();
    expect(await screen.findByRole("button", { name: /apply to target/i })).toBeInTheDocument();
  });

  it("hides Apply when the server reports no apply right", async () => {
    vi.mocked(api.listTables).mockResolvedValue([tableOut(false)]);
    renderDetail();

    await screen.findByRole("heading", { name: /^actions$/i });
    await waitFor(() => expect(applyButton()).toBeNull());
  });

  it("fails closed while the tables query is unresolved", async () => {
    // An unresolved affordance must not read as "allowed" (D25).
    vi.mocked(api.listTables).mockReturnValue(new Promise(() => {}));
    renderDetail();

    await screen.findByRole("heading", { name: /^actions$/i });
    expect(applyButton()).toBeNull();
  });

  it.each<ChangesetState>(["draft", "submitted", "rejected", "applied", "withdrawn"])(
    "does not offer Apply in state %s",
    async (state) => {
      vi.mocked(api.getChangeset).mockResolvedValue(changeset(state));
      renderDetail();

      await screen.findByRole("heading", { name: /^actions$/i });
      await waitFor(() => expect(applyButton()).toBeNull());
    },
  );

  it("requires a confirmation naming the table before calling the API", async () => {
    const user = userEvent.setup();
    renderDetail();

    await user.click(await screen.findByRole("button", { name: /apply to target/i }));

    // First click only arms it — nothing has been written.
    expect(api.apply).not.toHaveBeenCalled();
    expect(screen.getByText(/writes to the target database/i)).toBeInTheDocument();
    expect(screen.getAllByText("sample//fx_rates").length).toBeGreaterThan(0);

    vi.mocked(api.apply).mockResolvedValue({
      ok: true,
      changeset: changeset("applied"),
      report: null,
      error: null,
    });
    await user.click(screen.getByRole("button", { name: /yes, apply/i }));

    await waitFor(() => expect(api.apply).toHaveBeenCalledWith("cs1"));
  });

  it("can be cancelled without calling the API", async () => {
    const user = userEvent.setup();
    renderDetail();

    await user.click(await screen.findByRole("button", { name: /apply to target/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(api.apply).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: /apply to target/i })).toBeInTheDocument();
  });

  it("renders the target's reason when apply comes back not-ok", async () => {
    const user = userEvent.setup();
    const failure: ApplyResultOut = {
      ok: false,
      changeset: changeset("failed"),
      report: null,
      error: "UNIQUE constraint failed: fx_rates.pair",
    };
    vi.mocked(api.apply).mockResolvedValue(failure);
    renderDetail();

    await user.click(await screen.findByRole("button", { name: /apply to target/i }));
    await user.click(screen.getByRole("button", { name: /yes, apply/i }));

    expect(await screen.findByText(/UNIQUE constraint failed/)).toBeInTheDocument();
    expect(screen.getByText(/all-or-nothing/i)).toBeInTheDocument();
  });

  it("lists pre-apply validation issues when validation blocked the write", async () => {
    const user = userEvent.setup();
    vi.mocked(api.apply).mockResolvedValue({
      ok: false,
      changeset: changeset("failed"),
      report: {
        ok: false,
        issues: [
          {
            rule_id: "rate-positive",
            table: "fx_rates",
            row_key: null,
            column: "rate",
            severity: "error",
            message: "'rate' value -1 is below the minimum 0",
          },
        ],
      },
      error: null,
    });
    renderDetail();

    await user.click(await screen.findByRole("button", { name: /apply to target/i }));
    await user.click(screen.getByRole("button", { name: /yes, apply/i }));

    expect(await screen.findByText(/rate-positive/)).toBeInTheDocument();
    expect(screen.getByText(/below the minimum/)).toBeInTheDocument();
    // The copy has to explain why this can differ from the submit-time report.
    expect(
      screen.getByText(/may have changed since\s+approval/i),
    ).toBeInTheDocument();
  });

  it("offers Retry apply on a failed changeset", async () => {
    vi.mocked(api.getChangeset).mockResolvedValue(changeset("failed"));
    renderDetail();

    expect(
      await screen.findByRole("button", { name: /retry apply/i }),
    ).toBeInTheDocument();
  });
});
