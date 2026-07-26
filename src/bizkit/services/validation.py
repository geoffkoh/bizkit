"""ValidationService: rule execution and dry-run orchestration.

Rule *semantics* live in :mod:`bizkit.domain.validation`; per-dialect
dry-run *mechanics* live in the backends (spec §6). This service is the
seam between them, and the single place that assembles a
:class:`~bizkit.domain.validation.RuleContext`.

Validation runs at submit AND again immediately before apply (D12): the
target may drift between approval and apply, so a report that was clean at
submit proves nothing at apply time.
"""

from collections.abc import Callable, Sequence

from bizkit.domain.changeset import Changeset
from bizkit.domain.table import TableRef
from bizkit.domain.validation import BaseRule, RuleContext, ValidationReport

RowsFor = Callable[[TableRef, Sequence[str]], list[dict[str, object]]]


class ValidationService:
    """Runs declarative rule sets over changesets."""

    def validate(
        self,
        changeset: Changeset,
        rules: Sequence[BaseRule],
        rows_for: RowsFor | None = None,
    ) -> ValidationReport:
        """Evaluate every rule against every change item.

        Args:
            changeset: The changeset under validation.
            rules: The table's declarative rule set (D11).
            rows_for: Read-only row fetch for cross-table rules, resolved
                per referenced table so a rule may point at a table in
                another backend. ``None`` makes those rules report rather
                than pass — failing open would let an unvalidated row
                through to apply. Row-local rules never call it, so a rule
                set without cross-table rules needs no target connection.

        Returns:
            A structured report; empty rule sets yield an ok report.
        """
        context = RuleContext(table=changeset.table, rows_for=rows_for)
        report = ValidationReport()
        for rule in rules:
            for item in changeset.items:
                report.issues.extend(rule.evaluate(item, context))
        return report
