from backend.geographic_decomposition import (
    ClusterConfig,
    build_geographic_partition,
)


def complete_road_times(area_ids, minutes=2):
    return {
        (origin, destination): minutes * 60
        for origin in area_ids
        for destination in area_ids
        if origin != destination
    }


def test_distance_partition_is_reproducible_bounded_and_boundary_aware():
    areas = [{"id": f"area-{index:03d}"} for index in range(27)]
    roads = complete_road_times([area["id"] for area in areas])
    config = ClusterConfig(
        min_cluster_size=3,
        target_cluster_size=8,
        max_cluster_size=10,
        max_interarea_travel_minutes=5,
    )

    first = build_geographic_partition(
        areas, roads, strategy="DISTANCE_CLUSTER", config=config
    )
    second = build_geographic_partition(
        areas, roads, strategy="DISTANCE_CLUSTER", config=config
    )

    assert first == second
    assignments = [area_id for cluster in first.clusters for area_id in cluster.area_ids]
    assert sorted(assignments) == sorted(area["id"] for area in areas)
    assert len(assignments) == len(set(assignments))
    assert all(len(cluster.area_ids) <= config.max_cluster_size for cluster in first.clusters)
    assert len(first.clusters) > 1
    assert first.boundary_area_ids


def test_administrative_partition_uses_available_codes_before_road_distance():
    areas = [
        {"id": "a", "eup_myeon_id": "town-1"},
        {"id": "b", "eup_myeon_id": "town-1"},
        {"id": "c", "eup_myeon_id": "town-2"},
    ]
    roads = complete_road_times([area["id"] for area in areas], minutes=30)
    partition = build_geographic_partition(
        areas,
        roads,
        strategy="ADMINISTRATIVE_CLUSTER",
        config=ClusterConfig(1, 2, 2, 5),
    )

    assignment = partition.area_to_cluster
    assert assignment["a"] == assignment["b"]
    assert assignment["a"] != assignment["c"]
    assert partition.administrative_fallback_used is False


def test_administrative_partition_falls_back_for_areas_without_admin_codes():
    areas = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    roads = complete_road_times([area["id"] for area in areas])
    partition = build_geographic_partition(
        areas,
        roads,
        strategy="ADMINISTRATIVE_CLUSTER",
        config=ClusterConfig(1, 2, 2, 5),
    )

    assert partition.administrative_fallback_used is True
    assert len(partition.clusters) == 2


def test_provider_reachability_connects_areas_without_fixing_provider_ownership():
    areas = [{"id": area_id} for area_id in ("a", "b", "c", "d")]
    pairs = [
        ("shared-provider", "a"),
        ("provider-a", "b"),
        ("shared-provider", "c"),
        ("provider-d", "d"),
    ]
    partition = build_geographic_partition(
        areas,
        {},
        strategy="PROVIDER_REACHABILITY_CLUSTER",
        provider_area_pairs=pairs,
        config=ClusterConfig(1, 2, 3, 5),
    )

    assignment = partition.area_to_cluster
    assert assignment["a"] == assignment["c"]
    assert set(assignment) == {"a", "b", "c", "d"}


def test_cluster_config_rejects_inconsistent_size_limits():
    try:
        ClusterConfig(min_cluster_size=5, target_cluster_size=4, max_cluster_size=8)
    except ValueError as exc:
        assert "target_cluster_size" in str(exc)
    else:
        raise AssertionError("invalid cluster sizes must fail closed")


def test_undersized_reachability_groups_merge_without_exceeding_maximum():
    areas = [{"id": area_id} for area_id in ("a", "b", "c", "d", "e")]
    pairs = [(f"provider-{index}", area_id) for index, area_id in enumerate("abcde")]
    config = ClusterConfig(
        min_cluster_size=2,
        target_cluster_size=3,
        max_cluster_size=4,
        max_interarea_travel_minutes=5,
    )

    partition = build_geographic_partition(
        areas,
        {},
        strategy="PROVIDER_REACHABILITY_CLUSTER",
        provider_area_pairs=pairs,
        config=config,
    )

    sizes = [len(cluster.area_ids) for cluster in partition.clusters]
    assert sorted(sizes) == [2, 3]
    assert all(config.min_cluster_size <= size <= config.max_cluster_size for size in sizes)
