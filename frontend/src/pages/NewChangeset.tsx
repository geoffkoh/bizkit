import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type JSX } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, currentUser } from "../api";
import { Icon } from "../components/Icon";
import { showToast } from "../components/Toast";
import { describeError } from "../errors";
import type { ChangeItemIn, ChangeOp } from "../types";

interface ItemDraft {
  op: ChangeOp;
  key: string;
  values: string;
}

function parseItem(draft: ItemDraft, index: number): ChangeItemIn {
  const parse = (
    label: string,
    text: string,
  ): Record<string, unknown> | null => {
    const trimmed = text.trim();
    if (!trimmed) return null;
    try {
      const value = JSON.parse(trimmed) as unknown;
      if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new Error("expected a JSON object");
      }
      return value as Record<string, unknown>;
    } catch (e) {
      throw new Error(`Item ${index + 1} ${label}: ${String(e)}`);
    }
  };
  return {
    op: draft.op,
    key: parse("key", draft.key),
    values: parse("values", draft.values),
  };
}

function TablePicker(): JSX.Element {
  const user = currentUser();
  const { data: tables } = useQuery({
    queryKey: ["tables", user],
    queryFn: api.listTables,
  });
  const drafts = (tables ?? []).filter((t) => t.actions.submit);
  return (
    <>
      <h1>New changeset</h1>
      {drafts.length === 0 ? (
        <p className="muted">
          You cannot raise changesets on any table yet — ask for a maker grant
          on the table you need.
        </p>
      ) : (
        <>
          <p className="muted">Pick the table this change targets.</p>
          <ul className="plain-list">
            {drafts.map((t) => (
              <li key={t.path}>
                <Link
                  to={`/tables/new?backend=${encodeURIComponent(t.backend)}&schema=${encodeURIComponent(t.schema_name ?? "")}&table=${encodeURIComponent(t.table)}`}
                >
                  <code>{t.path}</code>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

export function NewChangeset(): JSX.Element {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const backend = params.get("backend") ?? "";
  const schema = params.get("schema") || null;
  const table = params.get("table") ?? "";

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [items, setItems] = useState<ItemDraft[]>([
    { op: "insert", key: "", values: "{}" },
  ]);
  const [formError, setFormError] = useState<string | null>(null);
  const hasTarget = backend !== "" && table !== "";

  const create = useMutation({
    mutationFn: (submitNow: boolean) =>
      api.createChangeset({
        backend,
        schema_name: schema,
        table,
        title,
        description,
        items: items.map(parseItem),
        submit_now: submitNow,
      }),
    onSuccess: (changeset) => {
      showToast(
        changeset.state === "submitted"
          ? `Submitted for review: \u201c${changeset.title}\u201d — ${changeset.item_count} change item(s) on ${changeset.table}`
          : `Draft saved: \u201c${changeset.title}\u201d — ${changeset.item_count} change item(s) on ${changeset.table}`,
        "success",
      );
      void queryClient.invalidateQueries({ queryKey: ["changesets"] });
      void navigate(`/changesets/${changeset.id}`);
    },
    onError: (e) => {
      const message = describeError(e);
      setFormError(message);
      showToast(message, "error");
    },
  });

  const attempt = (submitNow: boolean) => {
    setFormError(null);
    if (!title.trim()) {
      setFormError("A title is required");
      return;
    }
    try {
      items.map(parseItem);
    } catch (e) {
      setFormError(String(e));
      return;
    }
    create.mutate(submitNow);
  };

  const setItem = (index: number, patch: Partial<ItemDraft>) => {
    setItems((prev) =>
      prev.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    );
  };

  if (!hasTarget) return <TablePicker />;

  return (
    <>
      <p>
        <Link to="/" className="back-link">
          <Icon name="chevron-left" size={16} />
          All changesets
        </Link>
      </p>
      <h1>
        New changeset on{" "}
        <code>
          {backend}/{schema ?? ""}/{table}
        </code>
      </h1>
      <div className="form">
        <label>
          Title
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="What is changing?"
          />
        </label>
        <label>
          Description
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            placeholder="Why is it changing?"
          />
        </label>

        <h2>Change items</h2>
        {items.map((item, index) => (
          <div className="item-row" key={index}>
            <select
              value={item.op}
              onChange={(e) =>
                setItem(index, { op: e.target.value as ChangeOp })
              }
            >
              <option value="insert">insert</option>
              <option value="update">update</option>
              <option value="delete">delete</option>
            </select>
            <input
              placeholder='key JSON, e.g. {"pair": "EURUSD"}'
              value={item.key}
              onChange={(e) => setItem(index, { key: e.target.value })}
              disabled={item.op === "insert"}
            />
            <input
              placeholder='values JSON, e.g. {"rate": 1.09}'
              value={item.values}
              onChange={(e) => setItem(index, { values: e.target.value })}
              disabled={item.op === "delete"}
            />
            <button
              type="button"
              className="chip"
              onClick={() =>
                setItems((prev) => prev.filter((_, i) => i !== index))
              }
              disabled={items.length === 1}
            >
              remove
            </button>
          </div>
        ))}
        <p>
          <button
            type="button"
            className="chip"
            onClick={() =>
              setItems((prev) => [
                ...prev,
                { op: "insert", key: "", values: "{}" },
              ])
            }
          >
            + add item
          </button>
        </p>

        {formError && <p className="error">{formError}</p>}
        <p className="actions">
          <button
            type="button"
            onClick={() => attempt(false)}
            disabled={create.isPending}
          >
            Save draft
          </button>
          <button
            type="button"
            className="primary"
            onClick={() => attempt(true)}
            disabled={create.isPending}
          >
            Save &amp; submit for review
          </button>
        </p>
      </div>
    </>
  );
}
