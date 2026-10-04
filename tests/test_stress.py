"""Fast CI smoke test for scenario stress testing and invariants (§11, §33)."""

from __future__ import annotations

import pytest

from backend.travel import connect as connect_travel
from scripts.run_stress_tests import (
    REFERENCE_SEED,
    build_v4_stratified_matrix,
    build_v5_stress_matrix,
    deterministic_scenario_fingerprint,
    generate_scenario_data,
    run_single_stress_test,
    verify_invariants,
)


def test_quick_synthetic_stress_scenario_invariants(tmp_path) -> None:
    """Run a fast small scenario (16 areas, 3 providers, variant A) with tight time limit."""
    record = run_single_stress_test(
        num_areas=16,
        num_providers=3,
        variant="A",
        seed=REFERENCE_SEED,
        temp_dir=tmp_path,
        max_solver_seconds=1.5,
    )
    assert record["status"] == "PASS", f"Stress invariants violated: {record['violations']}"
    assert record["invariants_passed"] is True
    assert record["budget_spent_won"] <= record["budget_won"]
    assert record["covered_areas"] > 0
    assert record["solver_status"] in {"OPTIMAL", "FEASIBLE", "TIME_LIMIT"}
    assert record["candidate_round_count"] > 0
    assert len(record["deterministic_fingerprint"]) == 64
    assert record["status"] == "PASS"


@pytest.mark.parametrize(
    ("variant", "expected_missing_rate", "unavailable_count"),
    [
        ("A", 0.0, 0),
        ("B", 0.0, 0),
        ("C", 0.0, 0),
        ("D", 0.0, 0),
        ("E", 0.0, 0),
        ("F", 0.0, 0),
        ("G", 0.05, 0),
        ("H", 0.20, 0),
        ("I", 0.0, 1),
        ("J", 0.0, 2),
    ],
)
def test_synthetic_variants_apply_requested_failure_modes(
    tmp_path, variant: str, expected_missing_rate: float, unavailable_count: int
) -> None:
    areas, providers, connection, _budget, _policy, fallback_allowed, metadata = (
        generate_scenario_data(16, 3, variant, REFERENCE_SEED, tmp_path / f"{variant}.sqlite")
    )
    try:
        expected_missing = round(16 * 15 * expected_missing_rate)
        assert metadata["route_missing_edges"] == expected_missing
        assert len(metadata["unavailable_provider_ids"]) == unavailable_count
        assert fallback_allowed is (variant in {"G", "H"})
        if variant == "D":
            assert all(len(provider["availability"]) == 1 for provider in providers)
            assert all(area["requested_service_windows"] for area in areas)
        if variant == "E":
            normal, _, normal_connection, _, _, _, _ = generate_scenario_data(
                16, 3, "A", REFERENCE_SEED, tmp_path / "normal.sqlite"
            )
            try:
                assert sum(area["simulated_monthly_demand"] for area in areas) > sum(
                    area["simulated_monthly_demand"] for area in normal
                )
            finally:
                normal_connection.close()
        if variant == "F":
            assert metadata["low_data_area_count"] >= 8
    finally:
        connection.close()


def test_scenario_input_fingerprint_is_deterministic_and_route_sensitive(tmp_path) -> None:
    fingerprints = []
    for suffix, variant in (("first", "A"), ("second", "A"), ("changed", "G")):
        areas, providers, connection, budget, policy, _fallback, _metadata = generate_scenario_data(
            16, 3, variant, REFERENCE_SEED, tmp_path / f"{suffix}.sqlite"
        )
        try:
            fingerprints.append(
                deterministic_scenario_fingerprint(
                    areas,
                    providers,
                    budget,
                    policy,
                    connection,
                    seed=REFERENCE_SEED,
                    variant=variant,
                )
            )
        finally:
            connection.close()
    assert fingerprints[0] == fingerprints[1]
    assert fingerprints[0] != fingerprints[2]


def test_v4_stress_matrix_is_deterministic_and_stratified() -> None:
    first = build_v4_stratified_matrix()
    second = build_v4_stratified_matrix()
    assert first == second
    assert len(first) == 100
    assert len({seed for _areas, _providers, seed, _profile in first}) == 100
    assert {areas: sum(row[0] == areas for row in first) for areas in (16, 30, 50, 100, 200)} == {
        16: 20, 30: 20, 50: 20, 100: 20, 200: 20,
    }
    providers_per_stratum = {
        providers: sum(row[1] == providers for row in first)
        for providers in (3, 5, 10, 20)
    }
    assert providers_per_stratum == {
        3: 25, 5: 25, 10: 25, 20: 25,
    }


def test_v5_stress_matrix_is_180_deterministic_cases_with_new_profiles() -> None:
    first = build_v5_stress_matrix()
    second = build_v5_stress_matrix()
    assert first == second
    assert len(first) == 180
    names = {profile["name"] for _areas, _providers, _seed, profile in first}
    assert {
        "MASS_PROVIDER_DECLINE_REMOTE", "HOME_REPAIR_HIGH_UNIT_COST",
        "HUB_COMPATIBLE_DAILY_SERVICE", "ROUTE_LOSS_STALE_LOW_DATA",
    } <= names


def test_v4_stress_profile_keeps_zero_budget_low_data_and_wrong_service_explicit(tmp_path) -> None:
    profile = {
        "name": "ADVERSARIAL_ZERO",
        "budget_tier": "zero",
        "participation_rate": 0.0,
        "route_missing_rate": 0.0,
        "low_data_rate": 1.0,
        "wrong_service_only": True,
    }
    areas, providers, connection, budget, _policy, _fallback, metadata = generate_scenario_data(
        16, 3, "A", REFERENCE_SEED, tmp_path / "adversarial.sqlite", profile=profile
    )
    try:
        assert budget == 0
        assert all(area["needs_survey"] for area in areas)
        assert all(provider["provider_unavailable"] for provider in providers)
        assert all(
            provider["supported_services"] == ["unrelated_service"] for provider in providers
        )
        assert metadata["matrix_profile"] == "ADVERSARIAL_ZERO"
        assert metadata["observed_participation_rate"] == 0.0
        assert metadata["low_data_area_count"] == len(areas)
    finally:
        connection.close()


def test_invariant_checker_detects_unsafe_schedule_results(tmp_path) -> None:
    connection = connect_travel(tmp_path / "invariant.sqlite")
    area = {
        "id": "area-1",
        "service_type": "daily_necessities",
        "simulated_monthly_demand": 1,
    }
    provider = {
        "provider_id": "provider-1",
        "supported_services": ["laundry"],
        "service_capacity": 1,
        "max_monthly_rounds": 1,
        "max_daily_hours": 1,
        "provider_unavailable": True,
        "availability": [{"weekday": "monday", "start_time": "09:00", "end_time": "10:00"}],
    }
    result = {
        "budget_spent_won": 101,
        "served_units": 2,
        "rounds": [
            {
                "provider_id": "provider-1",
                "area_id": "area-1",
                "service_type": "daily_necessities",
                "scheduled_date": "2026-10-06",
                "departure_time": "10:00",
                "service_start_time": "10:00",
                "service_end_time": "11:00",
                "duration_minutes": 60,
                "service_units": 2,
                "travel_before_s": 60,
                "travel_after_s": 60,
                "travel_distance_m": -1,
                "travel_time_s": -1,
                "service_cost_won": -1,
                "travel_cost_won": 0,
                "minimum_compensation_topup_won": 0,
                "total_cost_won": -1,
            }
        ],
        "routes": [
            {
                "route_type": "HUB_ROUND_TRIP",
                "stops": [
                    {
                        "area_id": "area-1",
                        "incoming_from_area_id": "base-1",
                        "outgoing_to_area_id": "base-1",
                        "travel_before_distance_m": 1,
                        "travel_after_distance_m": 1,
                        "travel_before_s": 60,
                        "travel_after_s": 60,
                    }
                ],
            }
        ],
        "solver_status": "FEASIBLE",
        "optimality_proven": True,
        "time_limit_reached": True,
        "minimum_coverage_met": True,
        "unmet_minimum_frequency_areas": 1,
        "route_matrix_complete": False,
        "hub_fallback_group_count": 1,
    }
    try:
        report = verify_invariants(
            result,
            [area],
            [provider],
            100,
            connection,
            allow_route_fallback=False,
        )
    finally:
        connection.close()

    assert report["passed"] is False
    assert any("BUDGET_OUT_OF_RANGE" in item for item in report["violations"])
    assert any("SERVED_EXCEEDS_DEMAND" in item for item in report["violations"])
    assert any("UNSUPPORTED_SERVICE_ASSIGNMENT" in item for item in report["violations"])
    assert any("SERVICE_CAPACITY_EXCEEDED" in item for item in report["violations"])
    assert any("PROVIDER_UNAVAILABLE_ASSIGNED" in item for item in report["violations"])
    assert any("PROVIDER_AVAILABILITY_VIOLATION" in item for item in report["violations"])
    assert any("MISSING_ROAD_EDGE_USED" in item for item in report["violations"])
    assert "UNAUTHORIZED_HUB_FALLBACK" in report["violations"]
    assert any("SOLVER_STATUS_DISTORTION" in item for item in report["violations"])


def test_daily_work_invariant_counts_shared_multi_stop_legs_once(tmp_path) -> None:
    connection = connect_travel(tmp_path / "multi-stop-invariant.sqlite")
    provider = {
        "provider_id": "provider-1",
        "supported_services": ["laundry"],
        "service_capacity": 1,
        "max_monthly_rounds": 2,
        "max_daily_hours": 7,
        "availability": [{"weekday": "tuesday", "start_time": "08:00", "end_time": "18:00"}],
    }
    areas = [
        {"id": area_id, "service_type": "laundry", "simulated_monthly_demand": 1}
        for area_id in ("area-1", "area-2")
    ]
    rounds = [
        {
            "provider_id": "provider-1",
            "area_id": area_id,
            "service_type": "laundry",
            "scheduled_date": "2026-10-06",
            "departure_time": departure,
            "service_start_time": service_start,
            "service_end_time": service_end,
            "duration_minutes": 60,
            "service_units": 1,
            "travel_before_s": 5_400,
            "travel_after_s": 5_400,
            "route_group_key": "provider-1::2026-10-06",
        }
        for area_id, departure, service_start, service_end in (
            ("area-1", "08:00", "09:00", "10:00"),
            ("area-2", "10:00", "11:00", "12:00"),
        )
    ]
    result = {
        "budget_spent_won": 1,
        "served_units": 2,
        "rounds": rounds,
        "routes": [
            {
                "provider_id": "provider-1",
                "scheduled_date": "2026-10-06",
                "route_group_key": "provider-1::2026-10-06",
                "duration_s": 18_000,
                "stops": [],
            }
        ],
        "solver_status": "OPTIMAL",
        "optimality_proven": True,
        "time_limit_reached": False,
        "minimum_coverage_met": True,
        "unmet_minimum_frequency_areas": 0,
        "route_matrix_complete": True,
    }
    try:
        report = verify_invariants(
            result, areas, [provider], 10, connection, allow_route_fallback=False
        )
        assert report["passed"] is True, report["violations"]

        result["routes"][0]["duration_s"] = 18_360
        over_limit_report = verify_invariants(
            result, areas, [provider], 10, connection, allow_route_fallback=False
        )
        assert any("DAILY_WORK_LIMIT_EXCEEDED" in item for item in over_limit_report["violations"])
    finally:
        connection.close()
