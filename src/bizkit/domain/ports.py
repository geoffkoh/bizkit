"""Ports (protocols) implemented by the store, workspace, and backend layers.

The domain defines these interfaces; :mod:`bizkit.store` implements the
repositories and audit log, :mod:`bizkit.workspace` (default) and
:mod:`bizkit.store` (optional) implement :class:`AccessPolicy` and
:class:`TableRegistry`, and :mod:`bizkit.backends` implements
:class:`TargetBackend`. Services depend only on these protocols.
"""

from collections.abc import Sequence
from typing import Protocol

from bizkit.domain.access import Action
from bizkit.domain.approval import ReviewDecision
from bizkit.domain.audit import AuditEvent
from bizkit.domain.changeset import Changeset
from bizkit.domain.comment import Comment
from bizkit.domain.table import ColumnSpec, TableRef
from bizkit.domain.table_config import TableConfig


class ChangesetRepository(Protocol):
    """Persistence port for changesets."""

    def add(self, changeset: Changeset) -> None:
        """Persist a new changeset."""
        ...

    def get(self, changeset_id: str) -> Changeset:
        """Load a changeset or raise ``StoreError`` if absent."""
        ...

    def list(self) -> list[Changeset]:
        """Return all changesets."""
        ...

    def update(self, changeset: Changeset) -> None:
        """Persist an existing changeset via compare-and-set (spec D31).

        Raises ``ConcurrencyError`` when another writer got there first.
        """
        ...


class CommentRepository(Protocol):
    """Persistence port for comments."""

    def add(self, comment: Comment) -> None:
        """Persist a new comment."""
        ...

    def list_for(self, changeset_id: str) -> list[Comment]:
        """Return all comments on a changeset in creation order."""
        ...


class DecisionRepository(Protocol):
    """Persistence port for review decisions."""

    def add(self, decision: ReviewDecision) -> None:
        """Persist a review decision."""
        ...

    def list_for(self, changeset_id: str) -> list[ReviewDecision]:
        """Return a changeset's decisions in creation order."""
        ...


class AuditLog(Protocol):
    """Append-only persistence port for audit events."""

    def append(self, event: AuditEvent) -> None:
        """Append an event; must share the transaction of the action."""
        ...

    def list_for(self, changeset_id: str) -> list[AuditEvent]:
        """Return a changeset's events in append order."""
        ...


class AccessPolicy(Protocol):
    """Authorization port (spec D5/D7).

    Implementations may consult file-based grants, the store's grants
    table, or an external IAM — services cannot tell the difference.
    """

    def is_allowed(self, actor: str, action: Action, table: TableRef) -> bool:
        """Whether the actor may perform the action on the table."""
        ...


class TableRegistry(Protocol):
    """Resolves a table reference to its registered configuration (D19/D22)."""

    def lookup(self, ref: TableRef) -> TableConfig | None:
        """Return the table's configuration, or ``None`` if unregistered."""
        ...


class TargetBackend(Protocol):
    """Port to a target database technology.

    Writes happen only in :meth:`apply`, and only for approved changesets.
    :meth:`dry_run` must leave the target unchanged.
    """

    @property
    def name(self) -> str:
        """Registered backend name."""
        ...

    def introspect_table(self, ref: TableRef) -> list[ColumnSpec]:
        """Describe a table in canonical column specs."""
        ...

    def read_rows(
        self, ref: TableRef, columns: Sequence[str]
    ) -> list[dict[str, object]]:
        """Read rows (read-only), e.g. for cross-table validation."""
        ...

    def dry_run(self, changeset: Changeset) -> None:
        """Rehearse a changeset without changing the target."""
        ...

    def apply(self, changeset: Changeset) -> None:
        """Apply an approved changeset to the target."""
        ...
