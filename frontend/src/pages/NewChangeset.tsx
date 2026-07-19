import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
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

export function NewChangeset() {
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
      void queryClient.invalidateQueries({ queryKey: ["changesets"] });
      void navigate(`/changesets/${changeset.id}`);
    },
    onError: (e) => setFormError(String(e)),
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

  return (
    <>
      <p>
        <Link to="/tables">← Tables</Link>
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
