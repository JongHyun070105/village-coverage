"""Central, reviewable policy priorities for prototype planning scenarios."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BalancedScenarioWeights:
    vulnerability_points_per_share: int = 500
    concentration_basis_points: int = 10_000


BALANCED_SCENARIO_WEIGHTS = BalancedScenarioWeights()
