import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type JSX, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { api, ApiError, currentUser } from "../api";
import { Icon } from "../components/Icon";
import { SkeletonLines, SkeletonTable } from "../components/Skeleton";
import { Deadline, StateBadge } from "../components/StateBadge";
import { showToast } from "../components/Toast";
import { describeError } from "../errors";
import { tableRouteFromPath } from "../routes";
import type {
  ApplyResultOut,
  ChangesetDetailOut,
  CommentOut,
  TableActionsOut,
} from "../types";

/** Changeset detail (UI_SPECIFICATION.md §4.3).
 *
 * Section order is fixed by the spec: header → metadata → change items →
 * actions → decisions → comments → audit trail. Actions render only when they
 * are legal in the current state for this caller's capacity (§4.3's state ×
 * capacity table), and every one surfaces a 403/409 inline as well as through
 * a toast.
 */

function useTableActions(path: string): TableActionsOut | undefined {
  const user = currentUser();
  const { data: tables } = useQuery({
    queryKey: ["tables", user],
    queryFn: api.listTables,
  });
  return tables?.find((t) => t.path === path)?.actions;
}

function Items({ changeset }: { changeset: ChangesetDetailOut }): JSX.Element {
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
              <span
                className={`op op-${item.op}`}
                aria-label={`operation: ${item.op}`}
              >
                {item.op}
              </span>
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

interface WorkflowAction {
  /** Toast copy on success — names what happened to what. */
  success: string;
  run: () => Promise<ChangesetDetailOut>;
}

function Actions({ changeset }: { changeset: ChangesetDetailOut }): JSX.Element {
  const user = currentUser();
  const tableActions = useTableActions(changeset.table);
  // Affordance only (D25): closed until the server says otherwise, and a 403
  // is still handled if affordance and enforcement disagree.
  const canReview = tableActions?.approve ?? false;
  // `apply` is its own action (checker role by default), so it gets its own
  // affordance rather than riding on `approve`.
  const canApply = tableActions?.apply ?? false;
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [confirmApply, setConfirmApply] = useState(false);
  const [applyOutcome, setApplyOutcome] = useState<ApplyResultOut | null>(null);

  const act = useMutation({
    mutationFn: (action: WorkflowAction) =>
      action.run().then((result) => ({ result, action })),
    onSuccess: ({ action }) => {
      setActionError(null);
      setReason("");
      setConfirmWithdraw(false);
      showToast(action.success, "success");
      void queryClient.invalidateQueries();
    },
    onError: (error) => {
      // §6: inline next to the control AND an ambient toast — never one or
      // the other.
      const message = describeError(error);
      setActionError(message);
      showToast(message, "error");
    },
  });

  const isMaker = user === changeset.maker;
  const state = changeset.state;
  const label = `“${changeset.title}”`;

  // Apply returns a result rather than throwing when the *target* refuses, so
  // it needs its own mutation: `ok: false` is a 200 carrying the reason and a
  // changeset that is now FAILED.
  const applyAct = useMutation({
    mutationFn: () => api.apply(changeset.id),
    onSuccess: (result) => {
      setConfirmApply(false);
      setActionError(null);
      setApplyOutcome(result.ok ? null : result);
      if (result.ok) {
        showToast(`Applied ${label} to ${changeset.table}`, "success");
      } else {
        const blocking = result.report?.issues.length ?? 0;
        showToast(
          `Apply failed — ${
            result.error ?? `${blocking} validation issue(s)`
          }`,
          "error",
        );
      }
      void queryClient.invalidateQueries();
    },
    onError: (error) => {
      const message = describeError(error);
      setActionError(message);
      showToast(message, "error");
    },
  });

  const buttons: ReactNode[] = [];

  if (state === "draft" && isMaker) {
    buttons.push(
      <button
        key="submit"
        type="button"
        className="primary"
        disabled={act.isPending}
        onClick={() =>
          act.mutate({
            run: () => api.submit(changeset.id),
            success: `Submitted ${label} for review (revision ${
              changeset.revision + 1
            })`,
          })
        }
      >
        Submit for review
      </button>,
    );
  }
  if ((state === "draft" || state === "submitted") && isMaker) {
    // Destructive: inline two-click confirmation (§6), never a modal.
    buttons.push(
      confirmWithdraw ? (
        <span className="confirm" key="withdraw">
          <span className="muted">Withdraw {label}?</span>
          <button
            type="button"
            className="danger"
            disabled={act.isPending}
            onClick={() =>
              act.mutate({
                run: () => api.withdraw(changeset.id),
                success: `Withdrew ${label}`,
              })
            }
          >
            Yes, withdraw
          </button>
          <button type="button" onClick={() => setConfirmWithdraw(false)}>
            Keep it
          </button>
        </span>
      ) : (
        <button
          key="withdraw"
          type="button"
          onClick={() => setConfirmWithdraw(true)}
        >
          Withdraw
        </button>
      ),
    );
  }
  if (state === "submitted" && !isMaker && canReview) {
    buttons.push(
      <button
        key="approve"
        type="button"
        className="primary"
        disabled={act.isPending}
        onClick={() =>
          act.mutate({
            run: () => api.approve(changeset.id, reason),
            success: `Approved ${label} at revision ${changeset.revision}`,
          })
        }
      >
        Approve
      </button>,
      <button
        key="reject"
        type="button"
        className="danger"
        disabled={act.isPending}
        onClick={() => {
          if (!reason.trim()) {
            setActionError("Rejection requires a reason — fill the box first");
            return;
          }
          act.mutate({
            run: () => api.reject(changeset.id, reason),
            success: `Rejected ${label} at revision ${changeset.revision}`,
          });
        }}
      >
        Reject
      </button>,
    );
  }
  if ((state === "approved" || state === "failed") && canApply) {
    // Writing to a real target is the one irreversible step in the workflow,
    // so it takes two clicks and the confirmation names the table.
    const isRetry = state === "failed";
    buttons.push(
      confirmApply ? (
        <span className="confirm" key="apply">
          <span className="muted">
            {isRetry ? "Retry apply to" : "Apply to"} <code>{changeset.table}</code>?
            This writes to the target database.
          </span>
          <button
            type="button"
            className="primary"
            disabled={applyAct.isPending}
            onClick={() => applyAct.mutate()}
          >
            {applyAct.isPending ? "Applying…" : "Yes, apply"}
          </button>
          <button type="button" onClick={() => setConfirmApply(false)}>
            Cancel
          </button>
        </span>
      ) : (
        <button
          key="apply"
          type="button"
          className="primary"
          disabled={applyAct.isPending}
          onClick={() => setConfirmApply(true)}
        >
          {isRetry ? "Retry apply" : "Apply to target"}
        </button>
      ),
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
        disabled={act.isPending}
        onClick={() =>
          act.mutate({
            run: () => api.rework(changeset.id),
            success: `Reopened ${label} as a draft for rework`,
          })
        }
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
        <label className="review-note">
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
      {applyOutcome && !applyOutcome.ok && (
        <div className="panel">
          <p className="error">
            Apply failed — the changeset is now{" "}
            <strong>{applyOutcome.changeset.state}</strong> and nothing was
            written to <code>{changeset.table}</code> (all-or-nothing).
          </p>
          {applyOutcome.error && (
            <p className="error">Target said: {applyOutcome.error}</p>
          )}
          {applyOutcome.report?.issues.map((issue, index) => (
            <p className="muted" key={`${issue.rule_id}-${index}`}>
              {issue.severity}: {issue.rule_id}
              {issue.column ? ` [${issue.column}]` : ""} — {issue.message}
            </p>
          ))}
          <p className="muted">
            Validation runs again immediately before apply, so this can differ
            from the report at submit — the target may have changed since
            approval. The maker can rework it, or a checker can retry once the
            cause is cleared.
          </p>
        </div>
      )}
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
}): JSX.Element {
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
}): JSX.Element {
  const tableActions = useTableActions(tablePath);
  // Readers get no composer at all (§5 visibility matrix, D38).
  const canComment = tableActions?.comment ?? false;
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [parentId, setParentId] = useState<string | null>(null);
  const [commentError, setCommentError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["comments", changesetId],
    queryFn: () => api.listComments(changesetId),
  });

  const post = useMutation({
    mutationFn: () => api.addComment(changesetId, body, parentId),
    onSuccess: (comment) => {
      setBody("");
      setParentId(null);
      setCommentError(null);
      showToast(
        comment.parent_id ? "Reply posted" : "Comment posted",
        "success",
      );
      void queryClient.invalidateQueries({
        queryKey: ["comments", changesetId],
      });
    },
    onError: (error) => {
      const message = describeError(error);
      setCommentError(message);
      showToast(message, "error");
    },
  });

  const roots = (data ?? []).filter((c) => c.parent_id === null);
  const parent = data?.find((c) => c.id === parentId);

  return (
    <div className="panel">
      <h2>Comments</h2>
      {isLoading && <p className="muted">Loading…</p>}
      {!isLoading && roots.length === 0 && (
        <p className="muted">
          No comments yet{canComment ? " — start the thread below." : "."}
        </p>
      )}
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
          You have read-only access to this table — commenting is for makers
          and checkers.
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
            aria-label="Comment"
            onChange={(e) => setBody(e.target.value)}
            placeholder="Add a comment…"
          />
          <p className="actions">
            <button
              type="button"
              onClick={() => body.trim() && post.mutate()}
              disabled={post.isPending || !body.trim()}
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

function Decisions({
  changesetId,
}: {
  changesetId: string;
}): JSX.Element | null {
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
          <strong>{d.checker}</strong> {d.decision}d revision{" "}
          <span className="tabular">{d.revision}</span>
          {d.self_approved && (
            <span className="badge-self" aria-label="self-approved decision">
              SELF-APPROVED
            </span>
          )}
          {d.reason && <span className="muted"> — “{d.reason}”</span>}
          <span className="muted">
            {" "}
            · {new Date(d.decided_at).toLocaleString()}
          </span>
        </p>
      ))}
    </div>
  );
}

function AuditTrail({
  changesetId,
}: {
  changesetId: string;
}): JSX.Element | null {
  const { data, isLoading } = useQuery({
    queryKey: ["audit", changesetId],
    queryFn: () => api.listAudit(changesetId),
  });
  if (isLoading) {
    return (
      <div className="panel">
        <h2>Audit trail</h2>
        <SkeletonTable rows={3} cols={5} label="Loading audit trail…" />
      </div>
    );
  }
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

export function ChangesetDetail(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error } = useQuery({
    queryKey: ["changesets", id],
    queryFn: () => api.getChangeset(id!),
    enabled: Boolean(id),
  });
  // Same cache entry as the Decisions panel below: §2.5 wants the badge on the
  // detail surface as well as in the decision list.
  const { data: decisions } = useQuery({
    queryKey: ["decisions", id],
    queryFn: () => api.listDecisions(id!),
    enabled: Boolean(id),
  });
  const selfApproved = (decisions ?? []).some((d) => d.self_approved);

  if (isLoading) return <SkeletonLines lines={4} label="Loading changeset…" />;
  if (error instanceof ApiError && error.status === 404) {
    return (
      <p className="error">
        Changeset not found. <Link to="/">Back to the queue</Link>
      </p>
    );
  }
  if (error || !data)
    return <p className="error">Could not load: {describeError(error)}</p>;

  return (
    <>
      <p>
        <Link to="/" className="back-link">
          <Icon name="chevron-left" size={16} />
          All changesets
        </Link>
      </p>
      <h1>
        {data.title} <StateBadge state={data.state} />
        {selfApproved && (
          <span className="badge-self" aria-label="self-approved decision">
            SELF-APPROVED
          </span>
        )}
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
          <span className="tabular">{data.revision}</span>
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
