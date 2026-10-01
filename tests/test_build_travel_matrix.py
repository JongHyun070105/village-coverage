from scripts.build_travel_matrix import group_areas_by_region


def test_road_matrix_groups_areas_before_building_routes() -> None:
    areas = [
        {"id": "hongseong-ri", "region_id": "pilot:홍성군 장곡면"},
        {"id": "buyeo-ri", "region_id": "pilot:부여군 부여읍"},
        {"id": "legacy-ri"},
    ]

    grouped = group_areas_by_region(areas, "pilot:홍성군 장곡면")

    assert set(grouped) == {"pilot:홍성군 장곡면", "pilot:부여군 부여읍"}
    assert [area["id"] for area in grouped["pilot:홍성군 장곡면"]] == [
        "hongseong-ri",
        "legacy-ri",
    ]
    assert [area["id"] for area in grouped["pilot:부여군 부여읍"]] == ["buyeo-ri"]
    assert not any(
        origin.get("region_id", "pilot:홍성군 장곡면")
        != destination.get("region_id", "pilot:홍성군 장곡면")
        for group in grouped.values()
        for origin in group
        for destination in group
    )
