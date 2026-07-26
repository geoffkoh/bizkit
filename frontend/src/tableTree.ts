// Sidebar table tree shape (UI_SPECIFICATION.md §3): pure data transform,
// deliberately kept out of the component so the progressive-disclosure rule
// is testable in isolation.

import type { TreeNode } from "./components/Tree";
import { tableRoute } from "./routes";
import type { TableOut } from "./types";

/** Node ids are namespaced so a backend, a schema and a table never collide. */
export function backendNodeId(backend: string): string {
  return `be:${backend}`;
}

export function schemaNodeId(backend: string, schema: string | null): string {
  return `sc:${backend}/${schema ?? ""}`;
}

export function tableNodeId(path: string): string {
  return `tb:${path}`;
}

function byName(a: string, b: string): number {
  return a.localeCompare(b);
}

function tableLeaf(t: TableOut): TreeNode {
  return {
    id: tableNodeId(t.path),
    label: t.table,
    // Shown in the 64px rail, where the label (and the icon's own title) are
    // the only identity — so it carries the breadcrumb and the affordance (§3).
    hint: `${t.backend}${t.schema_name ? ` / ${t.schema_name}` : ""} / ${t.table} — ${
      t.actions.submit ? "you can raise changesets here" : "read-only for you"
    }`,
    to: tableRoute(t),
    icon: t.actions.submit ? "pencil" : "eye",
    iconTitle: t.actions.submit
      ? "you can raise changesets here"
      : "read-only for you",
  };
}

/**
 * Group tables into backend → schema → table.
 *
 * Progressive disclosure (§3): the schema level renders only when a backend
 * exposes more than one schema to this caller, so the common single-schema
 * case goes straight from backend to its table leaves. A caller who can see
 * just one table inside a normally-hidden schema still gets a single-item
 * schema node whenever that backend exposes more than one schema.
 */
export function buildTableTree(tables: readonly TableOut[]): TreeNode[] {
  const backends = new Map<string, TableOut[]>();
  for (const t of tables) {
    const group = backends.get(t.backend) ?? [];
    group.push(t);
    backends.set(t.backend, group);
  }

  const leaves = (list: readonly TableOut[]): TreeNode[] =>
    [...list].sort((a, b) => byName(a.table, b.table)).map(tableLeaf);

  return [...backends.entries()]
    .sort(([a], [b]) => byName(a, b))
    .map(([backend, group]): TreeNode => {
      const schemas = new Map<string, TableOut[]>();
      for (const t of group) {
        const key = t.schema_name ?? "";
        const bucket = schemas.get(key) ?? [];
        bucket.push(t);
        schemas.set(key, bucket);
      }

      const children: TreeNode[] =
        schemas.size > 1
          ? [...schemas.entries()]
              .sort(([a], [b]) => byName(a, b))
              .map(([schema, list]) => ({
                id: schemaNodeId(backend, schema || null),
                label: schema || "(default)",
                hint: `${backend} / ${schema || "(default)"}`,
                icon: "folder" as const,
                children: leaves(list),
              }))
          : leaves(group);

      return {
        id: backendNodeId(backend),
        label: backend,
        hint: backend,
        icon: "server",
        children,
      };
    });
}

/** Every branch node id, in render order — the "everything expanded" default. */
export function branchNodeIds(nodes: readonly TreeNode[]): string[] {
  return nodes.flatMap((node) =>
    node.children ? [node.id, ...branchNodeIds(node.children)] : [],
  );
}
