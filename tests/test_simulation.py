from __future__ import annotations

import json
from pathlib import Path

from backend.simulation import (
    REFERENCE_SEED,
    simulated_operating_profile,
    simulated_providers_for_seed,
)

ROOT = Path(__file__).resolve().parents[1]


def test_reference_seed_keeps_the_checked_in_pre_rnd_profiles() -> None:
    demo = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    profile_fields = (
        "demand_observation_count",
        "demand_data_count",
        "demand_confidence",
        "needs_survey",
        "simulated_monthly_demand",
        "service_type",
    )
    for area in demo["areas"]:
        simulated = simulated_operating_profile(area, REFERENCE_SEED)
        assert {field: area[field] for field in profile_fields} == simulated
    assert simulated_providers_for_seed(demo["providers"], REFERENCE_SEED) == demo["providers"]


def test_synthetic_seed_profiles_are_reproducible_and_perturbed() -> None:
    demo = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    area = demo["areas"][0]
    seed_profiles = [simulated_operating_profile(area, seed) for seed in range(2026, 2047)]
    assert seed_profiles == [simulated_operating_profile(area, seed) for seed in range(2026, 2047)]
    assert len({profile["demand_observation_count"] for profile in seed_profiles}) > 1
    assert len({profile["simulated_monthly_demand"] for profile in seed_profiles}) > 1
    assert len({profile["service_type"] for profile in seed_profiles}) > 1

    providers = demo["providers"]
    generated = simulated_providers_for_seed(providers, 2027)
    assert generated == simulated_providers_for_seed(providers, 2027)
    assert all(30 <= provider["capacity_per_month"] <= 60 for provider in generated)
