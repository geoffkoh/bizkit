"""Declarative validation rules and structured validation results.

Rules are serializable pydantic models — data, never code (spec D11).
Each rule type carries a ``kind`` discriminator so rule sets round-trip
through JSON. Evaluation semantics land with the validation milestone;
the schemas and report structures are the stable contract.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from bizkit.domain.changeset import ChangeItem
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


class BaseRule(BaseModel):
    """Common shape of all validation rules.

    Attributes:
        rule_id: Stable identifier referenced by issues and audit detail.
        description: Human-readable statement of the rule.
    """

    rule_id: str
    description: str = ""

    def evaluate(self, item: ChangeItem) -> list[ValidationIssue]:
        """Evaluate the rule against one change item.

        Args:
            item: The change item under validation.

        Returns:
            Structured issues; empty when the item passes.
        """
        raise NotImplementedError("Rule evaluation lands with the validation milestone")


class TypeRule(BaseRule):
    """A column value must conform to a canonical type."""

    kind: Literal["type"] = "type"
    column: str
    expected_type: str


class ConstraintRule(BaseRule):
    """Single-column constraints: nullability, bounds, allowed values."""

    kind: Literal["constraint"] = "constraint"
    column: str
    not_null: bool = False
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[str] | None = None


class CrossFieldRule(BaseRule):
    """A named predicate over multiple columns of the same row.

    ``predicate`` is the id of a registered predicate, never code.
    """

    kind: Literal["cross_field"] = "cross_field"
    columns: list[str]
    predicate: str


class CrossTableRule(BaseRule):
    """A check that reads another table (read-only) to validate a row.

    Example: a foreign-key-like existence check against a reference table.
    """

    kind: Literal["cross_table"] = "cross_table"
    ref_table: TableRef
    local_columns: list[str]
    ref_columns: list[str]
    must_exist: bool = True


Rule = Annotated[
    TypeRule | ConstraintRule | CrossFieldRule | CrossTableRule,
    Field(discriminator="kind"),
]
"""Discriminated union of all rule types (discriminator: ``kind``)."""
