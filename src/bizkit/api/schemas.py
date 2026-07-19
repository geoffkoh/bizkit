"""API DTOs — deliberately separate from domain models (spec §7)."""

from datetime import datetime

from pydantic import BaseModel, Field

from bizkit.domain.access import Action
from bizkit.domain.approval import ReviewDecision
from bizkit.domain.audit import AuditEvent
from bizkit.domain.changeset import ChangeItem, ChangeOp, Changeset
from bizkit.domain.comment import Comment
from bizkit.domain.ports import AccessPolicy
from bizkit.domain.table import TableRef
from bizkit.domain.table_config import TableConfig


class HealthOut(BaseModel):
    """Liveness response."""

    status: str = "ok"


class ReadyOut(BaseModel):
    """Readiness response (store reachable + config loaded)."""

    status: str
    store: bool
    config_fingerprint: str | None = None


class MeOut(BaseModel):
    """The caller's identity as asserted by the (dev) auth middleware."""

    user: str


def _table_path(ref: TableRef) -> str:
    return f"{ref.backend}/{ref.schema_name or ''}/{ref.table}"


def _rule_out(rule: BaseModel) -> "RuleOut":
    data = rule.model_dump(mode="json")
    return RuleOut(
        rule_id=str(data.pop("rule_id")),
        kind=str(data.pop("kind")),
        description=str(data.pop("description", "")),
        column=(str(data["column"]) if data.get("column") is not None else None),
        params={k: v for k, v in data.items() if k != "column" and v is not None},
    )


class ChangeItemOut(BaseModel):
    """One row-level change."""

    op: ChangeOp
    key: dict[str, object] | None = None
    values: dict[str, object] | None = None

    @classmethod
    def from_domain(cls, item: ChangeItem) -> "ChangeItemOut":
        """Project a domain change item."""
        return cls(op=item.op, key=item.key, values=item.values)


class ChangesetOut(BaseModel):
    """Changeset list projection."""

    id: str
    table: str
    maker: str
    title: str
    state: str
    revision: int
    item_count: int
    review_deadline: datetime | None
    apply_deadline: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, changeset: Changeset) -> "ChangesetOut":
        """Project a domain changeset into the list shape."""
        return cls(
            id=changeset.id,
            table=_table_path(changeset.table),
            maker=changeset.maker,
            title=changeset.title,
            state=changeset.state.value,
            revision=changeset.revision,
            item_count=len(changeset.items),
            review_deadline=changeset.review_deadline,
            apply_deadline=changeset.apply_deadline,
            created_at=changeset.created_at,
            updated_at=changeset.updated_at,
        )


class ChangesetDetailOut(ChangesetOut):
    """Changeset detail projection including items and description."""

    description: str
    items: list[ChangeItemOut]

    @classmethod
    def from_domain(cls, changeset: Changeset) -> "ChangesetDetailOut":
        """Project a domain changeset into the detail shape."""
        base = ChangesetOut.from_domain(changeset)
        return cls(
            **base.model_dump(),
            description=changeset.description,
            items=[ChangeItemOut.from_domain(i) for i in changeset.items],
        )


class RuleOut(BaseModel):
    """A declarative validation rule, presented for transparency (D11).

    Makers see constraints before drafting; readers/auditors see the
    governance on each table. Rules are data, so this is a plain
    projection of the rule model.
    """

    rule_id: str
    kind: str
    description: str
    column: str | None = None
    params: dict[str, object]


class TableActionsOut(BaseModel):
    """The caller's per-table affordances (D25/D28 — UX only, never authz)."""

    submit: bool
    approve: bool
    reject: bool
    comment: bool
    view: bool


class TableOut(BaseModel):
    """A registered configuration table and its effective policy."""

    backend: str
    schema_name: str | None
    table: str
    path: str
    rule_count: int
    review_ttl_seconds: float | None
    apply_ttl_seconds: float | None
    allow_self_approval: bool
    max_changeset_items: int
    rules: list[RuleOut]
    actions: TableActionsOut

    @classmethod
    def from_config(
        cls,
        config: TableConfig,
        actor: str,
        policy: AccessPolicy,
        global_self_approval: bool,
        global_max_items: int,
    ) -> "TableOut":
        """Project a table config plus the caller's affordances."""
        ref = config.table
        effective_self = (
            config.allow_self_approval
            if config.allow_self_approval is not None
            else global_self_approval
        )
        effective_max = (
            config.max_changeset_items
            if config.max_changeset_items is not None
            else global_max_items
        )
        return cls(
            backend=ref.backend,
            schema_name=ref.schema_name,
            table=ref.table,
            path=_table_path(ref),
            rule_count=len(config.rules),
            review_ttl_seconds=(
                config.review_ttl.total_seconds() if config.review_ttl else None
            ),
            apply_ttl_seconds=(
                config.apply_ttl.total_seconds() if config.apply_ttl else None
            ),
            allow_self_approval=effective_self,
            max_changeset_items=effective_max,
            rules=[_rule_out(rule) for rule in config.rules],
            actions=TableActionsOut(
                submit=policy.is_allowed(actor, Action.SUBMIT, ref),
                approve=policy.is_allowed(actor, Action.APPROVE, ref),
                reject=policy.is_allowed(actor, Action.REJECT, ref),
                comment=policy.is_allowed(actor, Action.COMMENT, ref),
                view=policy.is_allowed(actor, Action.VIEW, ref),
            ),
        )


class ColumnOut(BaseModel):
    """A column of a browsable table (canonical typing, D39)."""

    name: str
    type: str
    nullable: bool
    primary_key: bool


class RowsOut(BaseModel):
    """One page of table rows (D39)."""

    rows: list[dict[str, object]]
    total: int
    page: int
    page_size: int


class ChangeItemIn(BaseModel):
    """One row-level change in a creation request."""

    op: ChangeOp
    key: dict[str, object] | None = None
    values: dict[str, object] | None = None


class CreateChangesetIn(BaseModel):
    """Create a draft changeset (optionally submitting immediately)."""

    backend: str
    schema_name: str | None = None
    table: str
    title: str
    description: str = ""
    items: list[ChangeItemIn] = Field(default_factory=list)
    submit_now: bool = False


class ReviewIn(BaseModel):
    """Approve/reject request body."""

    reason: str = ""


class CommentIn(BaseModel):
    """New comment request body."""

    body: str
    parent_id: str | None = None


class CommentOut(BaseModel):
    """A comment on a changeset."""

    id: str
    changeset_id: str
    author: str
    body: str
    parent_id: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, comment: Comment) -> "CommentOut":
        """Project a domain comment."""
        return cls(
            id=comment.id,
            changeset_id=comment.changeset_id,
            author=comment.author,
            body=comment.body,
            parent_id=comment.parent_id,
            created_at=comment.created_at,
        )


class DecisionOut(BaseModel):
    """A review decision; self-approvals are flagged conspicuously (D26)."""

    revision: int
    checker: str
    decision: str
    reason: str
    decided_at: datetime
    self_approved: bool

    @classmethod
    def from_domain(cls, decision: ReviewDecision, maker: str) -> "DecisionOut":
        """Project a domain decision, deriving the self-approval flag."""
        return cls(
            revision=decision.revision,
            checker=decision.checker,
            decision=decision.decision.value,
            reason=decision.reason,
            decided_at=decision.decided_at,
            self_approved=decision.checker == maker,
        )


class ImportIssueOut(BaseModel):
    """One structured import finding (row 0 = header/file level)."""

    row: int
    column: str | None
    message: str


class ImportReportOut(BaseModel):
    """Import result: all-or-nothing (D36)."""

    ok: bool
    items_added: int
    issues: list[ImportIssueOut]


class AuditEventOut(BaseModel):
    """An audit-trail entry."""

    actor: str
    action: str
    from_state: str | None
    to_state: str | None
    detail: str
    at: datetime

    @classmethod
    def from_domain(cls, event: AuditEvent) -> "AuditEventOut":
        """Project a domain audit event."""
        return cls(
            actor=event.actor,
            action=event.action,
            from_state=event.from_state.value if event.from_state else None,
            to_state=event.to_state.value if event.to_state else None,
            detail=event.detail,
            at=event.at,
        )
