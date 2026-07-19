"""Group-mapping AccessPolicy adapter (spec D5/D25).

Entitlements are principal-less: trusted middleware asserts the caller's
group names, and configuration maps group → role + scope. Claims used
for enforcement must come from the verified server-side channel, never
from the client.
"""

from collections.abc import Callable, Sequence

from bizkit.config import GroupMapping
from bizkit.domain.access import ROLE_ACTIONS, Action, Scope
from bizkit.domain.table import TableRef


class GroupMappingAccessPolicy:
    """Decides actions from externally-asserted groups.

    Args:
        mappings: Group → role + scope mappings from configuration.
        groups_for: Callback returning the trusted group names asserted
            for an actor by the auth middleware (D6/D25).
    """

    def __init__(
        self,
        mappings: Sequence[GroupMapping],
        groups_for: Callable[[str], Sequence[str]],
    ) -> None:
        self._mappings = [(m.group, m.role, Scope.parse(m.scope)) for m in mappings]
        self._groups_for = groups_for

    def is_allowed(self, actor: str, action: Action, table: TableRef) -> bool:
        """Whether the actor's asserted groups permit the action."""
        actor_groups = set(self._groups_for(actor))
        return any(
            group in actor_groups
            and action in ROLE_ACTIONS[role]
            and scope.matches(table)
            for group, role, scope in self._mappings
        )
