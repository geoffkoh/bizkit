// Client route builders. One place, so the sidebar tree, the command palette
// and the changeset detail page can never disagree about a table's URL.

import type { TableOut } from "./types";

/** `/t/:backend/:schema/:table` — a null schema travels as `-`. */
export function tableRoute(t: TableOut): string {
  return `/t/${encodeURIComponent(t.backend)}/${encodeURIComponent(
    t.schema_name ?? "-",
  )}/${encodeURIComponent(t.table)}`;
}

/** Same route from the API's `backend/schema/table` path string. */
export function tableRouteFromPath(path: string): string {
  const [backend = "", schema = "", table = ""] = path.split("/");
  return `/t/${encodeURIComponent(backend)}/${encodeURIComponent(
    schema || "-",
  )}/${encodeURIComponent(table)}`;
}
