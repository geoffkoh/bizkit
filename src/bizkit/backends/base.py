"""Base class for target-database adapters.

Contract (spec §5): writes to a target happen only in :meth:`apply`, and
only for approved changesets; :meth:`dry_run` must leave the target
unchanged. Driver imports are lazy (D3) so the core install never needs
optional drivers.
"""

import importlib
from collections.abc import Sequence
from typing import ClassVar

from sqlalchemy import Engine, create_engine

from bizkit.domain.changeset import Changeset
from bizkit.domain.table import ColumnSpec, TableRef
from bizkit.exceptions import BackendNotInstalledError


class BaseBackend:
    """Common machinery for all target backends.

    Class Attributes:
        name: Registered backend name.
        extra: pip extra that installs the driver.
        driver_module: Import name checked lazily before first use.
    """

    name: ClassVar[str]
    extra: ClassVar[str]
    driver_module: ClassVar[str]

    def __init__(self, url: str) -> None:
        """Store the connection URL; no driver import happens here.

        Args:
            url: SQLAlchemy connection URL for the target.
        """
        self._url = url
        self._engine: Engine | None = None

    def _ensure_driver(self) -> None:
        """Import the optional driver or fail with the install hint."""
        try:
            importlib.import_module(self.driver_module)
        except ImportError as exc:
            raise BackendNotInstalledError(
                f"The {self.name!r} backend requires the optional driver "
                f"{self.driver_module!r}. Install it with: "
                f"pip install 'bizkit[{self.extra}]'"
            ) from exc

    @property
    def engine(self) -> Engine:
        """Lazily-created sync engine for the target."""
        if self._engine is None:
            self._ensure_driver()
            self._engine = create_engine(self._url)
        return self._engine

    def introspect_table(self, ref: TableRef) -> list[ColumnSpec]:
        """Describe a table in canonical column specs."""
        raise NotImplementedError(
            "Introspection lands with the backend implementation milestone"
        )

    def read_rows(
        self, ref: TableRef, columns: Sequence[str]
    ) -> list[dict[str, object]]:
        """Read rows (read-only), e.g. for cross-table validation."""
        raise NotImplementedError(
            "Read access lands with the backend implementation milestone"
        )

    def dry_run(self, changeset: Changeset) -> None:
        """Rehearse a changeset without changing the target."""
        raise NotImplementedError(
            "Dry-run lands with the backend implementation milestone"
        )

    def apply(self, changeset: Changeset) -> None:
        """Apply an approved changeset to the target."""
        raise NotImplementedError(
            "Apply lands with the backend implementation milestone"
        )
