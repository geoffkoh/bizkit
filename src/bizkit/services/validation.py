"""ValidationService: rule execution and dry-run orchestration.

Rule *semantics* live here; per-dialect dry-run *mechanics* live in the
backends (spec §6). Validation runs at submit AND again immediately
before apply (D12) — wiring into those transitions lands with the
validation milestone (see SPECIFICATION.md §13).
"""

from collections.abc import Sequence

from bizkit.domain.changeset import Changeset
from bizkit.domain.validation import BaseRule, ValidationReport


class ValidationService:
    """Runs declarative rule sets over changesets."""

    def validate(
        self, changeset: Changeset, rules: Sequence[BaseRule]
    ) -> ValidationReport:
        """Evaluate every rule against every change item.

        Args:
            changeset: The changeset under validation.
            rules: The table's declarative rule set (D11).

        Returns:
            A structured report; empty rule sets yield an ok report.
        """
        report = ValidationReport()
        for rule in rules:
            for item in changeset.items:
                report.issues.extend(rule.evaluate(item))
        return report
