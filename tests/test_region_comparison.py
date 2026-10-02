"""Tests for pilot region comparison, normalization, and licensing segregation (§19, §20)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend.region_comparison import compare_pilot_regions

ROOT = Path(__file__).resolve().parents[1]


def test_compare_pilot_regions_covers_all_three_regions_descriptively() -> None:
    demo_path = ROOT / "data" / "demo.json"
    data = json.loads(demo_path.read_text(encoding="utf-8"))

    result = compare_pilot_regions(data)
    assert result["analysis_type"] == "DESCRIPTIVE_REGION_COMPARISON"
    assert result["total_regions"] == 3
    assert result["total_areas"] == 54

    regions = result["regions"]
    assert len(regions) == 3

    region_names = {r["region_name"] for r in regions}
    assert "부여군 부여읍" in region_names
    assert "홍성군 장곡면" in region_names
    assert "아산시 음봉면" in region_names

    # Invariant: Strictly NO evaluative rankings or scores
    for reg in regions:
        assert "rank" not in reg
        assert "score" not in reg
        assert "grade" not in reg
        assert "best" not in reg
        assert "worst" not in reg

        # Badges segregation
        pub = reg["public_statistics"]
        assert pub["badge"] == "REAL"
        assert pub["population_total"] > 0
        assert pub["population_65_plus"] > 0
        assert 0.0 < pub["elderly_ratio"] < 1.0

        norm = reg["normalized_indicators"]
        assert norm["badge"] == "REAL"
        assert norm["population_per_area"] > 0
        assert norm["elderly_per_1000_pop"] > 0

        op = reg["operational_estimates"]
        assert op["badge"] == "SIMULATED"
        assert "simulated_monthly_demand_units" in op
        assert "data_sufficiency_breakdown" in op


def test_facility_detail_licensing_segregation() -> None:
    demo_path = ROOT / "data" / "demo.json"
    data = json.loads(demo_path.read_text(encoding="utf-8"))
    result = compare_pilot_regions(data)

    reg_map = {r["region_name"]: r for r in result["regions"]}

    # Buyeo has verified open public license for facility details
    buyeo_stat = reg_map["부여군 부여읍"]["public_statistics"]
    assert buyeo_stat["facility_licensing_status"] == "DETAIL_AVAILABLE"

    # Hongseong and Asan remain aggregate only due to unverified individual address licensing
    hong_stat = reg_map["홍성군 장곡면"]["public_statistics"]
    assert hong_stat["facility_licensing_status"] == "AGGREGATE_ONLY"
    asan_stat = reg_map["아산시 음봉면"]["public_statistics"]
    assert asan_stat["facility_licensing_status"] == "AGGREGATE_ONLY"


def test_api_regions_comparison_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/regions/comparison")
    assert response.status_code == 200
    data = response.json()
    assert data["total_regions"] == 3
    assert data["total_areas"] == 54
