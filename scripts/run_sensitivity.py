#!/usr/bin/env python3
"""Run provider and policy sensitivity analysis (§15, §16).

Outputs:
  artifacts/provider_sensitivity.json
  artifacts/policy_sensitivity.json
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.sensitivity import (  # noqa: E402
    run_policy_sensitivity_analysis,
    run_provider_participation_sensitivity,
)
from backend.travel import Route, connect, put_cached  # noqa: E402


def build_sensitivity_fixture(db_path: Path):
    connection = connect(db_path)
    base = {"id": "base-p1", "anchor_lat": 36.50, "anchor_lng": 126.65}
    base2 = {"id": "base-p2", "anchor_lat": 36.52, "anchor_lng": 126.63}

    # 6 Areas with distinct demographics and services
    areas = [
        {
            "id": "area-01",
            "name": "도산리",
            "service_type": "laundry",
            "simulated_monthly_demand": 2,
            "population_total": 120,
            "elderly_ratio_65": 0.45,
            "single_households_65_plus": 18,
            "needs_survey": False,
            "anchor_lat": 36.53,
            "anchor_lng": 126.68,
        },
        {
            "id": "area-02",
            "name": "광성리",
            "service_type": "daily_necessities",
            "simulated_monthly_demand": 3,
            "population_total": 85,
            "elderly_ratio_65": 0.52,
            "single_households_65_plus": 22,
            "needs_survey": True,
            "anchor_lat": 36.56,
            "anchor_lng": 126.61,
        },
        {
            "id": "area-03",
            "name": "화계리",
            "service_type": "laundry",
            "simulated_monthly_demand": 2,
            "population_total": 160,
            "elderly_ratio_65": 0.38,
            "single_households_65_plus": 14,
            "needs_survey": False,
            "anchor_lat": 36.48,
            "anchor_lng": 126.70,
        },
        {
            "id": "area-04",
            "name": "석성리",
            "service_type": "home_repair",
            "simulated_monthly_demand": 1,
            "population_total": 70,
            "elderly_ratio_65": 0.60,
            "single_households_65_plus": 25,
            "needs_survey": True,
            "anchor_lat": 36.45,
            "anchor_lng": 126.62,
        },
        {
            "id": "area-05",
            "name": "임천리",
            "service_type": "daily_necessities",
            "simulated_monthly_demand": 2,
            "population_total": 110,
            "elderly_ratio_65": 0.42,
            "single_households_65_plus": 15,
            "needs_survey": False,
            "anchor_lat": 36.55,
            "anchor_lng": 126.72,
        },
        {
            "id": "area-06",
            "name": "구룡리",
            "service_type": "laundry",
            "simulated_monthly_demand": 2,
            "population_total": 95,
            "elderly_ratio_65": 0.48,
            "single_households_65_plus": 19,
            "needs_survey": False,
            "anchor_lat": 36.49,
            "anchor_lng": 126.58,
        },
    ]

    # 3 Providers with realistic constraints
    providers = [
        {
            "provider_id": "provider-laundry-main",
            "name": "행복세탁",
            "base_area_id": "base-p1",
            "supported_services": ["laundry"],
            "availability": [
                {"weekday": "monday", "start_time": "09:00", "end_time": "18:00"},
                {"weekday": "wednesday", "start_time": "09:00", "end_time": "18:00"},
                {"weekday": "friday", "start_time": "09:00", "end_time": "18:00"},
            ],
            "max_monthly_rounds": 6,
            "service_capacity": 3,
            "max_daily_hours": 7.0,
            "max_travel_time_minutes": 80,
            "minimum_compensation_won": 1_000_000,
        },
        {
            "provider_id": "provider-goods-express",
            "name": "희망생필품유통",
            "base_area_id": "base-p2",
            "supported_services": ["daily_necessities"],
            "availability": [
                {"weekday": "tuesday", "start_time": "09:00", "end_time": "18:00"},
                {"weekday": "thursday", "start_time": "09:00", "end_time": "18:00"},
                {"weekday": "saturday", "start_time": "09:00", "end_time": "18:00"},
            ],
            "max_monthly_rounds": 6,
            "service_capacity": 3,
            "max_daily_hours": 7.0,
            "max_travel_time_minutes": 80,
            "minimum_compensation_won": 1_000_000,
        },
        {
            "provider_id": "provider-repair-care",
            "name": "마을수리센터",
            "base_area_id": "base-p1",
            "supported_services": ["home_repair", "daily_necessities"],
            "availability": [
                {"weekday": "wednesday", "start_time": "09:00", "end_time": "18:00"},
                {"weekday": "thursday", "start_time": "09:00", "end_time": "18:00"},
            ],
            "max_monthly_rounds": 3,
            "service_capacity": 2,
            "max_daily_hours": 6.0,
            "max_travel_time_minutes": 70,
            "minimum_compensation_won": 800_000,
        },
    ]

    # Populate complete travel matrix
    all_nodes = [base, base2] + [
        {"id": a["id"], "anchor_lat": a["anchor_lat"], "anchor_lng": a["anchor_lng"]}
        for a in areas
    ]
    for u in all_nodes:
        for v in all_nodes:
            if u["id"] == v["id"]:
                continue
            dx = (v["anchor_lng"] - u["anchor_lng"]) * 88.0
            dy = (v["anchor_lat"] - u["anchor_lat"]) * 111.0
            euc_km = math.hypot(dx, dy)
            road_km = max(0.8, euc_km * 1.35)
            dist_m = int(road_km * 1000)
            dur_s = max(60, int(dist_m / 12.5))
            put_cached(connection, u, v, Route(u["id"], v["id"], dist_m, dur_s))

    return areas, providers, connection


def main() -> int:
    artifacts_dir = ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        temp_db = Path(tf.name)

    try:
        areas, providers, connection = build_sensitivity_fixture(temp_db)
        budget_won = 1_500_000

        print("Running Provider Participation Sensitivity (§15)...")
        start_p = time.perf_counter()
        provider_res = run_provider_participation_sensitivity(
            areas, providers, connection, budget_won
        )
        p_ms = round((time.perf_counter() - start_p) * 1000, 2)
        n_scen = len(provider_res['scenarios'])
        print(f"Provider sensitivity completed in {p_ms}ms ({n_scen} scenarios)")

        p_path = artifacts_dir / "provider_sensitivity.json"
        with open(p_path, "w", encoding="utf-8") as f:
            json.dump(provider_res, f, ensure_ascii=False, indent=2)
        print(f"Saved: {p_path}")

        print("\nRunning Policy Weight Sensitivity (§16)...")
        start_pol = time.perf_counter()
        policy_res = run_policy_sensitivity_analysis(
            areas, providers, connection, budget_won
        )
        pol_ms = round((time.perf_counter() - start_pol) * 1000, 2)
        n_cfg = len(policy_res['configurations'])
        print(f"Policy sensitivity completed in {pol_ms}ms ({n_cfg} configs)")
        print(f"Sensitivity Flag: {policy_res['instability_flag']} - {policy_res['user_guidance']}")

        pol_path = artifacts_dir / "policy_sensitivity.json"
        with open(pol_path, "w", encoding="utf-8") as f:
            json.dump(policy_res, f, ensure_ascii=False, indent=2)
        print(f"Saved: {pol_path}")

    finally:
        connection.close()
        if temp_db.exists():
            temp_db.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
