"""Scope wildcard matching and grant-based decisions (spec D5/D27)."""

import pytest

from bizkit.domain.access import ROLE_ACTIONS, Action, Grant, Role, Scope
from bizkit.domain.table import TableRef
from bizkit.exceptions import ConfigError
from bizkit.workspace.access import FileAccessPolicy


def test_scope_parse_roundtrip() -> None:
    scope = Scope.parse("fx_prod/MART/FX_RATES")
    assert (scope.backend, scope.schema_name, scope.table) == (
        "fx_prod",
        "MART",
        "FX_RATES",
    )


def test_scope_parse_rejects_bad_patterns() -> None:
    for bad in ("fx_prod", "a/b", "a/b/c/d", "a//c"):
        with pytest.raises(ConfigError):
            Scope.parse(bad)


@pytest.mark.parametrize(
    ("pattern", "matches"),
    [
        ("*/*/*", True),
        ("fx_prod/*/*", True),
        ("fx_prod/MART/*", True),
        ("fx_prod/MART/FX_RATES", True),
        ("fx_prod/*/OTHER", False),
        ("other/*/*", False),
        ("fx_prod/PUBLIC/*", False),
    ],
)
def test_scope_matching(pattern: str, matches: bool) -> None:
    ref = TableRef(backend="fx_prod", schema_name="MART", table="FX_RATES")
    assert Scope.parse(pattern).matches(ref) is matches


def test_none_schema_matches_wildcard_only() -> None:
    ref = TableRef(backend="b", schema_name=None, table="t")
    assert Scope.parse("b/*/t").matches(ref)
    assert not Scope.parse("b/S/t").matches(ref)


def test_checker_role_cannot_submit() -> None:
    assert Action.SUBMIT not in ROLE_ACTIONS[Role.CHECKER]
    assert Action.APPROVE not in ROLE_ACTIONS[Role.MAKER]


def test_reader_role_is_view_only() -> None:
    assert ROLE_ACTIONS[Role.READER] == {Action.VIEW}


def test_file_access_policy_allow_and_deny(fx_table: TableRef) -> None:
    policy = FileAccessPolicy(
        [
            Grant(
                principal="alice",
                role=Role.MAKER,
                scope=Scope.parse("sample/*/*"),
            )
        ]
    )
    assert policy.is_allowed("alice", Action.SUBMIT, fx_table)
    assert not policy.is_allowed("alice", Action.APPROVE, fx_table)
    assert not policy.is_allowed("mallory", Action.SUBMIT, fx_table)
    other = TableRef(backend="prod", table="limits")
    assert not policy.is_allowed("alice", Action.SUBMIT, other)
