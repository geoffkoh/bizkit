"""Configuration objects for bizkit.

bizkit avoids global state: build a :class:`BizkitConfig` at the edge (CLI,
API startup, test fixture) and inject it into whatever needs it. The
workspace config *file* (spec D22/D23) is parsed by
:mod:`bizkit.workspace.loader` into these objects plus table configs and
grants.
"""

from datetime import timedelta
from typing import Final, Literal

from pydantic import BaseModel, Field

from bizkit.domain.access import Role

DEFAULT_STORE_URL: Final[str] = "sqlite:///bizkit.db"


class TargetConfig(BaseModel):
    """Connection profile for one target database.

    Attributes:
        backend: Registered backend technology (e.g. ``postgres``,
            ``snowflake``).
        url: SQLAlchemy connection URL for the target (supports
            ``${ENV_VAR}`` indirection in the workspace file, D30).
    """

    backend: str
    url: str


class GroupMapping(BaseModel):
    """External claim/group → role + scope mapping (D25).

    Attributes:
        group: Group or claim name asserted by trusted middleware.
        role: The bizkit role it maps to.
        scope: ``backend/schema/table`` pattern the role applies to.
    """

    group: str
    role: Role
    scope: str = "*/*/*"


class AccessConfig(BaseModel):
    """Access-control provider selection (spec D5/D22).

    Attributes:
        provider: ``file`` (workspace grants, default), ``store``
            (grants table, runtime administration), or ``groups``
            (external IAM claims).
        group_mappings: Used by the ``groups`` provider.
    """

    provider: Literal["file", "store", "groups"] = "file"
    group_mappings: list[GroupMapping] = Field(default_factory=list)


class WorkflowConfig(BaseModel):
    """Workflow policy defaults; per-table settings override them.

    Attributes:
        default_review_ttl: Review window default; ``None`` = no expiry
            (D21).
        default_apply_ttl: Apply window default; ``None`` = no expiry
            (D21).
        allow_self_approval: Deployment-level four-eyes opt-out (D26).
        max_changeset_items: Universal reviewability cap (D37).
    """

    default_review_ttl: timedelta | None = None
    default_apply_ttl: timedelta | None = None
    allow_self_approval: bool = False
    max_changeset_items: int = 10_000


class BizkitConfig(BaseModel):
    """Top-level bizkit configuration.

    Attributes:
        store_url: SQLAlchemy URL of the workflow metadata store (sync
            engine, D2; logical separation from targets, D29).
        targets: Named connection profiles for target databases.
        access: Access-control provider configuration.
        workflow: Workflow policy defaults.
    """

    store_url: str = DEFAULT_STORE_URL
    targets: dict[str, TargetConfig] = Field(default_factory=dict)
    access: AccessConfig = Field(default_factory=AccessConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)


def load_config(store_url: str | None = None) -> BizkitConfig:
    """Build a configuration object without a workspace file.

    Args:
        store_url: Override for the workflow store URL; defaults to
            ``sqlite:///bizkit.db`` when omitted.

    Returns:
        A ready-to-inject :class:`BizkitConfig`.
    """
    if store_url is None:
        return BizkitConfig()
    return BizkitConfig(store_url=store_url)
