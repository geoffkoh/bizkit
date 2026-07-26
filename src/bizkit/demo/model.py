"""Types a demo scenario is built from.

A scenario is deliberately split into *declarative* parts (the target
tables and the workspace config) and one *scripted* part (the changeset
history). Target schemas and rule sets are data because that is what they
are; a workflow history is a sequence of authorized service calls whose
order carries the meaning, so expressing it as data would only reinvent the
service API with less clarity.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from bizkit.domain.table import TableRef

if TYPE_CHECKING:  # pragma: no cover - typing only
    from bizkit.services.comments import CommentService
    from bizkit.services.workflow import WorkflowService


@dataclass(frozen=True)
class TargetTable:
    """One table to create in a demo target database.

    Attributes:
        name: Table name.
        ddl: Full `CREATE TABLE IF NOT EXISTS …` statement.
        columns: Column order matching each tuple in `rows`.
        rows: Seed rows inserted with `INSERT OR REPLACE`.

    Rows a *pending* changeset inserts must be absent here, or applying it
    trips the primary key; rows a pending update targets must be present.
    Scenario tests assert exactly that, because before apply existed
    (spec D44) the inconsistency was invisible.
    """

    name: str
    ddl: str
    columns: Sequence[str] = ()
    rows: Sequence[tuple[object, ...]] = ()


@dataclass
class SeedContext:
    """What a scenario's `populate` callable gets to work with.

    Attributes:
        workflow: Fully-wired service (registry, grants, backend resolver),
            so `apply` works and validation runs at submit.
        comments: Comment service sharing the same session.
        refs: Table references by `(backend, table)` for convenience.
        notes: Human-readable lines describing what was seeded; the runner
            prints them.
    """

    workflow: "WorkflowService"
    comments: "CommentService"
    refs: dict[tuple[str, str], TableRef]
    notes: list[str] = field(default_factory=list)

    def ref(self, backend: str, table: str) -> TableRef:
        """The `TableRef` for a seeded table."""
        return self.refs[(backend, table)]

    def note(self, line: str) -> None:
        """Record a line for the runner's summary."""
        self.notes.append(line)


@dataclass(frozen=True)
class Scenario:
    """A named, runnable demo dataset.

    Attributes:
        name: Value accepted by `--scenario`.
        summary: One-line description shown by `--list-scenarios`.
        targets: Target database name → the tables it holds. The key becomes
            both the SQLite filename stem and the target profile name in the
            workspace config.
        workspace: Builds the workspace dict given the store URL and the
            resolved `{profile: path}` mapping.
        populate: Scripts the changeset history through the services.
    """

    name: str
    summary: str
    targets: dict[str, Sequence[TargetTable]]
    workspace: Callable[[str, dict[str, Path]], dict[str, object]]
    populate: Callable[[SeedContext], None]


@dataclass(frozen=True)
class SeedResult:
    """What a seeding run produced, for the caller to report.

    Attributes:
        scenario: The scenario's name.
        workspace_path: Where the workspace config was written.
        target_paths: Profile name → target database file.
        notes: Lines contributed by the scenario's `populate`.
    """

    scenario: str
    workspace_path: Path
    target_paths: dict[str, Path]
    notes: Sequence[str]
