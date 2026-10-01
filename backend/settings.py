"""Central, reviewable policy priorities for prototype planning scenarios."""

from dataclasses import dataclass

DEFAULT_ALLOWED_SERVICES = ("laundry", "daily_necessities", "home_repair")


@dataclass(frozen=True)
class PlanningPolicy:
    """Explicit values chosen by the planner; these are not AI-selected weights."""

    minimum_services_per_area: int = 1
    elderly_priority_weight: int = 500
    single_elderly_household_priority_weight: int = 500
    survey_required_protection_weight: int = 1000
    maximum_round_trip_travel_minutes: int | None = None
    allowed_services: tuple[str, ...] = DEFAULT_ALLOWED_SERVICES
    minimum_provider_compensation_won: int = 0


@dataclass(frozen=True)
class BalancedScenarioWeights:
    vulnerability_points_per_share: int = 500
    concentration_basis_points: int = 10_000


BALANCED_SCENARIO_WEIGHTS = BalancedScenarioWeights()
