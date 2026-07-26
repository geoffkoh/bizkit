import { describe, expect, it } from "vitest";
import { approveRightsByPath, awaitsMyReview } from "./queue";
import type { ChangesetOut, TableOut } from "./types";

function table(path: string, approve: boolean): TableOut {
  const [backend, schema, name] = path.split("/");
  return {
    backend,
    schema_name: schema === "" ? null : schema,
    table: name,
    path,
    rule_count: 0,
    review_ttl_seconds: null,
    apply_ttl_seconds: null,
    allow_self_approval: false,
    max_changeset_items: 10000,
    rules: [],
    actions: {
      submit: true,
      approve,
      reject: approve,
      apply: approve,
      comment: true,
      view: true,
    },
  };
}

function changeset(over: Partial<ChangesetOut> = {}): ChangesetOut {
  return {
    id: "cs1",
    table: "sample//fx_rates",
    maker: "alice",
    title: "Add JPY rate",
    state: "submitted",
    revision: 1,
    item_count: 1,
    review_deadline: null,
    apply_deadline: null,
    created_at: "2026-07-19T13:31:14Z",
    updated_at: "2026-07-19T13:31:14Z",
    ...over,
  };
}

describe("awaitsMyReview", () => {
  const rights = approveRightsByPath([table("sample//fx_rates", true)]);

  it("counts a submitted changeset from another maker I can approve", () => {
    expect(awaitsMyReview(changeset(), "bob", rights)).toBe(true);
  });

  it("excludes my own changeset — maker is never the checker", () => {
    expect(awaitsMyReview(changeset({ maker: "bob" }), "bob", rights)).toBe(
      false,
    );
  });

  it.each<ChangesetOut["state"]>([
    "draft",
    "approved",
    "rejected",
    "applied",
    "failed",
    "withdrawn",
    "expired",
  ])("excludes state %s — only submitted awaits review", (state) => {
    expect(awaitsMyReview(changeset({ state }), "bob", rights)).toBe(false);
  });

  it("excludes a table I hold no approve right on", () => {
    const noRight = approveRightsByPath([table("sample//fx_rates", false)]);
    expect(awaitsMyReview(changeset(), "bob", noRight)).toBe(false);
  });

  it("fails closed when the tables query has not resolved", () => {
    // The bug fixed in ccd92dd: an unresolved query must not read as "allowed".
    expect(awaitsMyReview(changeset(), "bob", approveRightsByPath(undefined))).toBe(
      false,
    );
  });

  it("fails closed for a table absent from my grants", () => {
    const otherTable = approveRightsByPath([table("sample//holidays", true)]);
    expect(awaitsMyReview(changeset(), "bob", otherTable)).toBe(false);
  });
});
