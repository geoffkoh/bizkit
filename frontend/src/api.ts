// Typed API client. All server access goes through here — no ad-hoc
// fetch calls in components (frontend-engineer agent rule).
//
// Identity is a DEV convenience: the SPA sends X-Bizkit-User and the
// server's dev middleware trusts it. Roles shown in the UI are
// affordances only — enforcement always happens server-side (D25).

import type {
  AuditEventOut,
  ChangesetDetailOut,
  ChangesetOut,
  ColumnOut,
  CommentOut,
  CreateChangesetIn,
  DecisionOut,
  ImportReportOut,
  MeOut,
  ReadyOut,
  RowsOut,
  TableOut,
} from "./types";

export function tableUrlPart(backend: string, schema: string | null): string {
  return `${encodeURIComponent(backend)}/${encodeURIComponent(schema || "-")}`;
}

const USER_KEY = "bizkit.user";

export function currentUser(): string {
  return localStorage.getItem(USER_KEY) ?? "alice";
}

export function setCurrentUser(user: string): void {
  localStorage.setItem(USER_KEY, user);
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init?: { method?: string; body?: unknown },
): Promise<T> {
  const response = await fetch(path, {
    method: init?.method ?? "GET",
    headers: {
      "X-Bizkit-User": currentUser(),
      ...(init?.body !== undefined
        ? { "Content-Type": "application/json" }
        : {}),
    },
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const api = {
  ready: () => request<ReadyOut>("/api/ready"),
  /** The caller's identity, display-only (D42). Never a token store. */
  me: () => request<MeOut>("/api/v1/me"),
  listTables: () => request<TableOut[]>("/api/v1/tables"),
  listColumns: (backend: string, schema: string | null, table: string) =>
    request<ColumnOut[]>(
      `/api/v1/tables/${tableUrlPart(backend, schema)}/${encodeURIComponent(table)}/columns`,
    ),
  listRows: (
    backend: string,
    schema: string | null,
    table: string,
    page = 1,
    pageSize = 500,
    q = "",
    sort = "",
    direction: "asc" | "desc" = "asc",
  ) =>
    // At config-table scale (≤500 rows) the grid fetches once and does
    // search/sort/paging client-side; larger tables switch to manual
    // server paging with server-side q/sort (UI_SPECIFICATION.md §4.1).
    request<RowsOut>(
      `/api/v1/tables/${tableUrlPart(backend, schema)}/${encodeURIComponent(table)}/rows` +
        `?page=${page}&page_size=${pageSize}&q=${encodeURIComponent(q)}` +
        `&sort=${encodeURIComponent(sort)}&direction=${direction}`,
    ),
  listChangesets: () => request<ChangesetOut[]>("/api/v1/changesets"),
  getChangeset: (id: string) =>
    request<ChangesetDetailOut>(`/api/v1/changesets/${id}`),
  createChangeset: (body: CreateChangesetIn) =>
    request<ChangesetDetailOut>("/api/v1/changesets", {
      method: "POST",
      body,
    }),
  submit: (id: string) =>
    request<ChangesetDetailOut>(`/api/v1/changesets/${id}/submit`, {
      method: "POST",
    }),
  approve: (id: string, reason: string) =>
    request<ChangesetDetailOut>(`/api/v1/changesets/${id}/approve`, {
      method: "POST",
      body: { reason },
    }),
  reject: (id: string, reason: string) =>
    request<ChangesetDetailOut>(`/api/v1/changesets/${id}/reject`, {
      method: "POST",
      body: { reason },
    }),
  rework: (id: string) =>
    request<ChangesetDetailOut>(`/api/v1/changesets/${id}/rework`, {
      method: "POST",
    }),
  withdraw: (id: string) =>
    request<ChangesetDetailOut>(`/api/v1/changesets/${id}/withdraw`, {
      method: "POST",
    }),
  importCsv: async (
    id: string,
    filename: string,
    mode: "append" | "diff",
    csvText: string,
  ): Promise<ImportReportOut> => {
    const response = await fetch(
      `/api/v1/changesets/${id}/items/import?mode=${mode}&filename=${encodeURIComponent(filename)}`,
      {
        method: "POST",
        headers: {
          "X-Bizkit-User": currentUser(),
          "Content-Type": "text/csv",
        },
        body: csvText,
      },
    );
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) detail = body.detail;
      } catch {
        // keep statusText
      }
      throw new ApiError(response.status, detail);
    }
    return (await response.json()) as ImportReportOut;
  },
  listComments: (id: string) =>
    request<CommentOut[]>(`/api/v1/changesets/${id}/comments`),
  addComment: (id: string, body: string, parentId: string | null) =>
    request<CommentOut>(`/api/v1/changesets/${id}/comments`, {
      method: "POST",
      body: { body, parent_id: parentId },
    }),
  listDecisions: (id: string) =>
    request<DecisionOut[]>(`/api/v1/changesets/${id}/decisions`),
  listAudit: (id: string) =>
    request<AuditEventOut[]>(`/api/v1/changesets/${id}/audit`),
};
