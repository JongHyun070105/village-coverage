"""Seeded synthetic pre-R&D operating inputs kept separate from public data."""

from __future__ import annotations

from random import Random
from typing import Any

REFERENCE_SEED = 2026
OBSERVATION_COUNTS = (1, 2, 3, 4, 6, 8)
SERVICE_TYPES = ("laundry", "daily_necessities", "home_repair")


def simulated_operating_profile(
    area: dict[str, Any], seed: int = REFERENCE_SEED
) -> dict[str, Any]:
    """Create reproducible demo demand and observation fields for one area.

    Seed 2026 preserves the submitted pilot inputs. Other seeds perturb only
    simulated observations, modeled need, and service category; public fields
    such as population, household counts, facilities, and coordinates remain
    untouched.
    """
    area_id = str(area["id"])
    stable = int(area_id[-3:])
    population = max(int(area.get("population_total") or 0), 1)
    elderly_share = float(area.get("elderly_ratio_65") or 0)
    household_share = int(area.get("single_households_total") or 0) / population
    base_demand = max(3, min(12, round(3 + elderly_share * 7 + household_share * 5)))

    if seed == REFERENCE_SEED:
        observation_count = OBSERVATION_COUNTS[(stable + seed) % len(OBSERVATION_COUNTS)]
        demand_units = max(2, base_demand + ((stable * 17 + seed) % 5) - 2)
        service_type = SERVICE_TYPES[stable % len(SERVICE_TYPES)]
    else:
        random = Random(f"{seed}:{area_id}")
        observation_count = random.choice(OBSERVATION_COUNTS)
        demand_units = max(2, base_demand + random.randint(-2, 2))
        service_type = random.choice(SERVICE_TYPES)

    return {
        "demand_observation_count": observation_count,
        "demand_data_count": observation_count,
        "demand_confidence": "조사 필요"
        if observation_count < 4
        else "주의"
        if observation_count < 7
        else "충분",
        "needs_survey": observation_count < 4,
        "simulated_monthly_demand": demand_units,
        "service_type": service_type,
    }


def simulated_providers_for_seed(
    providers: list[dict[str, Any]], seed: int = REFERENCE_SEED
) -> list[dict[str, Any]]:
    """Vary synthetic monthly capacity for robustness runs, preserving seed 2026."""
    if seed == REFERENCE_SEED:
        return [dict(provider) for provider in providers]
    random = Random(f"provider-capacity:{seed}")
    return [
        {**provider, "capacity_per_month": random.randint(30, 60)}
        for provider in providers
    ]
