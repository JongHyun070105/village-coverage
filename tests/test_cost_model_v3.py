import pytest

from backend import cost_model_v3
from backend.cost_model_v3 import UNKNOWN, funding_gap, plan_cost_model


def make_round(**overrides):
    row = {
        "provider_id": "p1", "area_id": "a1", "scheduled_date": "2026-06-03",
        "service_units": 2, "service_cost_won": 510_000,
        "travel_before_s": 1200, "travel_after_s": 1200, "travel_distance_m": 8000,
        "travel_cost_won": 14_400 + 13_334, "minimum_compensation_topup_won": 0,
    }
    row.update(overrides)
    return row


def test_unprovided_components_stay_unknown_and_not_zero() -> None:
    model = plan_cost_model([make_round()])
    by_key = {c["component"]: c["amount_won"] for c in model["components"]}
    for key in ("SETUP", "MATERIAL", "VEHICLE", "FIXED_PARTICIPATION"):
        assert by_key[key] == UNKNOWN
    assert model["cost_status"] == "AT_LEAST_KNOWN_FLOOR"
    assert model["total_cost_won"] is None
    assert model["known_cost_floor_won"] == sum(
        v for v in by_key.values() if v != UNKNOWN
    )


def test_travel_splits_into_distance_and_time_with_residual_reported() -> None:
    model = plan_cost_model([make_round()])
    item = model["rounds"][0]["components"]
    assert item["TRAVEL_DISTANCE"] == 14_400
    assert item["TRAVEL_TIME"] == 13_334
    assert model["travel_reconciliation_residual_won"] == 0
    drift = plan_cost_model([make_round(travel_cost_won=30_000)])
    assert drift["travel_reconciliation_residual_won"] == 30_000 - 14_400 - 13_334


def test_full_assumptions_give_exact_total() -> None:
    assumptions = {
        "setup_per_round_won": 5_000, "material_per_unit_won": 3_000,
        "vehicle_per_round_won": 7_000, "fixed_participation_per_provider_month_won": 10_000,
    }
    rounds = [make_round(), make_round(scheduled_date="2026-06-10"),
              make_round(provider_id="p2")]
    model = plan_cost_model(rounds, assumptions, minimum_compensation_topup_won=4_000)
    assert model["cost_status"] == "EXACT"
    assert model["provider_months_with_service"] == 2
    parts = {c["component"]: c["amount_won"] for c in model["components"]}
    assert parts["SETUP"] == 15_000 and parts["MATERIAL"] == 18_000
    assert parts["VEHICLE"] == 21_000 and parts["FIXED_PARTICIPATION"] == 20_000
    assert model["total_cost_won"] == sum(parts.values())


def test_explicit_zero_is_known_zero_not_unknown() -> None:
    model = plan_cost_model([make_round()], {"setup_per_round_won": 0})
    parts = {c["component"]: c["amount_won"] for c in model["components"]}
    assert parts["SETUP"] == 0


def test_invalid_assumption_rejected() -> None:
    with pytest.raises(ValueError):
        plan_cost_model([make_round()], {"setup_per_round_won": -1})
    with pytest.raises(ValueError):
        plan_cost_model([make_round()], {"vehicle_per_round_won": True})


def exact_model():
    return plan_cost_model(
        [make_round()],
        {"setup_per_round_won": 0, "material_per_unit_won": 0, "vehicle_per_round_won": 0,
         "fixed_participation_per_provider_month_won": 0},
    )


def test_gap_exact_when_costs_and_funding_known() -> None:
    model = exact_model()
    floor = model["known_cost_floor_won"]
    gap = funding_gap(model, budget_won=floor - 1000)
    assert gap["status"] == "EXACT" and gap["gap_won"] == 1000
    assert funding_gap(model, budget_won=floor + 5)["gap_won"] == 0


def test_unknown_costs_never_produce_a_point_gap() -> None:
    model = plan_cost_model([make_round()])
    gap = funding_gap(model, budget_won=model["known_cost_floor_won"] + 1)
    assert gap["status"] == "LOWER_BOUND_UNKNOWN_COSTS"
    assert gap["gap_won"] is None and gap["gap_at_most_won"] is None
    assert gap["gap_at_least_won"] == 0
    assert gap["unknown_cost_components"]
    short = funding_gap(model, budget_won=0)
    assert short["gap_at_least_won"] == model["known_cost_floor_won"]


def test_unknown_funding_gives_upper_bound_only() -> None:
    model = exact_model()
    gap = funding_gap(model, budget_won=0, other_funding={"CENTRAL_GOV_SUBSIDY": UNKNOWN})
    assert gap["status"] == "UPPER_BOUND_UNKNOWN_FUNDING"
    assert gap["gap_won"] is None and gap["gap_at_least_won"] is None
    assert gap["gap_at_most_won"] == model["known_cost_floor_won"]
    assert gap["unknown_funding_sources"] == ["CENTRAL_GOV_SUBSIDY"]


def test_unknown_on_both_sides_has_no_bound() -> None:
    model = plan_cost_model([make_round()])
    gap = funding_gap(model, budget_won=0, other_funding={"DONATION": None})
    assert gap["status"] == "UNKNOWN_BOTH_SIDES"
    assert gap["gap_won"] is None
    assert gap["gap_at_least_won"] is None and gap["gap_at_most_won"] is None


def test_negative_funding_rejected() -> None:
    with pytest.raises(ValueError):
        funding_gap(exact_model(), budget_won=-1)
    with pytest.raises(ValueError):
        funding_gap(exact_model(), budget_won=1, other_funding={"DONATION": -1})


def test_model_is_deterministic() -> None:
    rounds = [make_round(), make_round(provider_id="p2")]
    assert plan_cost_model(rounds) == plan_cost_model(rounds)
    assert cost_model_v3.MODEL_VERSION == "COST_MODEL_V3"


def test_api_cost_model_for_stored_schedule(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from backend.main import app

    monkeypatch.setenv("VILLAGECOVERAGE_APP_DB", str(tmp_path / "cost.sqlite"))
    client = TestClient(app)
    created = client.post("/api/schedules", json={"scenario": "efficiency",
                                                  "budget_won": 5_000_000})
    assert created.status_code == 201, created.text
    schedule_id = created.json()["schedule_id"]
    response = client.post(f"/api/schedules/{schedule_id}/cost-model-v3", json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cost_model"]["cost_status"] == "AT_LEAST_KNOWN_FLOOR"
    assert body["funding_gap"]["gap_won"] is None
    assert body["funding_gap"]["status"] == "LOWER_BOUND_UNKNOWN_COSTS"
    bad = client.post(f"/api/schedules/{schedule_id}/cost-model-v3",
                      json={"setup_per_round_won": -5})
    assert bad.status_code == 422
    assert client.post("/api/schedules/nope/cost-model-v3", json={}).status_code == 404
