"""Compare laundry delivery modes on a pilot region's real road matrix (V4 §87-§88).

Usage: uv run python scripts/run_service_mode_comparison.py [--region "pilot:홍성군 장곡면"]
Writes artifacts/service_mode_comparison.json. Demand and operating parameters
are SIMULATION; road legs are cached Kakao routes; facility counts are public data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import database  # noqa: E402
from backend.regions import select_region  # noqa: E402
from backend.service_mode_comparison import compare_service_modes  # noqa: E402
from backend.source_snapshots import utc_now  # noqa: E402
from backend.travel import connect, get_cached  # noqa: E402

DEFAULT_REGIONS = ("pilot:홍성군 장곡면", "pilot:부여군 부여읍", "pilot:아산시 음봉면")


def region_comparison(source: dict, region_id: str) -> dict:
    data = select_region(source, region_id)
    areas = data["areas"]
    by_id = {str(a["id"]): a for a in areas}
    travel = connect()
    app = database.connect(Path("/tmp") / "vc_service_mode_app.sqlite")
    try:
        database.seed_reference_data(app, source)
        database.seed_provider_data(app, source)
        providers = database.list_providers(app, region_id)
        base = str(providers[0]["base_area_id"]) if providers else str(areas[0]["id"])

        def road(origin: str, destination: str):
            if origin == destination:
                return (0, 0)
            route = get_cached(travel, by_id[origin], by_id[destination])
            return (route.distance_m, route.duration_s) if route else None

        # Same laundry demand for every mode: the region's simulated laundry baseline,
        # applied to every area so all modes serve an identical request set.
        laundry_areas = [
            {**a, "simulated_monthly_demand": int(a.get("simulated_monthly_demand") or 0)}
            for a in areas
        ]
        result = compare_service_modes(areas=laundry_areas, base_area_id=base, road=road)
        result["region_id"] = region_id
        result["area_count"] = len(areas)
        result["provider_base_provenance"] = "SIMULATED provider base at a public area anchor"
        return result
    finally:
        travel.close()
        app.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", action="append")
    args = parser.parse_args()
    source = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
    regions = args.region or list(DEFAULT_REGIONS)
    report = {
        "generated_at": utc_now(),
        "service_type": "laundry",
        "regions": [region_comparison(source, region) for region in regions],
    }
    out = ROOT / "artifacts" / "service_mode_comparison.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for region in report["regions"]:
        print(region["region_id"], region["demand_units_per_month"])
        for mode, row in region["modes"].items():
            print(f"  {mode:15s} {row.get('status')} cost={row.get('monthly_cost_won')} "
                  f"km={row.get('vehicle_distance_km')} staff_h={row.get('staff_hours')} "
                  f"resident_min={row.get('resident_travel_minutes_per_unit')}")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
