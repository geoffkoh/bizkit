"""ImportService: bulk CSV → change items in a DRAFT changeset (spec D36).

A drafting convenience, never a control bypass: submit/validation/review/
apply are unchanged. All-or-nothing with a structured
:class:`ImportReport`; capped by the effective ``max_changeset_items``
(D37); audited with verb ``import`` recording source filename, content
hash, and row count.
"""

import csv
import hashlib
import io
from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, Field

from bizkit.config import WorkflowConfig
from bizkit.domain.access import Action
from bizkit.domain.audit import AuditEvent
from bizkit.domain.changeset import ChangeItem, ChangeOp, Changeset, ChangesetState
from bizkit.domain.ports import (
    AccessPolicy,
    AuditLog,
    ChangesetRepository,
    TableRegistry,
    TargetBackend,
)
from bizkit.domain.table import ColumnSpec
from bizkit.exceptions import (
    AccessDeniedError,
    ApprovalError,
    ChangesetLimitError,
    ChangesetStateError,
)

_TRUE_VALUES = {"true", "1", "yes", "y"}
_FALSE_VALUES = {"false", "0", "no", "n"}
_OP_COLUMN = "_op"


class ImportMode(StrEnum):
    """How rows in the file map to change items."""

    APPEND = "append"
    DIFF = "diff"


class ImportIssue(BaseModel):
    """One structured import finding (row/column scoped).

    Row 0 refers to the header/file level; data rows are 1-based.
    """

    row: int
    column: str | None = None
    message: str


class ImportReport(BaseModel):
    """Result of an import attempt.

    All-or-nothing: when ``issues`` contains anything, no items were
    added (D36).
    """

    issues: list[ImportIssue] = Field(default_factory=list)
    items_added: int = 0

    @property
    def ok(self) -> bool:
        """Whether the import succeeded."""
        return not self.issues


class ImportService:
    """Bulk CSV import into DRAFT changesets (spec D36).

    Args:
        changesets: Changeset repository (CAS updates, D31).
        audit: Append-only audit log sharing the same session.
        access: Authorization port.
        config: Workflow defaults (for the D37 cap).
        registry: Optional table registry for per-table cap overrides.
        backend_for: Resolves a changeset's table to its target backend
            (introspection for coercion; current rows for diff mode).
    """

    def __init__(
        self,
        changesets: ChangesetRepository,
        audit: AuditLog,
        access: AccessPolicy,
        config: WorkflowConfig | None = None,
        registry: TableRegistry | None = None,
        backend_for: Callable[..., TargetBackend] | None = None,
    ) -> None:
        self._changesets = changesets
        self._audit = audit
        self._access = access
        self._config = config or WorkflowConfig()
        self._registry = registry
        self._backend_for = backend_for

    def import_csv(
        self,
        changeset_id: str,
        actor: str,
        filename: str,
        content: bytes,
        mode: ImportMode = ImportMode.APPEND,
    ) -> ImportReport:
        """Import CSV rows into a DRAFT changeset (all-or-nothing).

        Args:
            changeset_id: The draft to extend.
            actor: Acting identity; must be the changeset's maker with
                ``submit`` rights on the table.
            filename: Source filename (recorded in the audit event).
            content: Raw CSV bytes (UTF-8, BOM tolerated).
            mode: ``append`` (explicit ``_op`` column) or ``diff``
                (file = desired end state).

        Returns:
            The structured report; ``items_added`` is 0 whenever any
            issue was found.

        Raises:
            ChangesetStateError: If the changeset is not in DRAFT.
            ApprovalError: If the actor is not the maker.
            AccessDeniedError: If the actor lacks submit rights.
            ChangesetLimitError: If the result would exceed the
                effective ``max_changeset_items`` cap (D37).
            NotImplementedError: If no backend resolver was provided.
        """
        changeset = self._changesets.get(changeset_id)
        if changeset.state is not ChangesetState.DRAFT:
            raise ChangesetStateError(
                f"Import targets DRAFT changesets only; {changeset.id} is "
                f"{changeset.state.value!r}"
            )
        if actor != changeset.maker:
            raise ApprovalError(
                f"Only the maker {changeset.maker!r} may import into "
                f"changeset {changeset.id}, not {actor!r}"
            )
        if not self._access.is_allowed(actor, Action.SUBMIT, changeset.table):
            raise AccessDeniedError(
                f"User {actor!r} lacks 'submit' rights on "
                f"{changeset.table.qualified_name()}"
            )
        if self._backend_for is None:
            raise NotImplementedError(
                "ImportService needs a backend resolver for introspection"
            )
        backend = self._backend_for(changeset.table)
        columns = backend.introspect_table(changeset.table)

        report = ImportReport()
        header, rows = self._parse_csv(content, report)
        if report.issues:
            return report

        by_name = {c.name: c for c in columns}
        pk_cols = [c.name for c in columns if c.primary_key]

        if mode is ImportMode.APPEND:
            items = self._append_items(header, rows, by_name, pk_cols, report)
        else:
            items = self._diff_items(
                backend, changeset, header, rows, by_name, pk_cols, report
            )
        if report.issues:
            return report

        cap = self._effective_max_items(changeset)
        if len(changeset.items) + len(items) > cap:
            raise ChangesetLimitError(
                f"Import would grow changeset {changeset.id} to "
                f"{len(changeset.items) + len(items)} items, exceeding the "
                f"effective max_changeset_items cap of {cap}"
            )

        changeset.items.extend(items)
        self._changesets.update(changeset)
        digest = hashlib.sha256(content).hexdigest()[:12]
        self._audit.append(
            AuditEvent(
                changeset_id=changeset.id,
                actor=actor,
                action="import",
                detail=(
                    f"{filename} sha256:{digest} mode={mode.value} "
                    f"rows={len(rows)} items={len(items)}"
                ),
            )
        )
        report.items_added = len(items)
        return report

    # -- parsing and coercion ---------------------------------------------

    def _parse_csv(
        self, content: bytes, report: ImportReport
    ) -> tuple[list[str], list[dict[str, str]]]:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            report.issues.append(ImportIssue(row=0, message="File is not valid UTF-8"))
            return [], []
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            report.issues.append(ImportIssue(row=0, message="CSV has no header row"))
            return [], []
        header = [name.strip() for name in reader.fieldnames]
        rows = [
            {(k or "").strip(): (v or "") for k, v in raw.items()} for raw in reader
        ]
        if not rows:
            report.issues.append(ImportIssue(row=0, message="CSV has no data rows"))
        return header, rows

    def _check_header(
        self,
        header: list[str],
        by_name: dict[str, ColumnSpec],
        report: ImportReport,
        allow_op: bool,
    ) -> None:
        for name in header:
            if name == _OP_COLUMN and allow_op:
                continue
            if name not in by_name:
                report.issues.append(
                    ImportIssue(
                        row=0,
                        column=name,
                        message=f"Unknown column {name!r} for this table",
                    )
                )

    def _coerce_cell(
        self,
        spec: ColumnSpec,
        raw: str,
        row_number: int,
        report: ImportReport,
    ) -> object | None:
        value = raw.strip()
        if value == "":
            return None
        if spec.type == "integer":
            try:
                return int(value)
            except ValueError:
                report.issues.append(
                    ImportIssue(
                        row=row_number,
                        column=spec.name,
                        message=f"{value!r} is not an integer",
                    )
                )
                return None
        if spec.type == "decimal":
            try:
                return float(value)
            except ValueError:
                report.issues.append(
                    ImportIssue(
                        row=row_number,
                        column=spec.name,
                        message=f"{value!r} is not a number",
                    )
                )
                return None
        if spec.type == "boolean":
            lowered = value.lower()
            if lowered in _TRUE_VALUES:
                return True
            if lowered in _FALSE_VALUES:
                return False
            report.issues.append(
                ImportIssue(
                    row=row_number,
                    column=spec.name,
                    message=f"{value!r} is not a boolean",
                )
            )
            return None
        return value

    def _coerce_row(
        self,
        row: dict[str, str],
        by_name: dict[str, ColumnSpec],
        row_number: int,
        report: ImportReport,
    ) -> dict[str, object]:
        coerced: dict[str, object] = {}
        for name, raw in row.items():
            spec = by_name.get(name)
            if spec is None:
                continue  # header check already flagged unknown columns
            value = self._coerce_cell(spec, raw, row_number, report)
            if value is not None:
                coerced[name] = value
        return coerced

    def _row_key(
        self,
        coerced: dict[str, object],
        pk_cols: list[str],
        row_number: int,
        report: ImportReport,
    ) -> dict[str, object] | None:
        key: dict[str, object] = {}
        for col in pk_cols:
            if col not in coerced:
                report.issues.append(
                    ImportIssue(
                        row=row_number,
                        column=col,
                        message="Missing primary-key value",
                    )
                )
                return None
            key[col] = coerced[col]
        return key

    # -- append mode -------------------------------------------------------

    def _append_items(
        self,
        header: list[str],
        rows: list[dict[str, str]],
        by_name: dict[str, ColumnSpec],
        pk_cols: list[str],
        report: ImportReport,
    ) -> list[ChangeItem]:
        self._check_header(header, by_name, report, allow_op=True)
        if report.issues:
            return []
        items: list[ChangeItem] = []
        for number, row in enumerate(rows, start=1):
            op_raw = row.get(_OP_COLUMN, "").strip().lower() or "insert"
            try:
                op = ChangeOp(op_raw)
            except ValueError:
                report.issues.append(
                    ImportIssue(
                        row=number,
                        column=_OP_COLUMN,
                        message=f"Unknown op {op_raw!r} "
                        "(expected insert/update/delete)",
                    )
                )
                continue
            if op is not ChangeOp.INSERT and not pk_cols:
                report.issues.append(
                    ImportIssue(
                        row=number,
                        column=_OP_COLUMN,
                        message="Table has no primary key; only inserts "
                        "can be imported",
                    )
                )
                continue
            coerced = self._coerce_row(row, by_name, number, report)
            if op is ChangeOp.INSERT:
                if not coerced:
                    report.issues.append(
                        ImportIssue(row=number, message="Insert row is empty")
                    )
                    continue
                items.append(ChangeItem(op=op, values=coerced))
                continue
            key = self._row_key(coerced, pk_cols, number, report)
            if key is None:
                continue
            if op is ChangeOp.DELETE:
                items.append(ChangeItem(op=op, key=key))
                continue
            values = {k: v for k, v in coerced.items() if k not in pk_cols}
            if not values:
                report.issues.append(
                    ImportIssue(
                        row=number,
                        message="Update row changes no non-key columns",
                    )
                )
                continue
            items.append(ChangeItem(op=op, key=key, values=values))
        return items

    # -- diff mode ---------------------------------------------------------

    def _diff_items(
        self,
        backend: TargetBackend,
        changeset: Changeset,
        header: list[str],
        rows: list[dict[str, str]],
        by_name: dict[str, ColumnSpec],
        pk_cols: list[str],
        report: ImportReport,
    ) -> list[ChangeItem]:
        if not pk_cols:
            report.issues.append(
                ImportIssue(
                    row=0,
                    message="Diff mode requires a primary key on the table",
                )
            )
            return []
        self._check_header(header, by_name, report, allow_op=False)
        for col in pk_cols:
            if col not in header:
                report.issues.append(
                    ImportIssue(
                        row=0,
                        column=col,
                        message="Diff mode requires every primary-key column",
                    )
                )
        if report.issues:
            return []

        desired: dict[tuple[str, ...], dict[str, object]] = {}
        for number, row in enumerate(rows, start=1):
            coerced = self._coerce_row(row, by_name, number, report)
            key = self._row_key(coerced, pk_cols, number, report)
            if key is None:
                continue
            desired[tuple(str(key[c]) for c in pk_cols)] = coerced
        if report.issues:
            return []

        current_rows = backend.read_rows(changeset.table, list(by_name))
        current: dict[tuple[str, ...], dict[str, object]] = {
            tuple(str(row[c]) for c in pk_cols): row for row in current_rows
        }

        items: list[ChangeItem] = []
        file_columns = [c for c in header if c in by_name]
        for key_tuple, wanted in desired.items():
            existing = current.get(key_tuple)
            key = {c: wanted[c] for c in pk_cols}
            if existing is None:
                items.append(ChangeItem(op=ChangeOp.INSERT, values=wanted))
                continue
            changed = {
                col: wanted.get(col)
                for col in file_columns
                if col not in pk_cols
                and str(wanted.get(col, "")) != str(existing.get(col, ""))
            }
            if changed:
                items.append(ChangeItem(op=ChangeOp.UPDATE, key=key, values=changed))
        for key_tuple, existing in current.items():
            if key_tuple not in desired:
                items.append(
                    ChangeItem(
                        op=ChangeOp.DELETE,
                        key={c: existing[c] for c in pk_cols},
                    )
                )
        return items

    def _effective_max_items(self, changeset: Changeset) -> int:
        table_config = (
            self._registry.lookup(changeset.table) if self._registry else None
        )
        if table_config is not None and table_config.max_changeset_items is not None:
            return table_config.max_changeset_items
        return self._config.max_changeset_items
