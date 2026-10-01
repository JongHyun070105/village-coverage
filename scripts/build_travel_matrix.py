#!/usr/bin/env python3
"""Cache a directed Kakao Mobility road-distance/time matrix in local SQLite."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.travel import (  # noqa: E402
    ROUTING_VERSION,
    Route,
    connect,
    fetch_group,
    fetch_single,
    get_cached,
    put_cached,
)
from scripts.api_smoke_test import _load_config  # noqa: E402


def group_areas_by_region(
    areas: list[dict[str, object]], default_region_id: str
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for area in areas:
        identifier = str(area.get("region_id") or default_region_id)
        grouped.setdefault(identifier, []).append(area)
    return grouped


def main() -> int:
    try:
        demo = json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))
        areas = demo["areas"]
    except Exception:
        print("Demo data is missing or invalid; build public-data aggregates first.")
        return 2
    api_key = _load_config("KAKAO_REST_API_KEY")
    if not api_key:
        print("KAKAO_REST_API_KEY is missing; value was not inspected or printed.")
        return 2

    connection = connect()
    default_region_id = str(demo.get("default_region_id", "pilot:legacy"))
    grouped_areas = group_areas_by_region(areas, default_region_id)

    region_reports: list[dict[str, object]] = []
    all_routes: list[tuple[dict[str, object], dict[str, object]]] = []
    for region_id, region_areas in sorted(grouped_areas.items()):
        expected = len(region_areas) * (len(region_areas) - 1)
        cached_before = sum(
            get_cached(connection, origin, destination) is not None
            for origin in region_areas
            for destination in region_areas
            if origin["id"] != destination["id"]
        )
        fetched = 0
        failed = 0
        for origin in region_areas:
            missing = [
                destination
                for destination in region_areas
                if destination["id"] != origin["id"]
                and get_cached(connection, origin, destination) is None
            ]
            routes = fetch_group(origin, missing, api_key)
            for destination in missing:
                route = routes.get(destination["id"])
                if route is None:
                    route = fetch_single(origin, destination, api_key)
                    time.sleep(0.12)
                if route is None:
                    # An exact cache fallback is allowed; a straight-line estimate is not.
                    route = get_cached(connection, origin, destination)
                else:
                    put_cached(connection, origin, destination, route)
                    fetched += 1
            for destination in region_areas:
                if destination["id"] != origin["id"] and get_cached(
                    connection, origin, destination
                ) is None:
                    failed += 1
            time.sleep(0.08)
        cached_after = sum(
            get_cached(connection, origin, destination) is not None
            for origin in region_areas
            for destination in region_areas
            if origin["id"] != destination["id"]
        )
        region_reports.append(
            {
                "region_id": region_id,
                "area_count": len(region_areas),
                "expected_directed_inter_area_routes": expected,
                "routes_cached_before": cached_before,
                "fresh_routes_added": fetched,
                "routes_available_after": cached_after,
                "route_coverage": round(cached_after / expected, 4) if expected else 0,
                "routes_missing": failed,
            }
        )
        all_routes.extend(
            (origin, destination)
            for origin in region_areas
            for destination in region_areas
            if origin["id"] != destination["id"]
        )

    # Zero is the exact self-to-self route; all inter-area routes remain provider results.
    for area in areas:
        self_route = Route(area["id"], area["id"], 0, 0)
        put_cached(connection, area, area, self_route)

    expected = sum(int(region["expected_directed_inter_area_routes"]) for region in region_reports)
    cached_before = sum(int(region["routes_cached_before"]) for region in region_reports)
    fetched = sum(int(region["fresh_routes_added"]) for region in region_reports)
    cached_after = sum(
        get_cached(connection, origin, destination) is not None
        for origin, destination in all_routes
    )
    failed = sum(int(region["routes_missing"]) for region in region_reports)
    summary = {
        "region": demo["region"],
        "regions": region_reports,
        "provider": "Kakao Mobility multi-destination directions API",
        "routing_version": ROUTING_VERSION,
        "priority": "TIME",
        "area_count": len(areas),
        "expected_directed_inter_area_routes": expected,
        "routes_cached_before": cached_before,
        "fresh_routes_added": fetched,
        "routes_available_after": cached_after,
        "route_coverage": round(cached_after / expected, 4) if expected else 0,
        "routes_missing": failed,
        "self_routes_added": len(areas),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "cache_file": "data/village_coverage.sqlite (local, ignored by Git)",
        "fallback_policy": (
            "Use an exact cached road route after retry; never substitute straight-line distance."
        ),
    }
    report_path = ROOT / "artifacts" / "travel_matrix_report.json"
    report_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    connection.close()
    print(
        f"Road matrix: {cached_after}/{expected} directed inter-area routes cached "
        f"({summary['route_coverage']:.0%}); missing={failed}."
    )
    return 0 if cached_after == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
