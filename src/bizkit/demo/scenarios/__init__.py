"""Registry of named demo scenarios (spec D45).

Adding a scenario is a new module here plus one row in `SCENARIOS`; the CLI
picks it up with no change, since `--scenario` reads its choices from this
mapping.
"""

from typing import Final

from bizkit.demo.model import Scenario
from bizkit.demo.scenarios import enterprise, sample

SAMPLE: Final[Scenario] = Scenario(
    name="sample",
    summary=(
        "One target, 5 tables, 8 changesets — every state reachable without "
        "touching the target. The small default."
    ),
    targets={"sample": sample.TABLES},
    workspace=sample.workspace,
    populate=sample.populate,
)

ENTERPRISE: Final[Scenario] = Scenario(
    name="enterprise",
    summary=(
        "Two targets, 8 tables, 10 changesets — cross-table (incl. "
        "cross-backend) rules, a real APPLIED and FAILED, a rework at "
        "revision 2, and narrowly scoped grants."
    ),
    targets={"risk": enterprise.RISK_TABLES, "crm": enterprise.CRM_TABLES},
    workspace=enterprise.workspace,
    populate=enterprise.populate,
)

SCENARIOS: Final[dict[str, Scenario]] = {
    SAMPLE.name: SAMPLE,
    ENTERPRISE.name: ENTERPRISE,
}
"""Every seedable scenario, keyed by its `--scenario` value."""

DEFAULT_SCENARIO: Final[str] = SAMPLE.name


def get_scenario(name: str) -> Scenario:
    """Look up a scenario by name.

    Raises:
        KeyError: If no scenario is registered under that name.
    """
    return SCENARIOS[name]
