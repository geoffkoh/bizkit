// Mirrors src/bizkit/api/schemas.py — keep the two in sync.

export type ChangesetState =
  | "draft"
  | "submitted"
  | "approved"
  | "rejected"
  | "applied"
  | "failed"
  | "withdrawn"
  | "expired";

export type ChangeOp = "insert" | "update" | "delete";

export interface ChangeItemOut {
  op: ChangeOp;
  key: Record<string, unknown> | null;
  values: Record<string, unknown> | null;
}

export interface ChangesetOut {
  id: string;
  table: string;
  maker: string;
  title: string;
  state: ChangesetState;
  revision: number;
  item_count: number;
  review_deadline: string | null;
  apply_deadline: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChangesetDetailOut extends ChangesetOut {
  description: string;
  items: ChangeItemOut[];
}

export interface TableActionsOut {
  submit: boolean;
  approve: boolean;
  reject: boolean;
  comment: boolean;
  view: boolean;
}

export interface RuleOut {
  rule_id: string;
  kind: "type" | "constraint" | "cross_field" | "cross_table";
  description: string;
  column: string | null;
  params: Record<string, unknown>;
}

export interface TableOut {
  backend: string;
  schema_name: string | null;
  table: string;
  path: string;
  rule_count: number;
  review_ttl_seconds: number | null;
  apply_ttl_seconds: number | null;
  allow_self_approval: boolean;
  max_changeset_items: number;
  rules: RuleOut[];
  actions: TableActionsOut;
}

export interface ColumnOut {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
}

export type Row = Record<string, unknown>;

export interface RowsOut {
  rows: Row[];
  total: number;
  page: number;
  page_size: number;
}

export interface CommentOut {
  id: string;
  changeset_id: string;
  author: string;
  body: string;
  parent_id: string | null;
  created_at: string;
}

export interface DecisionOut {
  revision: number;
  checker: string;
  decision: "approve" | "reject";
  reason: string;
  decided_at: string;
  self_approved: boolean;
}

export interface AuditEventOut {
  actor: string;
  action: string;
  from_state: string | null;
  to_state: string | null;
  detail: string;
  at: string;
}

export interface ReadyOut {
  status: string;
  store: boolean;
  config_fingerprint: string | null;
}

/** Authentication modes from spec D42. */
export type AuthProviderName = "none" | "oidc" | "ldap" | "token";

/**
 * `GET /api/v1/me`.
 *
 * The server's `MeOut` currently carries only `user` — the D42 `auth/` module
 * (and with it `auth.provider`) is not built yet. `auth` is therefore
 * optional, and an absent value means the dev `none` provider: the moment the
 * backend starts reporting a provider, the UI switches to the read-only
 * identity display with no frontend change (D42, UI_SPECIFICATION.md §3).
 */
export interface MeOut {
  user: string;
  auth?: { provider: AuthProviderName } | null;
}

export interface ChangeItemIn {
  op: ChangeOp;
  key: Record<string, unknown> | null;
  values: Record<string, unknown> | null;
}

export interface ImportIssueOut {
  row: number;
  column: string | null;
  message: string;
}

export interface ImportReportOut {
  ok: boolean;
  items_added: number;
  issues: ImportIssueOut[];
}

export interface CreateChangesetIn {
  backend: string;
  schema_name: string | null;
  table: string;
  title: string;
  description: string;
  items: ChangeItemIn[];
  submit_now: boolean;
}
