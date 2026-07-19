"""CommentService: threaded discussion on changesets."""

from bizkit.domain.access import Action
from bizkit.domain.audit import AuditEvent
from bizkit.domain.comment import Comment
from bizkit.domain.ports import (
    AccessPolicy,
    AuditLog,
    ChangesetRepository,
    CommentRepository,
)
from bizkit.exceptions import AccessDeniedError


class CommentService:
    """Add and list threaded comments (authorized via ``comment``)."""

    def __init__(
        self,
        comments: CommentRepository,
        changesets: ChangesetRepository,
        audit: AuditLog,
        access: AccessPolicy,
    ) -> None:
        self._comments = comments
        self._changesets = changesets
        self._audit = audit
        self._access = access

    def add_comment(
        self,
        changeset_id: str,
        author: str,
        body: str,
        parent_id: str | None = None,
    ) -> Comment:
        """Add a comment (or threaded reply) to a changeset."""
        changeset = self._changesets.get(changeset_id)
        if not self._access.is_allowed(author, Action.COMMENT, changeset.table):
            raise AccessDeniedError(
                f"User {author!r} lacks 'comment' rights on "
                f"{changeset.table.qualified_name()}"
            )
        comment = Comment(
            changeset_id=changeset_id,
            author=author,
            body=body,
            parent_id=parent_id,
        )
        self._comments.add(comment)
        self._audit.append(
            AuditEvent(
                changeset_id=changeset_id,
                actor=author,
                action="comment",
                detail=f"comment {comment.id}",
            )
        )
        return comment

    def thread_for(self, changeset_id: str) -> list[Comment]:
        """Return a changeset's comments in creation order."""
        return self._comments.list_for(changeset_id)
