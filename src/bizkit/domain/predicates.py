"""Named predicates referenced by :class:`~bizkit.domain.validation.CrossFieldRule`.

Rule sets are declarative data (spec D11): a workspace file names a
predicate by id, it never carries code. This module is the registry those
ids resolve against, so the set of expressible checks is fixed at release
time and reviewable — an unknown id is a validation issue, not an import
of arbitrary behaviour.

Predicates receive the row values for the rule's declared columns, in the
declared order, and answer whether the row passes.
"""

from collections.abc import Callable, Sequence
from datetime import date
from typing import Final

Predicate = Callable[[Sequence[object]], bool]


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _pair_is_6_uppercase(values: Sequence[object]) -> bool:
    """A currency pair is exactly six uppercase ASCII letters (e.g. EURUSD)."""
    pair = _text(values[0] if values else None)
    return len(pair) == 6 and pair.isascii() and pair.isalpha() and pair.isupper()


def _date_is_iso(values: Sequence[object]) -> bool:
    """The value parses as an ISO-8601 calendar date (YYYY-MM-DD)."""
    raw = _text(values[0] if values else None)
    try:
        date.fromisoformat(raw)
    except ValueError:
        return False
    # fromisoformat accepts YYYYMMDD too; the rule means the dashed form.
    return len(raw) == 10


def _isin_is_valid(values: Sequence[object]) -> bool:
    """A 12-character ISIN with a valid Luhn check digit."""
    isin = _text(values[0] if values else None).upper()
    if len(isin) != 12 or not isin[:2].isalpha() or not isin.isalnum():
        return False
    # Expand letters to their two-digit ordinals, then Luhn over the digits.
    digits = "".join(
        str(ord(char) - ord("A") + 10) if char.isalpha() else char for char in isin
    )
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _all_present(values: Sequence[object]) -> bool:
    """Every declared column carries a non-empty value."""
    return all(_text(value).strip() != "" for value in values)


def _strictly_increasing(values: Sequence[object]) -> bool:
    """Declared columns are in strictly ascending order (e.g. min < max)."""
    try:
        numbers = [float(_text(value)) for value in values]
    except ValueError:
        return False
    return all(a < b for a, b in zip(numbers, numbers[1:], strict=False))


PREDICATES: Final[dict[str, Predicate]] = {
    "pair-is-6-uppercase": _pair_is_6_uppercase,
    "date-is-iso": _date_is_iso,
    "isin-is-valid": _isin_is_valid,
    "all-present": _all_present,
    "strictly-increasing": _strictly_increasing,
}
"""Registered predicate ids. Adding one is a reviewed code change."""


def lookup(predicate_id: str) -> Predicate | None:
    """Resolve a predicate id, or ``None`` when it is not registered."""
    return PREDICATES.get(predicate_id)
