"""Declarative rule evaluation (spec D11/D12).

Rules stay serializable data; these tests pin the *semantics* each `kind`
carries, including the partial-update rule that a column absent from an
UPDATE is unchanged rather than null.
"""

from collections.abc import Sequence

import pytest

from bizkit.domain.changeset import ChangeItem, ChangeOp
from bizkit.domain.table import TableRef
from bizkit.domain.validation import (
    ConstraintRule,
    CrossFieldRule,
    CrossTableRule,
    RuleContext,
    Severity,
    TypeRule,
    ValidationReport,
)

FX = TableRef(backend="sample", schema_name=None, table="fx_rates")


def ctx(
    rows: dict[str, list[dict[str, object]]] | None = None,
) -> RuleContext:
    """A context whose `rows_for` serves canned rows per qualified name."""

    def rows_for(ref: TableRef, columns: Sequence[str]) -> list[dict[str, object]]:
        return (rows or {}).get(ref.qualified_name(), [])

    return RuleContext(table=FX, rows_for=rows_for)


def insert(**values: object) -> ChangeItem:
    return ChangeItem(op=ChangeOp.INSERT, values=dict(values))


def update(key: dict[str, object], **values: object) -> ChangeItem:
    return ChangeItem(op=ChangeOp.UPDATE, key=key, values=dict(values))


def delete(**key: object) -> ChangeItem:
    return ChangeItem(op=ChangeOp.DELETE, key=dict(key))


class TestTypeRule:
    rule = TypeRule(rule_id="rate-numeric", column="rate", expected_type="decimal")

    def test_accepts_a_conforming_value(self) -> None:
        assert self.rule.evaluate(insert(rate=1.09), ctx()) == []

    def test_accepts_an_integer_for_a_decimal_column(self) -> None:
        assert self.rule.evaluate(insert(rate=2), ctx()) == []

    def test_rejects_a_non_numeric_value(self) -> None:
        issues = self.rule.evaluate(insert(rate="abc"), ctx())
        assert len(issues) == 1
        assert issues[0].rule_id == "rate-numeric"
        assert issues[0].column == "rate"
        assert issues[0].table == "fx_rates"
        assert issues[0].severity is Severity.ERROR

    def test_ignores_null_because_nullability_is_a_constraint_concern(self) -> None:
        assert self.rule.evaluate(insert(rate=None), ctx()) == []

    def test_ignores_a_column_absent_from_the_item(self) -> None:
        assert self.rule.evaluate(insert(pair="EURUSD"), ctx()) == []

    def test_ignores_deletes_which_carry_no_values(self) -> None:
        assert self.rule.evaluate(delete(pair="EURUSD"), ctx()) == []

    def test_checks_integers_strictly(self) -> None:
        rule = TypeRule(rule_id="t", column="n", expected_type="integer")
        assert rule.evaluate(insert(n=3), ctx()) == []
        assert len(rule.evaluate(insert(n=3.5), ctx())) == 1

    def test_rejects_bool_for_a_numeric_column(self) -> None:
        # bool is an int subclass in Python; a boolean is not a rate.
        assert len(self.rule.evaluate(insert(rate=True), ctx())) == 1


class TestConstraintRule:
    def test_not_null_rejects_an_explicit_null(self) -> None:
        rule = ConstraintRule(rule_id="r", column="rate", not_null=True)
        issues = rule.evaluate(insert(rate=None), ctx())
        assert len(issues) == 1
        assert "null" in issues[0].message.lower()

    def test_not_null_rejects_a_column_missing_from_an_insert(self) -> None:
        rule = ConstraintRule(rule_id="r", column="rate", not_null=True)
        assert len(rule.evaluate(insert(pair="EURUSD"), ctx())) == 1

    def test_not_null_ignores_a_column_absent_from_an_update(self) -> None:
        # A partial update leaves unlisted columns alone — not set to null.
        rule = ConstraintRule(rule_id="r", column="rate", not_null=True)
        assert rule.evaluate(update({"pair": "EURUSD"}, source="desk"), ctx()) == []

    def test_min_value_rejects_below_bound(self) -> None:
        rule = ConstraintRule(rule_id="r", column="rate", min_value=0)
        assert len(rule.evaluate(insert(rate=-1), ctx())) == 1
        assert rule.evaluate(insert(rate=0), ctx()) == []

    def test_max_value_rejects_above_bound(self) -> None:
        rule = ConstraintRule(rule_id="r", column="limit", max_value=10)
        assert len(rule.evaluate(insert(limit=11), ctx())) == 1
        assert rule.evaluate(insert(limit=10), ctx()) == []

    def test_bounds_on_a_non_numeric_value_report_rather_than_crash(self) -> None:
        rule = ConstraintRule(rule_id="r", column="rate", min_value=0)
        issues = rule.evaluate(insert(rate="abc"), ctx())
        assert len(issues) == 1

    def test_allowed_values_rejects_an_unknown_value(self) -> None:
        rule = ConstraintRule(
            rule_id="r", column="source", allowed_values=["vendor", "desk"]
        )
        assert len(rule.evaluate(insert(source="rumour"), ctx())) == 1
        assert rule.evaluate(insert(source="desk"), ctx()) == []

    def test_a_single_rule_can_report_several_issues(self) -> None:
        rule = ConstraintRule(
            rule_id="r", column="rate", not_null=True, min_value=0, max_value=5
        )
        assert rule.evaluate(insert(rate=3), ctx()) == []
        assert len(rule.evaluate(insert(rate=99), ctx())) == 1

    def test_carries_the_row_key_on_updates(self) -> None:
        rule = ConstraintRule(rule_id="r", column="rate", min_value=0)
        issues = rule.evaluate(update({"pair": "EURUSD"}, rate=-1), ctx())
        assert issues[0].row_key == {"pair": "EURUSD"}


class TestCrossFieldRule:
    def test_registered_predicate_passes_and_fails(self) -> None:
        rule = CrossFieldRule(
            rule_id="pair-format", columns=["pair"], predicate="pair-is-6-uppercase"
        )
        assert rule.evaluate(insert(pair="EURUSD"), ctx()) == []
        assert len(rule.evaluate(insert(pair="eurusd"), ctx())) == 1
        assert len(rule.evaluate(insert(pair="EUR"), ctx())) == 1

    def test_iso_date_predicate(self) -> None:
        rule = CrossFieldRule(
            rule_id="day-iso", columns=["day"], predicate="date-is-iso"
        )
        assert rule.evaluate(insert(day="2027-01-01"), ctx()) == []
        assert len(rule.evaluate(insert(day="01/01/2027"), ctx())) == 1

    def test_isin_predicate_checks_the_check_digit(self) -> None:
        rule = CrossFieldRule(
            rule_id="isin", columns=["isin"], predicate="isin-is-valid"
        )
        assert rule.evaluate(insert(isin="US0378331005"), ctx()) == []
        assert len(rule.evaluate(insert(isin="US0378331006"), ctx())) == 1

    def test_an_unknown_predicate_is_an_error_not_a_crash(self) -> None:
        # Rule sets are config; a typo must surface as a validation issue.
        rule = CrossFieldRule(rule_id="r", columns=["pair"], predicate="no-such")
        issues = rule.evaluate(insert(pair="EURUSD"), ctx())
        assert len(issues) == 1
        assert "unknown predicate" in issues[0].message.lower()

    def test_ignores_deletes(self) -> None:
        rule = CrossFieldRule(
            rule_id="r", columns=["pair"], predicate="pair-is-6-uppercase"
        )
        assert rule.evaluate(delete(pair="EURUSD"), ctx()) == []


class TestCrossTableRule:
    rule = CrossTableRule(
        rule_id="desk-known",
        ref_table=TableRef(backend="sample", table="desks"),
        local_columns=["desk"],
        ref_columns=["name"],
        must_exist=True,
    )

    def test_passes_when_the_referenced_row_exists(self) -> None:
        rows: dict[str, list[dict[str, object]]] = {
            "desks": [{"name": "FX"}, {"name": "RATES"}]
        }
        assert self.rule.evaluate(insert(desk="FX"), ctx(rows)) == []

    def test_fails_when_the_referenced_row_is_missing(self) -> None:
        rows: dict[str, list[dict[str, object]]] = {"desks": [{"name": "FX"}]}
        issues = self.rule.evaluate(insert(desk="EQUITY"), ctx(rows))
        assert len(issues) == 1
        assert "desks" in issues[0].message

    def test_must_exist_false_inverts_the_check(self) -> None:
        rule = self.rule.model_copy(update={"must_exist": False})
        rows: dict[str, list[dict[str, object]]] = {"desks": [{"name": "FX"}]}
        assert len(rule.evaluate(insert(desk="FX"), ctx(rows))) == 1
        assert rule.evaluate(insert(desk="EQUITY"), ctx(rows)) == []

    def test_without_a_target_connection_it_reports_rather_than_passing(self) -> None:
        # Failing open would let an unvalidated row through to apply.
        issues = self.rule.evaluate(
            insert(desk="FX"), RuleContext(table=FX, rows_for=None)
        )
        assert len(issues) == 1
        assert issues[0].severity is Severity.ERROR

    def test_ignores_deletes(self) -> None:
        assert self.rule.evaluate(delete(pair="EURUSD"), ctx({"desks": []})) == []


class TestSerialization:
    @pytest.mark.parametrize(
        "rule",
        [
            TypeRule(rule_id="a", column="c", expected_type="integer"),
            ConstraintRule(rule_id="b", column="c", not_null=True),
            CrossFieldRule(rule_id="c", columns=["c"], predicate="date-is-iso"),
            CrossTableRule(
                rule_id="d",
                ref_table=TableRef(backend="s", table="t"),
                local_columns=["a"],
                ref_columns=["b"],
            ),
        ],
    )
    def test_rules_round_trip_through_json(self, rule: object) -> None:
        # Rules are data, never code (D11): evaluation must not break that.
        assert isinstance(
            rule, TypeRule | ConstraintRule | CrossFieldRule | CrossTableRule
        )
        restored = type(rule).model_validate_json(rule.model_dump_json())
        assert restored == rule


class TestReport:
    def test_ok_is_false_only_for_errors(self) -> None:
        rule = ConstraintRule(rule_id="r", column="rate", min_value=0)
        report = ValidationReport(issues=rule.evaluate(insert(rate=-1), ctx()))
        assert report.ok is False

    def test_empty_report_is_ok(self) -> None:
        assert ValidationReport().ok is True
