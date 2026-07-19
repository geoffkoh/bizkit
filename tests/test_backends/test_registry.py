"""Backend registry, lazy driver discipline, and the type map (spec D3/D4)."""

from typing import ClassVar

import pytest

from bizkit.backends.base import BaseBackend
from bizkit.backends.registry import available_backends, get_backend_class
from bizkit.backends.typemap import CANONICAL_TYPES, to_canonical, to_dialect
from bizkit.exceptions import (
    BackendNotInstalledError,
    BizkitError,
    UnknownBackendError,
)

ALL_BACKENDS = [
    "oracle",
    "mssql",
    "mysql",
    "percona",
    "postgres",
    "snowflake",
    "databricks",
    "sqlite",  # dev-only demo backend (D39)
]


def test_all_backends_registered() -> None:
    assert available_backends() == sorted(ALL_BACKENDS)


def test_unknown_backend_raises() -> None:
    with pytest.raises(UnknownBackendError):
        get_backend_class("nope")


@pytest.mark.parametrize("name", ALL_BACKENDS)
def test_backend_classes_import_without_drivers(name: str) -> None:
    backend_class = get_backend_class(name)
    assert issubclass(backend_class, BaseBackend)


def test_percona_rides_mysql() -> None:
    assert get_backend_class("percona") is get_backend_class("mysql")


def test_missing_driver_names_the_extra() -> None:
    class FakeBackend(BaseBackend):
        name: ClassVar[str] = "fake"
        extra: ClassVar[str] = "fake-extra"
        driver_module: ClassVar[str] = "definitely_not_a_real_module"

    backend = FakeBackend("sqlite:///ignored.db")
    with pytest.raises(BackendNotInstalledError, match=r"bizkit\[fake-extra\]"):
        _ = backend.engine


@pytest.mark.parametrize("backend", ALL_BACKENDS)
@pytest.mark.parametrize("canonical", sorted(CANONICAL_TYPES))
def test_typemap_is_bidirectional(backend: str, canonical: str) -> None:
    dialect = to_dialect(canonical, backend)
    assert to_canonical(dialect, backend) == canonical


def test_typemap_unknown_inputs() -> None:
    with pytest.raises(UnknownBackendError):
        to_dialect("string", "nope")
    with pytest.raises(BizkitError):
        to_dialect("blob", "postgres")
    with pytest.raises(BizkitError):
        to_canonical("GEOGRAPHY", "postgres")
