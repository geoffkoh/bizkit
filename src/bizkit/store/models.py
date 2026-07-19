"""SQLAlchemy ORM models for the workflow store.

Persistence strategy (spec §4): the domain aggregate is stored as a JSON
payload column plus indexed scalar columns for querying. Audit rows carry
an autoincrement ``seq`` for stable append ordering; changesets carry
``lock_version`` for optimistic locking (D31).
"""

from typing import Any

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all store models."""


class ChangesetRecord(Base):
    """Persisted changeset aggregate."""

    __tablename__ = "bizkit_changesets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[str] = mapped_column(String(20), index=True)
    maker: Mapped[str] = mapped_column(String(200), index=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ReviewDecisionRecord(Base):
    """Persisted review decision."""

    __tablename__ = "bizkit_review_decisions"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    changeset_id: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class CommentRecord(Base):
    """Persisted comment."""

    __tablename__ = "bizkit_comments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    changeset_id: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class AuditEventRecord(Base):
    """Persisted audit event (append-only; spec D10/D35)."""

    __tablename__ = "bizkit_audit_events"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(32), unique=True)
    changeset_id: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
