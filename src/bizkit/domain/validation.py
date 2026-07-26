"""Declarative validation rules and structured validation results.

Rules are serializable pydantic models — data, never code (spec D11).
Each rule type carries a ``kind`` discriminator so rule sets round-trip
through JSON. Evaluation is pure: a rule reads the change item and, for
cross-table rules, rows fetched through the context's read-only callback —
never arbitrary code and never a write.

Two conventions run through every rule:

* **Deletes carry no values.** Value-shaped rules (type, constraint,
  cross-field, cross-table) do not apply to a DELETE item; referential
  concerns about deletions belong to the target's own constraints.
* **A column absent from an UPDATE is unchanged, not null.** Only the
  columns an item actually supplies are examined, so a partial update
  cannot trip a `not_null` rule on a column it never touches. For an
  INSERT, absence *is* meaningful — the row would be written without it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from bizkit.domain import predicates
from bizkit.domain.changeset import ChangeItem, ChangeOp
from bizkit.domain.table import TableRef


class Severity(StrEnum):
    """Severity of a validation issue; only errors block transitions."""

    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(BaseModel):
    """One structured validation finding — never a bare string.

    Attributes:
        rule_id: Id of the rule that produced the issue.
        table: Qualified name of the table the issue concerns.
        row_key: Identifier of the offending row, when known.
        column: Offending column, when the issue is column-scoped.
        severity: Error (blocking) or warning (advisory).
        message: Human-readable explanation.
    """

    rule_id: str
    table: str
    row_key: dict[str, object] | None = None
    column: str | None = None
    severity: Severity = Severity.ERROR
    message: str


class ValidationReport(BaseModel):
    """Collected issues from one validation run.

    Attributes:
        issues: All findings, errors and warnings alike.
    """

    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether the report contains no blocking (error) issues."""
        return all(issue.severity is not Severity.ERROR for issue in self.issues)


@dataclass(frozen=True)
class RuleContext:
    """Everything a rule needs beyond the change item itself.

    Attributes:
        table: The changeset's target table; stamped onto every issue.
        rows_for: Read-only row fetch used by cross-table rules. ``None``
            when no target connection is available — cross-table rules then
            report rather than passing, because failing open would let an
            unvalidated row reach apply.
    """

    table: TableRef
    rows_for: Callable[[TableRef, Sequence[str]], list[dict[str, object]]] | None = None


def _values_under_test(item: ChangeItem) -> dict[str, object] | None:
    """The columns a value-shaped rule should examine.

    Returns ``None`` for a DELETE, which supplies no values at all.
    """
    if item.op is ChangeOp.DELETE:
        return None
    return item.values or {}


class BaseRule(BaseModel):
    """Common shape of all validation rules.

    Attributes:
        rule_id: Stable identifier referenced by issues and audit detail.
        description: Human-readable statement of the rule.
    """

    rule_id: str
    description: str = ""

    def evaluate(self, item: ChangeItem, context: RuleContext) -> list[ValidationIssue]:
        """Evaluate the rule against one change item.

        Args:
            item: The change item under validation.
            context: Target table and the read-only row fetch.

        Returns:
            Structured issues; empty when the item passes.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement evaluate()"
        )

    def _issue(
        self,
        context: RuleContext,
        item: ChangeItem,
        message: str,
        column: str | None = None,
    ) -> ValidationIssue:
        """Build an issue pre-filled from the rule and item."""
        return ValidationIssue(
            rule_id=self.rule_id,
            table=context.table.qualified_name(),
            row_key=item.key,
            column=column,
            severity=Severity.ERROR,
            message=message,
        )


def _is_canonical_type(value: object, expected: str) -> bool:
    """Whether ``value`` inhabits bizkit's canonical type ``expected``.

    Deliberately strict: a numeric-looking *string* in a decimal column is a
    type error, not a near-miss. Every write path (CSV import, the grid, the
    API) coerces from the target's introspected types first, so a string
    arriving here means the value really is untyped.
    """
    # bool is an int subclass in Python; it is never a number to a rule.
    if isinstance(value, bool):
        return expected == "boolean"
    if expected == "integer":
        return isinstance(value, int)
    if expected == "decimal":
        return isinstance(value, int | float | Decimal)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return False
    if expected == "date":
        if isinstance(value, date) and not isinstance(value, datetime):
            return True
        return isinstance(value, str) and _parses_as(value, date.fromisoformat)
    if expected == "timestamp":
        if isinstance(value, datetime):
            return True
        return isinstance(value, str) and _parses_as(value, datetime.fromisoformat)
    # An unrecognised expected_type cannot be checked; treat as satisfied and
    # let `bizkit config validate` be the place that flags the rule set.
    return True


def _parses_as(raw: str, parser: Callable[[str], object]) -> bool:
    try:
        parser(raw)
    except ValueError:
        return False
    return True


def _as_number(value: object) -> Decimal | None:
    """Coerce to Decimal for bound comparisons, or ``None`` if not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None


class TypeRule(BaseRule):
    """A column value must conform to a canonical type."""

    kind: Literal["type"] = "type"
    column: str
    expected_type: str

    def evaluate(self, item: ChangeItem, context: RuleContext) -> list[ValidationIssue]:
        """Check the column's declared canonical type."""
        values = _values_under_test(item)
        if values is None or self.column not in values:
            return []
        value = values[self.column]
        # Nullability belongs to ConstraintRule; a null has no type to check.
        if value is None or _is_canonical_type(value, self.expected_type):
            return []
        return [
            self._issue(
                context,
                item,
                f"{self.column!r} value {value!r} is not a valid {self.expected_type}",
                column=self.column,
            )
        ]


class ConstraintRule(BaseRule):
    """Single-column constraints: nullability, bounds, allowed values."""

    kind: Literal["constraint"] = "constraint"
    column: str
    not_null: bool = False
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[str] | None = None

    def evaluate(self, item: ChangeItem, context: RuleContext) -> list[ValidationIssue]:
        """Check nullability, numeric bounds, and the allowed-value set."""
        values = _values_under_test(item)
        if values is None:
            return []
        issues: list[ValidationIssue] = []

        if self.column not in values:
            # Absent on an INSERT means the row would be written without it;
            # absent on an UPDATE means untouched.
            if self.not_null and item.op is ChangeOp.INSERT:
                issues.append(
                    self._issue(
                        context,
                        item,
                        f"{self.column!r} is required but missing (null)",
                        column=self.column,
                    )
                )
            return issues

        value = values[self.column]
        if value is None:
            if self.not_null:
                issues.append(
                    self._issue(
                        context,
                        item,
                        f"{self.column!r} must not be null",
                        column=self.column,
                    )
                )
            return issues

        if self.min_value is not None or self.max_value is not None:
            number = _as_number(value)
            if number is None:
                issues.append(
                    self._issue(
                        context,
                        item,
                        f"{self.column!r} value {value!r} is not numeric, so bounds "
                        "cannot be checked",
                        column=self.column,
                    )
                )
            else:
                if self.min_value is not None and number < Decimal(str(self.min_value)):
                    issues.append(
                        self._issue(
                            context,
                            item,
                            f"{self.column!r} value {value!r} is below the minimum "
                            f"{self.min_value}",
                            column=self.column,
                        )
                    )
                if self.max_value is not None and number > Decimal(str(self.max_value)):
                    issues.append(
                        self._issue(
                            context,
                            item,
                            f"{self.column!r} value {value!r} is above the maximum "
                            f"{self.max_value}",
                            column=self.column,
                        )
                    )

        if self.allowed_values is not None and str(value) not in self.allowed_values:
            allowed = ", ".join(sorted(self.allowed_values))
            issues.append(
                self._issue(
                    context,
                    item,
                    f"{self.column!r} value {value!r} is not one of the allowed "
                    f"values ({allowed})",
                    column=self.column,
                )
            )
        return issues


class CrossFieldRule(BaseRule):
    """A named predicate over multiple columns of the same row.

    ``predicate`` is the id of a registered predicate, never code.
    """

    kind: Literal["cross_field"] = "cross_field"
    columns: list[str]
    predicate: str

    def evaluate(self, item: ChangeItem, context: RuleContext) -> list[ValidationIssue]:
        """Apply the registered predicate to the declared columns."""
        values = _values_under_test(item)
        if values is None:
            return []
        # Only fire once the item supplies at least one declared column, so a
        # partial update is not judged on columns it never touched.
        if not any(column in values for column in self.columns):
            return []
        predicate = predicates.lookup(self.predicate)
        if predicate is None:
            return [
                self._issue(
                    context,
                    item,
                    f"unknown predicate {self.predicate!r} — rule set names a "
                    "predicate bizkit does not register",
                )
            ]
        subject = [values.get(column) for column in self.columns]
        if predicate(subject):
            return []
        columns = ", ".join(self.columns)
        return [
            self._issue(
                context,
                item,
                f"{columns} failed predicate {self.predicate!r}",
                column=self.columns[0] if len(self.columns) == 1 else None,
            )
        ]


class CrossTableRule(BaseRule):
    """A check that reads another table (read-only) to validate a row.

    Example: a foreign-key-like existence check against a reference table.
    """

    kind: Literal["cross_table"] = "cross_table"
    ref_table: TableRef
    local_columns: list[str]
    ref_columns: list[str]
    must_exist: bool = True

    def evaluate(self, item: ChangeItem, context: RuleContext) -> list[ValidationIssue]:
        """Check the local tuple against the reference table's rows."""
        values = _values_under_test(item)
        if values is None:
            return []
        if not any(column in values for column in self.local_columns):
            return []
        if context.rows_for is None:
            return [
                self._issue(
                    context,
                    item,
                    f"cannot check {self.ref_table.qualified_name()}: no target "
                    "connection available for cross-table validation",
                )
            ]
        subject = tuple(str(values.get(column)) for column in self.local_columns)
        known = {
            tuple(str(row.get(column)) for column in self.ref_columns)
            for row in context.rows_for(self.ref_table, self.ref_columns)
        }
        present = subject in known
        if present is self.must_exist:
            return []
        ref = self.ref_table.qualified_name()
        message = (
            f"{subject} not found in {ref}"
            if self.must_exist
            else f"{subject} already exists in {ref}"
        )
        return [
            self._issue(
                context,
                item,
                message,
                column=self.local_columns[0] if len(self.local_columns) == 1 else None,
            )
        ]


Rule = Annotated[
    TypeRule | ConstraintRule | CrossFieldRule | CrossTableRule,
    Field(discriminator="kind"),
]
"""Discriminated union of all rule types (discriminator: ``kind``)."""
