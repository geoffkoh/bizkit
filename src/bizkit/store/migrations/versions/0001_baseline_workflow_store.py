"""Baseline workflow store schema.

Revision ID: 0001
Revises:
Created: 2026-07-27

The starting point of the migration chain (spec D46): the four always-present
store tables as they stood when ``metadata.create_all`` was retired.

Adoption case: a store created by the pre-D46 ``create_all`` path already has
these tables. Recreating them would fail, and dropping them would destroy the
audit trail, so this revision **skips creation when the schema is already
there** and simply stamps it — the same end state, without touching a row.
Later revisions need no such check; they are ordinary forward migrations.

Store migrations are forward-only and expand/contract (spec D46): additive
and N-1-compatible here, the contracting drop a release later. Never rewrite
audit rows -- D35's append-only guarantee holds through upgrades.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _already_present() -> bool:
    """Report whether a pre-migration store already holds these tables.

    Returns:
        True if the store predates D46 and needs stamping rather than
        creating. Always False offline, where there is no database to
        inspect and generated DDL assumes a fresh store.
    """
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table("bizkit_changesets")


def upgrade() -> None:
    """Create the baseline schema, unless it predates the migration chain."""
    if _already_present():
        return

    op.create_table(
        "bizkit_changesets",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("maker", sa.String(length=200), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bizkit_changesets_state"), "bizkit_changesets", ["state"], unique=False
    )
    op.create_index(
        op.f("ix_bizkit_changesets_maker"), "bizkit_changesets", ["maker"], unique=False
    )

    op.create_table(
        "bizkit_review_decisions",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("changeset_id", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("seq"),
    )
    op.create_index(
        op.f("ix_bizkit_review_decisions_changeset_id"),
        "bizkit_review_decisions",
        ["changeset_id"],
        unique=False,
    )

    op.create_table(
        "bizkit_comments",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("changeset_id", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bizkit_comments_changeset_id"),
        "bizkit_comments",
        ["changeset_id"],
        unique=False,
    )

    op.create_table(
        "bizkit_audit_events",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=32), nullable=False),
        sa.Column("changeset_id", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(
        op.f("ix_bizkit_audit_events_changeset_id"),
        "bizkit_audit_events",
        ["changeset_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the store. Destroys the audit trail; restore-from-backup instead."""
    op.drop_index(op.f("ix_bizkit_audit_events_changeset_id"), "bizkit_audit_events")
    op.drop_table("bizkit_audit_events")
    op.drop_index(op.f("ix_bizkit_comments_changeset_id"), "bizkit_comments")
    op.drop_table("bizkit_comments")
    op.drop_index(
        op.f("ix_bizkit_review_decisions_changeset_id"), "bizkit_review_decisions"
    )
    op.drop_table("bizkit_review_decisions")
    op.drop_index(op.f("ix_bizkit_changesets_maker"), "bizkit_changesets")
    op.drop_index(op.f("ix_bizkit_changesets_state"), "bizkit_changesets")
    op.drop_table("bizkit_changesets")
