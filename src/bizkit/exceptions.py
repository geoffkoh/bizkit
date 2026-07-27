"""Custom exception hierarchy for bizkit.

Every error raised by bizkit derives from :class:`BizkitError`; callers can
catch that one type to handle any library failure. Never raise bare
``Exception`` from bizkit code.
"""


class BizkitError(Exception):
    """Base class for all bizkit errors."""


class ChangesetStateError(BizkitError):
    """An illegal changeset state transition was attempted."""


class ApprovalError(BizkitError):
    """An approval rule was violated (e.g. maker checking their own change)."""


class AccessDeniedError(BizkitError):
    """The actor lacks the required grant for the attempted action."""


class ValidationFailedError(BizkitError):
    """A changeset failed validation and the requested action is blocked.

    Carries the structured report so delivery layers can render the issues
    rather than only the summary message.
    """

    def __init__(self, message: str, report: object | None = None) -> None:
        super().__init__(message)
        self.report = report


class ChangesetLimitError(BizkitError):
    """A changeset would exceed the effective ``max_changeset_items`` cap."""


class UnknownBackendError(BizkitError):
    """A target backend name is not registered."""


class BackendNotInstalledError(BizkitError):
    """A target backend's optional driver is not installed."""


class ApplyError(BizkitError):
    """Applying an approved changeset to the target database failed."""


class StoreError(BizkitError):
    """The workflow metadata store could not complete an operation."""


class StoreSchemaError(StoreError):
    """The store's schema revision does not match the code's (spec D46).

    Raised instead of migrating implicitly: bizkit never upgrades a store as
    a side effect of starting up.
    """


class ConcurrencyError(BizkitError):
    """An optimistic-lock conflict: another writer changed the changeset first."""


class ConfigError(BizkitError):
    """The workspace configuration file is invalid or unresolvable."""
