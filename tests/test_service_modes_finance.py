import pytest

from backend.public_finance import UNKNOWN, plan_cost_breakdown, public_finance_view
from backend.service_mode_comparison import ModeAssumptions, compare_service_modes, select_hubs
from backend.service_modes import SERVICE_ALLOWED_MODES

# Line of four villages, 10 minutes / 8 km apart; base at v0.
POSITIONS = {"v0": 0, "v1": 1, "v2": 2, "v3": 3}
AREAS = [
    {"id": "v0", "simulated_monthly_demand": 2, "facility_count": 1, "population_total": 100},
    {"id": "v1", "simulated_monthly_demand": 3, "facility_count": 0, "population_total": 80},
    {"id": "v2", "simulated_monthly_demand": 1, "facility_count": 2, "population_total": 60},
    {"id": "v3", "simulated_monthly_demand": 4, "facility_count": 0, "population_total": 120},
]


def road(a: str, b: str):
    steps = abs(POSITIONS[a] - POSITIONS[b])
    return (8_000 * steps, 600 * steps) if a != b else (0, 0)


def test_every_requested_mode_is_reported_without_a_winner():
    result = compare_service_modes(areas=AREAS, base_area_id="v0", road=road)
    assert set(result["modes"]) == {"HOME_VISIT", "VILLAGE_PICKUP", "MOBILE_SERVICE",
                                    "VILLAGE_HUB"}
    assert "우열을 판정하지 않습니다" in result["policy_note"]
    assert "best" not in str(result).lower()
    for mode in result["modes"].values():
        assert mode["served_units"] == 10
        assert mode["provenance"].startswith("MODEL ESTIMATE")


def test_home_visit_has_zero_resident_travel_but_most_vehicle_distance():
    modes = compare_service_modes(areas=AREAS, base_area_id="v0", road=road)["modes"]
    assert modes["HOME_VISIT"]["resident_travel_minutes_per_unit"] == 0
    assert modes["HOME_VISIT"]["vehicle_distance_km"] > modes["MOBILE_SERVICE"][
        "vehicle_distance_km"]


def test_hub_mode_uses_existing_public_facility_without_construction_cost():
    hub = compare_service_modes(areas=AREAS, base_area_id="v0", road=road)["modes"][
        "VILLAGE_HUB"]
    assert hub["hub"]["hub_area_ids"][0] in {"v0", "v2"}  # only areas with a facility
    assert hub["monthly_cost_breakdown_won"]["FIXED_INFRASTRUCTURE_COST"] == 0
    assert "SIMULATED" in hub["hub"]["facility_availability"]


def test_new_construction_cost_is_unknown_not_zero():
    hub = compare_service_modes(
        areas=AREAS, base_area_id="v0", road=road,
        assumptions=ModeAssumptions(existing_public_asset=False),
    )["modes"]["VILLAGE_HUB"]
    assert hub["unknown_cost_items"] == ["FIXED_INFRASTRUCTURE_COST"]
    assert hub["monthly_cost_won"] is None


def test_hub_selection_minimizes_demand_weighted_travel():
    best = select_hubs(AREAS, road, max_hubs=1)[0]
    assert best["hub_area_ids"] == ["v2"]  # closer to heavy-demand v1/v3 than v0


def test_missing_road_marks_pickup_unavailable():
    def broken(a, b):
        return None if "v3" in (a, b) and a != b else road(a, b)

    modes = compare_service_modes(areas=AREAS, base_area_id="v0", road=broken)["modes"]
    assert modes["VILLAGE_PICKUP"]["status"] == "UNAVAILABLE"
    assert modes["HOME_VISIT"]["unreachable_area_ids"] == ["v3"]


def test_service_mode_taxonomy_matches_v4_policy():
    assert SERVICE_ALLOWED_MODES["home_repair"] == ("HOME_VISIT",)
    assert set(SERVICE_ALLOWED_MODES["daily_necessities"]) == {"VILLAGE_HUB", "DELIVERY"}
    assert {"VILLAGE_PICKUP", "MOBILE_SERVICE", "HOME_VISIT"} <= set(
        SERVICE_ALLOWED_MODES["laundry"])


def test_unknown_support_is_never_treated_as_zero():
    view = public_finance_view(gross_cost_won=1_000_000, served_units=10)
    assert view["net_public_funding_need_won"] is None
    assert view["net_public_funding_status"] == "UPPER_BOUND_UNKNOWN_OFFSETS"
    assert view["user_fee_revenue_won"] == UNKNOWN
    assert view["existing_public_support_won"] == UNKNOWN


def test_fully_specified_scenario_gives_exact_net_need():
    view = public_finance_view(
        gross_cost_won=1_000_000, served_units=10, user_fee_per_unit_won=5_000,
        fee_exempt_share=0.4,
        funding={"CENTRAL_GOV_SUBSIDY": 200_000, "PUBLIC_PROGRAM": 100_000,
                 "COOPERATIVE_REVENUE": 0, "DONATION": 50_000, "SOCIAL_CONTRIBUTION": 0,
                 "OTHER": 0},
        cost_breakdown=plan_cost_breakdown({"service_cost_won": 700_000,
                                            "travel_cost_won": 300_000}),
    )
    assert view["user_fee_revenue_won"] == 30_000  # 6 paying units x 5,000
    assert view["existing_public_support_won"] == 300_000
    assert view["other_revenue_won"] == 50_000
    assert view["net_public_funding_need_won"] == 620_000
    assert view["sustainability"]["local_budget_dependency_ratio"] == 0.62
    labels = {row["category"]: row["amount_won"] for row in view["cost_breakdown"]}
    assert labels["SERVICE_EXECUTION_COST"] == 700_000 and labels["VEHICLE_COST"] == UNKNOWN


def test_invalid_finance_inputs_are_rejected():
    with pytest.raises(ValueError):
        public_finance_view(gross_cost_won=1, served_units=1, user_fee_per_unit_won=1,
                            fee_exempt_share=1.5)
    with pytest.raises(ValueError):
        public_finance_view(gross_cost_won=1, served_units=1, funding={"DONATION": -1})
