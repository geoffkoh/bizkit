"""File-backed AccessPolicy adapter — the default (spec D22)."""

from bizkit.domain.access import ROLE_ACTIONS, Action, Grant
from bizkit.domain.table import TableRef


class FileAccessPolicy:
    """Decides actions from grants declared in the workspace config file."""

    def __init__(self, grants: list[Grant]) -> None:
        self._grants = list(grants)

    def is_allowed(self, actor: str, action: Action, table: TableRef) -> bool:
        """Whether any of the actor's grants covers the action on the table."""
        return any(
            grant.principal == actor
            and action in ROLE_ACTIONS[grant.role]
            and grant.scope.matches(table)
            for grant in self._grants
        )
