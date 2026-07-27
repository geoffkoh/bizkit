"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Created: ${create_date}

Store migrations are forward-only and expand/contract (spec D46): additive
and N-1-compatible here, the contracting drop a release later. Never rewrite
audit rows -- D35's append-only guarantee holds through upgrades.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply the schema change."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Best-effort reversal; the supported rollback is restore-from-backup."""
    ${downgrades if downgrades else "pass"}
