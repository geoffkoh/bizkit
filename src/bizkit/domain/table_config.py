"""Registered configuration-table settings.

A :class:`TableConfig` anchors per-table policy: validation rule sets
(spec D19), expiry TTLs (D21), the self-approval override (D27), and the
changeset size cap override (D37). Its system of record is the workspace
config file by default, or the optional store-backed registry (D22).
"""

from datetime import timedelta

from pydantic import BaseModel, Field

from bizkit.domain.table import TableRef
from bizkit.domain.validation import Rule


class TableConfig(BaseModel):
    """Per-table policy and rule set.

    Attributes:
        table: The configuration table this applies to.
        review_ttl: Review window; ``None`` falls back to the workflow
            default (D21).
        apply_ttl: Apply window; ``None`` falls back to the workflow
            default (D21).
        allow_self_approval: Tri-state four-eyes override; ``None``
            inherits the workflow default (D27).
        max_changeset_items: Tri-state size-cap override; ``None``
            inherits the workflow default (D37).
        rules: Declarative validation rule set (D11); versioned by
            content fingerprint under file-first config (D22).
    """

    table: TableRef
    review_ttl: timedelta | None = None
    apply_ttl: timedelta | None = None
    allow_self_approval: bool | None = None
    max_changeset_items: int | None = None
    rules: list[Rule] = Field(default_factory=list)
