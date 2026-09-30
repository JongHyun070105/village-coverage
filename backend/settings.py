"""Central, reviewable policy weights for prototype planning scenarios."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BalancedScenarioWeights:
    base: int = 100
    elderly_population_share: int = 90
    older_single_household_population_share: int = 45
    needs_survey: int = 35


BALANCED_SCENARIO_WEIGHTS = BalancedScenarioWeights()
