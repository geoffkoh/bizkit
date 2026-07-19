import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, currentUser } from "../api";
import { Deadline, StateBadge } from "../components/StateBadge";
import type {
  ChangesetDetailOut,
  CommentOut,
  TableActionsOut,
} from "../types";

function tableRouteFromPath(path: string): string {
  const [backend, schema, table] = path.split("/");
  return `/t/${encodeURIComponent(backend)}/${encodeURIComponent(
    schema || "-",
  )}/${encodeURIComponent(table)}`;
}

function useTableActions(path: string): TableActionsOut | undefined {
  const user = currentUser();
  const { data: tables } = useQuery({
    queryKey: ["tables", user],
    queryFn: api.listTables,
  });
  return tables?.find((t) => t.path === path)?.actions;
}

function Items({ changeset }: { changeset: ChangesetDetailOut }) {
  if (changeset.items.length === 0)
    return <p className="muted">No change items.</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>Op</th>
          <th>Row key</th>
          <th>Values</th>
        </tr>
      </thead>
      <tbody>
        {changeset.items.map((item, i) => (
          <tr key={i} className={`op-${item.op}`}>
            <td>
              <span className={`op op-${item.op}`}>{item.op}</span>
            </td>
            <td>
              <code>{item.key ? JSON.stringify(item.key) : "—"}</code>
            </td>
            <td>
              <code>{item.values ? JSON.stringify(item.values) : "—"}</code>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Actions({ changeset }: { changeset: ChangesetDetailOut }) {
  const user = currentUser();
  const tableActions = useTableActions(changeset.table);
  const canReview = tableActions?.approve ?? true;
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const act = useMutation({
    mutationFn: (fn: () => Promise<ChangesetDetailOut>) => fn(),
    onSuccess: () => {
      setActionError(null);
      setReason("");
      void queryClient.invalidateQueries();
    },
    onError: (e) => setActionError(String(e)),
  });

  const isMaker = user === changeset.maker;
  const state = changeset.state;
  const buttons: React.ReactNode[] = [];

  if (state === "draft" && isMaker) {
    buttons.push(
      <button
        key="submit"
        type="button"
        className="primary"
        onClick={() => act.mutate(() => api.submit(changeset.id))}
      >
        Submit for review
      </button>,
    );
  }
  if ((state === "draft" || state === "submitted") && isMaker) {
    buttons.push(
      <button
        key="withdraw"
        type="button"
        onClick={() => act.mutate(() => api.withdraw(changeset.id))}
      >
        Withdraw
      </button>,
    );
  }
  if (state === "submitted" && !isMaker && canReview) {
    buttons.push(
      <button
        key="approve"
        type="button"
        className="primary"
        onClick={() => act.mutate(() => api.approve(changeset.id, reason))}
      >
        Approve
      </button>,
      <button
        key="reject"
        type="button"
        className="danger"
        onClick={() => {
          if (!reason.trim()) {
            setActionError("Rejection requires a reason — fill the box first");
            return;
          }
          act.mutate(() => api.reject(changeset.id, reason));
        }}
      >
        Reject
      </button>,
    );
  }
  if (
    (state === "rejected" || state === "failed" || state === "expired") &&
    isMaker
  ) {
    buttons.push(
      <button
        key="rework"
        type="button"
        className="primary"
        onClick={() => act.mutate(() => api.rework(changeset.id))}
      >
        Rework (back to draft)
      </button>,
    );
  }

  return (
    <div className="panel">
      <h2>Actions</h2>
      {state === "submitted" && isMaker && (
        <p className="muted">
          You are the maker — another checker must review this changeset
          (four-eyes).
        </p>
      )}
      {state === "submitted" && !isMaker && canReview && (
        <label>
          Review note{" "}
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="optional for approve, required for reject"
          />
        </label>
      )}
      {buttons.length > 0 ? (
        <p className="actions">{buttons}</p>
      ) : (
        <p className="muted">
          No actions available for <strong>{user}</strong> in state{" "}
          <strong>{state}</strong>.
        </p>
      )}
      {actionError && <p className="error">{actionError}</p>}
    </div>
  );
}

function CommentNode({
  comment,
  all,
  onReply,
}: {
  comment: CommentOut;
  all: CommentOut[];
  onReply: (parentId: string) => void;
}) {
  const replies = all.filter((c) => c.parent_id === comment.id);
  return (
    <div className="comment">
      <div className="comment-head">
        <strong>{comment.author}</strong>
        <span className="muted">
          {new Date(comment.created_at).toLocaleString()}
        </span>
        <button
          type="button"
          className="chip"
          onClick={() => onReply(comment.id)}
        >
          reply
        </button>
      </div>
      <p>{comment.body}</p>
      {replies.length > 0 && (
        <div className="replies">
          {replies.map((r) => (
            <CommentNode key={r.id} comment={r} all={all} onReply={onReply} />
          ))}
        </div>
      )}
    </div>
  );
}

function Comments({
  changesetId,
  tablePath,
}: {
  changesetId: string;
  tablePath: string;
}) {
  const tableActions = useTableActions(tablePath);
  const canComment = tableActions?.comment ?? true;
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [parentId, setParentId] = useState<string | null>(null);
  const [commentError, setCommentError] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ["comments", changesetId],
    queryFn: () => api.listComments(changesetId),
  });

  const post = useMutation({
    mutationFn: () => api.addComment(changesetId, body, parentId),
    onSuccess: () => {
      setBody("");
      setParentId(null);
      setCommentError(null);
      void queryClient.invalidateQueries({
        queryKey: ["comments", changesetId],
      });
    },
    onError: (e) => setCommentError(String(e)),
  });

  const roots = (data ?? []).filter((c) => c.parent_id === null);
  const parent = data?.find((c) => c.id === parentId);

  return (
    <div className="panel">
      <h2>Comments</h2>
      {roots.length === 0 && <p className="muted">No comments yet.</p>}
      {roots.map((c) => (
        <CommentNode
          key={c.id}
          comment={c}
          all={data ?? []}
          onReply={setParentId}
        />
      ))}
      {!canComment && (
        <p className="muted">
          You have read-only access to this table — commenting is for
          makers and checkers.
        </p>
      )}
      {canComment && (
      <div className="comment-form">
        {parent && (
          <p className="muted">
            Replying to <strong>{parent.author}</strong>{" "}
            <button
              type="button"
              className="chip"
              onClick={() => setParentId(null)}
            >
              cancel
            </button>
          </p>
        )}
        <textarea
          rows={2}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Add a comment…"
        />
        <p className="actions">
          <button
            type="button"
            onClick={() => body.trim() && post.mutate()}
            disabled={post.isPending}
          >
            Comment
          </button>
        </p>
        {commentError && <p className="error">{commentError}</p>}
      </div>
      )}
    </div>
  );
}

function Decisions({ changesetId }: { changesetId: string }) {
  const { data } = useQuery({
    queryKey: ["decisions", changesetId],
    queryFn: () => api.listDecisions(changesetId),
  });
  if (!data || data.length === 0) return null;
  return (
    <div className="panel">
      <h2>Review decisions</h2>
      {data.map((d, i) => (
        <p key={i}>
          <strong>{d.checker}</strong> {d.decision}d revision {d.revision}
          {d.self_approved && <span className="badge-self">SELF-APPROVED</span>}
          {d.reason && <span className="muted"> — “{d.reason}”</span>}
          <span className="muted"> · {new Date(d.decided_at).toLocaleString()}</span>
        </p>
      ))}
    </div>
  );
}

function AuditTrail({ changesetId }: { changesetId: string }) {
  const { data } = useQuery({
    queryKey: ["audit", changesetId],
    queryFn: () => api.listAudit(changesetId),
  });
  if (!data || data.length === 0) return null;
  return (
    <div className="panel">
      <h2>Audit trail</h2>
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Actor</th>
            <th>Action</th>
            <th>Transition</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {data.map((e, i) => (
            <tr key={i}>
              <td className="muted">{new Date(e.at).toLocaleString()}</td>
              <td>{e.actor}</td>
              <td>
                <code>{e.action}</code>
              </td>
              <td className="muted">
                {e.from_state ?? "·"} → {e.to_state ?? "·"}
              </td>
              <td>{e.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ChangesetDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error } = useQuery({
    queryKey: ["changesets", id],
    queryFn: () => api.getChangeset(id!),
    enabled: Boolean(id),
  });

  if (isLoading) return <p className="muted">Loading…</p>;
  if (error instanceof ApiError && error.status === 404) {
    return (
      <p className="error">
        Changeset not found. <Link to="/">Back to the queue</Link>
      </p>
    );
  }
  if (error || !data)
    return <p className="error">Failed to load: {String(error)}</p>;

  return (
    <>
      <p>
        <Link to="/">← All changesets</Link>
      </p>
      <h1>
        {data.title} <StateBadge state={data.state} />
      </h1>
      {data.description && <p>{data.description}</p>}
      <dl>
        <dt>Table</dt>
        <dd>
          <Link to={tableRouteFromPath(data.table)}>
            <code>{data.table}</code>
          </Link>
        </dd>
        <dt>Maker</dt>
        <dd>{data.maker}</dd>
        <dt>Revision</dt>
        <dd>
          {data.revision}
          <span className="muted">
            {" "}
            — approvals bind to the exact revision reviewed
          </span>
        </dd>
        <dt>Deadlines</dt>
        <dd>
          <Deadline label="review by" value={data.review_deadline} />{" "}
          <Deadline label="apply by" value={data.apply_deadline} />
          {!data.review_deadline && !data.apply_deadline && (
            <span className="muted">none</span>
          )}
        </dd>
      </dl>

      <h2>Change items ({data.items.length})</h2>
      <Items changeset={data} />

      <Actions changeset={data} />
      <Decisions changesetId={data.id} />
      <Comments changesetId={data.id} tablePath={data.table} />
      <AuditTrail changesetId={data.id} />
    </>
  );
}
