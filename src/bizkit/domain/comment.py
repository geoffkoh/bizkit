"""Threaded comments on changesets."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex


class Comment(BaseModel):
    """A comment on a changeset, threaded via ``parent_id``.

    Attributes:
        id: Opaque unique identifier.
        changeset_id: The changeset being discussed.
        author: User who wrote the comment.
        body: Comment text.
        parent_id: Id of the comment being replied to, or ``None`` for a
            top-level comment.
        created_at: Creation timestamp (UTC).
    """

    id: str = Field(default_factory=_new_id)
    changeset_id: str
    author: str
    body: str
    parent_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
