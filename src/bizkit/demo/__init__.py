"""Demo/dev seeding — named scenarios that build a runnable bizkit workspace.

**Dev tooling, not production code.** Nothing here runs in a real
deployment: seeding writes a workspace config file, creates a SQLite
*target* database (the `sqlite` demo backend, spec D39), and drives
`WorkflowService`/`CommentService` to produce changesets in every lifecycle
state so the CLI, API, and SPA all have something real to work against.

This lives outside `cli/` deliberately (spec D45). It is a *consumer* of
services, so it sits at the same layer as `api/` and `cli/` rather than
inside either: the CLI is meant to be a thin delivery layer, and a seeder
that authors DDL and scripts a workflow history is neither thin nor a
delivery concern. Keeping it here also makes scenarios reusable — tests and
future demo surfaces can seed without going through the CLI.

Scenarios never bypass the workflow. Every changeset is created and
transitioned through `WorkflowService`, so the seeded history obeys the
same invariants as production: four-eyes, revision binding, exactly one
audit event per transition, and validation at submit.
"""

from bizkit.demo.model import Scenario, SeedContext, SeedResult, TargetTable
from bizkit.demo.runner import seed
from bizkit.demo.scenarios import SCENARIOS, DEFAULT_SCENARIO, get_scenario

__all__ = [
    "DEFAULT_SCENARIO",
    "SCENARIOS",
    "Scenario",
    "SeedContext",
    "SeedResult",
    "TargetTable",
    "get_scenario",
    "seed",
]
