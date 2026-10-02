"""Descriptive cross-region comparison with metric normalization and source labeling (§19)."""

from __future__ import annotations

from typing import Any

from backend.data_quality import assess_area_data_quality
from backend.regions import region_catalog, select_region

FACILITY_LICENSING_STATUS: dict[str, str] = {
    "pilot:부여군 부여읍": "DETAIL_AVAILABLE",
    "pilot:홍성군 장곡면": "AGGREGATE_ONLY",
    "pilot:아산시 음봉면": "AGGREGATE_ONLY",
    "pilot:아산시 송악면": "AGGREGATE_ONLY",
}


def compare_pilot_regions(data: dict[str, Any]) -> dict[str, Any]:
    """Generate normalized, descriptive comparison across verified pilot regions.

    Invariants:
      - No evaluative rankings (NO best/worst/rank 1st/2nd/3rd).
      - Strict REAL vs SIMULATED badge segregation.
      - Normalized per-area and per-1,000-population indicators.
    """
    regions = region_catalog(data)
    region_comparisons: list[dict[str, Any]] = []

    for reg in regions:
        r_id = reg["region_id"]
        reg_data = select_region(data, r_id)
        areas = reg_data.get("areas", [])
        area_count = len(areas)

        # 1. Real public statistics
        pop_total = sum(int(a.get("population_total", 0)) for a in areas)
        pop_65 = sum(
            round(int(a.get("population_total", 0)) * float(a.get("elderly_ratio_65", 0)))
            for a in areas
        )
        single_65 = sum(int(a.get("single_households_65_plus", 0)) for a in areas)
        facility_total = sum(int(a.get("facility_count", 0)) for a in areas)
        elderly_ratio = round(pop_65 / pop_total, 4) if pop_total > 0 else 0.0

        licensing = FACILITY_LICENSING_STATUS.get(r_id, "AGGREGATE_ONLY")

        # 2. Simulated & operational parameters
        sim_demand = sum(int(a.get("simulated_monthly_demand", 0)) for a in areas)
        needs_survey_count = sum(1 for a in areas if a.get("needs_survey", False))

        # Data quality evaluation across areas
        qualities = [assess_area_data_quality(a) for a in areas]
        sufficiency_counts = {
            "SUFFICIENT": sum(1 for q in qualities if q["overall_status"] == "SUFFICIENT"),
            "LIMITED": sum(1 for q in qualities if q["overall_status"] == "LIMITED"),
            "SURVEY_REQUIRED": sum(
                1 for q in qualities if q["overall_status"] == "SURVEY_REQUIRED"
            ),
        }

        # Route burden estimation (km from first anchor or base)
        # Average distance between area anchors
        if area_count > 1:
            lats = [float(a.get("anchor_lat", 36.5)) for a in areas]
            lngs = [float(a.get("anchor_lng", 126.6)) for a in areas]
            c_lat = sum(lats) / area_count
            c_lng = sum(lngs) / area_count
            # Approximate radius in km
            avg_dist_km = sum(
                ((lat - c_lat) ** 2 * 111.0**2 + (lng - c_lng) ** 2 * 88.0**2) ** 0.5
                for lat, lng in zip(lats, lngs, strict=True)
            ) / area_count
            route_burden_km = round(avg_dist_km, 2)
        else:
            route_burden_km = 0.0

        # Normalization
        pop_per_area = round(pop_total / area_count, 1) if area_count > 0 else 0.0
        elderly_per_1000 = round((pop_65 / pop_total) * 1000, 1) if pop_total > 0 else 0.0
        single_per_1000 = round((single_65 / pop_total) * 1000, 1) if pop_total > 0 else 0.0
        fac_per_1000 = round((facility_total / pop_total) * 1000, 2) if pop_total > 0 else 0.0
        facilities_per_area = round(facility_total / area_count, 2) if area_count > 0 else 0.0

        surv_ratio = round(needs_survey_count / area_count, 3) if area_count > 0 else 0.0

        region_comparisons.append(
            {
                "region_id": r_id,
                "region_name": reg["name"],
                "province": reg["province"],
                "county": reg["county"],
                "town": reg["town"],
                "area_count": area_count,
                # Public Census Statistics (REAL)
                "public_statistics": {
                    "badge": "REAL",
                    "population_total": pop_total,
                    "population_65_plus": pop_65,
                    "elderly_ratio": elderly_ratio,
                    "single_households_65_plus": single_65,
                    "facility_count": facility_total,
                    "facility_licensing_status": licensing,
                },
                # Normalized Indicators (REAL)
                "normalized_indicators": {
                    "badge": "REAL",
                    "population_per_area": pop_per_area,
                    "elderly_per_1000_pop": elderly_per_1000,
                    "single_elderly_per_1000_pop": single_per_1000,
                    "facilities_per_1000_pop": fac_per_1000,
                    "facilities_per_area": facilities_per_area,
                },
                # Operational & Model Parameters (SIMULATED)
                "operational_estimates": {
                    "badge": "SIMULATED",
                    "simulated_monthly_demand_units": sim_demand,
                    "survey_required_areas_count": needs_survey_count,
                    "survey_required_ratio": surv_ratio,
                    "data_sufficiency_breakdown": sufficiency_counts,
                    "route_spatial_spread_km": route_burden_km,
                },
            }
        )

    desc = (
        "충청남도 3개 파일럿 지역(부여읍, 장곡면, 음봉면)의 공공데이터 및 "
        "시뮬레이션 지표 기술적 비교"
    )
    return {
        "analysis_type": "DESCRIPTIVE_REGION_COMPARISON",
        "description": desc,
        "evaluation_rule": "서열화(순위/등급/우열) 없이 순수 통계 및 운영 지표 비교만 제공",
        "total_regions": len(region_comparisons),
        "total_areas": sum(r["area_count"] for r in region_comparisons),
        "regions": region_comparisons,
    }
