from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.regions import DEFAULT_REGION_ID, region_catalog, region_id, select_region


def test_region_catalog_and_filter_keep_only_exact_selected_town() -> None:
    first_id = DEFAULT_REGION_ID
    second_id = region_id("부여군", "부여읍")
    data = {
        "region": "홍성군 장곡면",
        "default_region_id": first_id,
        "regions": [
            {
                "region_id": first_id,
                "province": "충청남도",
                "county": "홍성군",
                "town": "장곡면",
                "name": "홍성군 장곡면",
                "area_count": 1,
                "full_source_join_rate": 1.0,
            },
            {
                "region_id": second_id,
                "province": "충청남도",
                "county": "부여군",
                "town": "부여읍",
                "name": "부여군 부여읍",
                "area_count": 1,
                "full_source_join_rate": 1.0,
            },
        ],
        "areas": [
            {"id": "area-janggok", "region_id": first_id, "county": "홍성군", "town": "장곡면"},
            {"id": "area-buyeo", "region_id": second_id, "county": "부여군", "town": "부여읍"},
        ],
    }

    assert [item["region_id"] for item in region_catalog(data)] == [first_id, second_id]
    selected = select_region(data, second_id)
    assert selected["region"] == "부여군 부여읍"
    assert selected["areas"] == [data["areas"][1]]
    assert selected["regions"] == data["regions"]


def test_unverified_region_cannot_be_selected() -> None:
    with pytest.raises(ValueError, match="unknown or unverified"):
        select_region({"regions": [], "areas": []}, "pilot:unknown town")


def test_committed_public_fixture_has_three_complete_disjoint_regions() -> None:
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "data" / "demo.json").read_text(encoding="utf-8"))
    regions = region_catalog(data)

    assert len(regions) >= 3
    all_area_ids: set[str] = set()
    for option in regions:
        selected = select_region(data, option["region_id"])
        area_ids = {str(area["id"]) for area in selected["areas"]}
        assert len(area_ids) == option["area_count"]
        assert area_ids.isdisjoint(all_area_ids)
        assert all_area_ids.isdisjoint(area_ids)
        assert option["full_source_join_rate"] == 1.0
        assert option["household_join_rate"] == 1.0
        assert option["facility_area_coverage"] == 1.0
        assert all(
            area["anchor_lat"] is not None and area["anchor_lng"] is not None
            for area in selected["areas"]
        )
        all_area_ids.update(area_ids)

    assert all_area_ids == {str(area["id"]) for area in data["areas"]}
