from scripts.run_stress_tests import verify_invariants


class _EmptyTravelMatrix:
    def execute(self, _query):
        return self

    def fetchall(self):
        return []


def _round(area_id: str, scheduled_date: str) -> dict[str, object]:
    return {
        "provider_id": "provider-1",
        "area_id": area_id,
        "service_type": "laundry",
        "service_units": 1,
        "service_cost_won": 0,
        "travel_cost_won": 0,
        "minimum_compensation_topup_won": 0,
        "total_cost_won": 0,
        "travel_distance_m": 0,
        "travel_time_s": 0,
        "scheduled_date": scheduled_date,
        "departure_time": "09:00",
        "service_start_time": "09:00",
        "service_end_time": "09:30",
        "travel_before_s": 0,
        "travel_after_s": 0,
        "duration_minutes": 30,
    }


def _verify(rounds: list[dict[str, object]]) -> dict[str, object]:
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday")
    areas = [
        {"id": str(item["area_id"]), "simulated_monthly_demand": 1}
        for item in rounds
    ]
    providers = [
        {
            "provider_id": "provider-1",
            "supported_services": ["laundry"],
            "service_capacity": 1,
            "max_monthly_rounds": 1,
            "max_daily_hours": 8,
            "availability": [
                {"weekday": day, "start_time": "08:00", "end_time": "18:00"}
                for day in weekdays
            ],
        }
    ]
    result = {
        "budget_spent_won": 0,
        "served_units": len(rounds),
        "rounds": rounds,
        "routes": [],
        "solver_status": "OPTIMAL",
        "optimality_proven": True,
        "time_limit_reached": False,
        "minimum_coverage_met": True,
        "unmet_minimum_frequency_areas": 0,
    }
    return verify_invariants(
        result, areas, providers, 0, _EmptyTravelMatrix(), allow_route_fallback=False
    )


def test_monthly_capacity_is_counted_per_calendar_month():
    rounds = [
        _round("area-oct", "2026-10-30"),
        _round("area-nov", "2026-11-02"),
    ]

    result = _verify(rounds)

    assert result["passed"], result["violations"]


def test_monthly_capacity_overage_in_one_month_is_detected():
    rounds = [
        _round("area-a", "2026-10-29"),
        _round("area-b", "2026-10-30"),
    ]

    result = _verify(rounds)

    assert result["passed"] is False
    assert result["violations"] == [
        "PROVIDER_MONTHLY_CAPACITY_EXCEEDED: provider-1 assigned 2 in 2026-10 > 1"
    ]
