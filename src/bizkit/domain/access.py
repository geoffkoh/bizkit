"""Access-control domain model: roles, actions, scopes, grants.

Rights are scoped per table/target (spec D5). Principals are external
identities — bizkit never stores credentials (D6). The ``AccessPolicy``
port consuming these types lives in :mod:`bizkit.domain.ports`.
"""

from enum import StrEnum
from typing import Final

from pydantic import BaseModel

from bizkit.domain.table import TableRef
from bizkit.exceptions import ConfigError


class Role(StrEnum):
    """Coarse role granted on a scope."""

    MAKER = "maker"
    CHECKER = "checker"
    READER = "reader"
    ADMIN = "admin"


class Action(StrEnum):
    """Fine-grained workflow action checked by the AccessPolicy port."""

    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    APPLY = "apply"
    COMMENT = "comment"
    VIEW = "view"


ROLE_ACTIONS: Final[dict[Role, frozenset[Action]]] = {
    Role.MAKER: frozenset({Action.SUBMIT, Action.COMMENT, Action.VIEW}),
    Role.CHECKER: frozenset(
        {
            Action.APPROVE,
            Action.REJECT,
            Action.APPLY,
            Action.COMMENT,
            Action.VIEW,
        }
    ),
    Role.READER: frozenset({Action.VIEW}),
    Role.ADMIN: frozenset({Action.VIEW}),
}
"""Default role → action mapping (spec §3.2). Readers hold view only
(D38); admin manages grants and views — neither gains approve rights
implicitly."""


class Scope(BaseModel):
    """What a grant applies to: ``(backend, schema, table)`` with wildcards.

    Each segment is an exact string or ``*`` (matches anything). The
    ``backend`` segment refers to the target profile name from the
    workspace configuration.
    """

    backend: str = "*"
    schema_name: str = "*"
    table: str = "*"

    @classmethod
    def parse(cls, spec: str) -> "Scope":
        """Parse a ``backend/schema/table`` scope string.

        Args:
            spec: Scope pattern, e.g. ``fx_prod/*/FX_RATES``.

        Returns:
            The parsed scope.

        Raises:
            ConfigError: If the pattern does not have three segments.
        """
        parts = spec.split("/")
        if len(parts) != 3 or not all(parts):
            raise ConfigError(
                f"Invalid scope {spec!r}: expected 'backend/schema/table' "
                "with '*' wildcards"
            )
        return cls(backend=parts[0], schema_name=parts[1], table=parts[2])

    def matches(self, ref: TableRef) -> bool:
        """Whether this scope covers the given table reference."""
        ref_schema = ref.schema_name if ref.schema_name is not None else ""
        return (
            self.backend in ("*", ref.backend)
            and self.schema_name in ("*", ref_schema)
            and self.table in ("*", ref.table)
        )


class Grant(BaseModel):
    """A principal's role on a scope (internal file/store adapters only).

    With an external IAM (spec D25), entitlements live outside bizkit and
    no Grant objects exist.
    """

    principal: str
    role: Role
    scope: Scope
