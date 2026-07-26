"""Base class for target-database adapters.

Contract (spec §5): writes to a target happen only in :meth:`apply`, and
only for approved changesets; :meth:`dry_run` must leave the target
unchanged. Driver imports are lazy (D3) so the core install never needs
optional drivers.
"""

import importlib
from collections.abc import Sequence
from typing import ClassVar

from sqlalchemy import Connection, Engine, MetaData, Table, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import Executable

from bizkit.domain.changeset import ChangeItem, ChangeOp, Changeset, ChangesetState
from bizkit.domain.table import ColumnSpec, TableRef
from bizkit.exceptions import ApplyError, BackendNotInstalledError

_APPLICABLE_STATES = frozenset(
    # FAILED is included because FAILED -> APPLIED is the retry of an
    # already-approved revision (spec D20), not a fresh approval.
    {ChangesetState.APPROVED, ChangesetState.FAILED}
)


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

    # -- write path (spec §5) ---------------------------------------------
    #
    # One implementation, built on SQLAlchemy Core against the reflected
    # table, serves every dialect: statements are compiled per-dialect by
    # SQLAlchemy and identifiers/parameters are quoted and bound rather than
    # interpolated. A dialect overrides only where its semantics genuinely
    # differ (see the per-backend modules for quirk notes).

    def _reflect(self, ref: TableRef) -> Table:
        """Reflect the target table, or fail with a clear message."""
        try:
            return Table(
                ref.table,
                MetaData(),
                schema=ref.schema_name,
                autoload_with=self.engine,
            )
        except SQLAlchemyError as exc:
            raise ApplyError(
                f"Cannot reflect {ref.qualified_name()!r} on backend "
                f"{self.name!r}: {exc}"
            ) from exc

    @staticmethod
    def _check_columns(table: Table, item: ChangeItem) -> None:
        """Reject column names the target does not have.

        A changeset whose items name foreign columns is a misattribution, so
        it must fail loudly rather than partially apply.
        """
        known = set(table.columns.keys())
        for source in (item.key or {}, item.values or {}):
            unknown = sorted(set(source) - known)
            if unknown:
                raise ApplyError(
                    f"{', '.join(repr(c) for c in unknown)} "
                    f"{'is' if len(unknown) == 1 else 'are'} not a column of "
                    f"{table.fullname!r}"
                )

    def _execute_item(
        self, connection: Connection, table: Table, item: ChangeItem, position: int
    ) -> None:
        """Execute one change item, asserting it touched exactly one row."""
        self._check_columns(table, item)
        where = None
        if item.op in (ChangeOp.UPDATE, ChangeOp.DELETE):
            if not item.key:
                raise ApplyError(f"item {position}: {item.op.value} requires a row key")
            where = [table.c[column] == value for column, value in item.key.items()]

        if item.op is ChangeOp.INSERT:
            if not item.values:
                raise ApplyError(f"item {position}: insert requires values")
            statement: Executable = table.insert().values(**item.values)
        elif item.op is ChangeOp.UPDATE:
            if not item.values:
                raise ApplyError(f"item {position}: update requires values")
            assert where is not None
            statement = table.update().where(*where).values(**item.values)
        else:
            assert where is not None
            statement = table.delete().where(*where)

        try:
            result = connection.execute(statement)
        except SQLAlchemyError as exc:
            raise ApplyError(f"item {position}: {exc}") from exc

        # A key that matches no row (or several) means the target drifted since
        # approval — exactly what pre-apply revalidation exists to catch, and
        # never something to silently absorb.
        if item.op in (ChangeOp.UPDATE, ChangeOp.DELETE) and result.rowcount != 1:
            raise ApplyError(
                f"item {position}: {item.op.value} on key {item.key!r} matched "
                f"{result.rowcount} rows, expected exactly 1 — the target has "
                "drifted since approval"
            )

    def _run(self, changeset: Changeset, *, commit: bool) -> None:
        """Execute every item in one transaction; commit or roll back.

        All-or-nothing: the first failure aborts the whole changeset.
        """
        if changeset.state not in _APPLICABLE_STATES:
            raise ApplyError(
                f"Changeset {changeset.id} is {changeset.state.value!r}; only "
                "an approved changeset may touch a target database"
            )
        if not changeset.items:
            return
        table = self._reflect(changeset.table)
        # An explicit transaction, rolled back for a rehearsal. `begin()` emits
        # ROLLBACK on exit unless committed, so a dry run cannot leak a write
        # even if a later item raises.
        with self.engine.connect() as connection:
            with connection.begin() as transaction:
                for position, item in enumerate(changeset.items, start=1):
                    self._execute_item(connection, table, item, position)
                if commit:
                    transaction.commit()
                else:
                    transaction.rollback()

    def dry_run(self, changeset: Changeset) -> None:
        """Rehearse a changeset without changing the target.

        Executes every item inside a transaction and rolls it back, so the
        target's own constraints are exercised for real. Raises
        :class:`~bizkit.exceptions.ApplyError` on the first problem.

        Note: engines without transactional DML (notably Databricks) cannot
        honour the rollback; those adapters must override this method.
        """
        self._run(changeset, commit=False)

    def apply(self, changeset: Changeset) -> None:
        """Apply an approved changeset to the target.

        The only method in bizkit that writes to a target database, and only
        for an APPROVED changeset (or a FAILED one being retried, D20).
        """
        self._run(changeset, commit=True)
