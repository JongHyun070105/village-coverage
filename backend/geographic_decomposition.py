"""Deterministic road/provider-aware geographic partitioning for solver proposals."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from math import ceil
from typing import Iterable, Literal

ClusterStrategy = Literal[
    "ADMINISTRATIVE_CLUSTER",
    "DISTANCE_CLUSTER",
    "PROVIDER_REACHABILITY_CLUSTER",
    "HYBRID_CLUSTER",
]

ADMINISTRATIVE_FIELDS = (
    "administrative_cluster_id",
    "eup_myeon_id",
    "administrative_district_code",
)


@dataclass(frozen=True)
class ClusterConfig:
    """Benchmark-tunable cluster limits; distance is measured on directed road time."""

    min_cluster_size: int = 4
    target_cluster_size: int = 16
    max_cluster_size: int = 24
    max_interarea_travel_minutes: int = 60
    max_provider_pairs_per_area: int = 3
    local_solve_time_seconds: float = 0.1
    enable_heuristic_candidate_pruning: bool = False

    def __post_init__(self) -> None:
        if self.min_cluster_size < 1:
            raise ValueError("min_cluster_size must be positive")
        if self.target_cluster_size < self.min_cluster_size:
            raise ValueError("target_cluster_size must be at least min_cluster_size")
        if self.max_cluster_size < self.target_cluster_size:
            raise ValueError("max_cluster_size must be at least target_cluster_size")
        if self.max_interarea_travel_minutes < 1:
            raise ValueError("max_interarea_travel_minutes must be positive")
        if self.max_provider_pairs_per_area < 1:
            raise ValueError("max_provider_pairs_per_area must be positive")
        if self.local_solve_time_seconds <= 0:
            raise ValueError("local_solve_time_seconds must be positive")


@dataclass(frozen=True)
class GeographicCluster:
    cluster_id: str
    area_ids: tuple[str, ...]


@dataclass(frozen=True)
class GeographicPartition:
    strategy: ClusterStrategy
    clusters: tuple[GeographicCluster, ...]
    boundary_area_ids: tuple[str, ...]
    administrative_fallback_used: bool = False

    @property
    def area_to_cluster(self) -> dict[str, str]:
        return {
            area_id: cluster.cluster_id
            for cluster in self.clusters
            for area_id in cluster.area_ids
        }


def _road_time_minutes(
    first: str,
    second: str,
    road_times_seconds: dict[tuple[str, str], int],
) -> int | None:
    outbound = road_times_seconds.get((first, second))
    inbound = road_times_seconds.get((second, first))
    if outbound is None or inbound is None:
        return None
    return ceil(max(outbound, inbound) / 60)


def _components(area_ids: tuple[str, ...], adjacency: dict[str, set[str]]) -> list[tuple[str, ...]]:
    unseen = set(area_ids)
    found: list[tuple[str, ...]] = []
    while unseen:
        root = min(unseen)
        queue = deque([root])
        unseen.remove(root)
        component = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(adjacency[current] & unseen):
                unseen.remove(neighbor)
                queue.append(neighbor)
        found.append(tuple(sorted(component)))
    return sorted(found, key=lambda component: component[0])


def _component_distance(
    first: str,
    second: str,
    road_times_seconds: dict[tuple[str, str], int],
    distance_fallback: int,
) -> int:
    if first == second:
        return 0
    distance = _road_time_minutes(first, second, road_times_seconds)
    return distance_fallback if distance is None else distance


def _split_component(
    component: tuple[str, ...],
    road_times_seconds: dict[tuple[str, str], int],
    config: ClusterConfig,
) -> list[tuple[str, ...]]:
    if len(component) <= config.max_cluster_size:
        return [component]

    seed_count = ceil(len(component) / config.target_cluster_size)
    fallback_distance = config.max_interarea_travel_minutes + 1
    first_seed = min(
        component,
        key=lambda candidate: (
            sum(
                _component_distance(candidate, other, road_times_seconds, fallback_distance)
                for other in component
            ),
            candidate,
        ),
    )
    seeds = [first_seed]
    while len(seeds) < seed_count:
        next_seed = max(
            (area_id for area_id in component if area_id not in seeds),
            key=lambda candidate: (
                min(
                    _component_distance(candidate, seed, road_times_seconds, fallback_distance)
                    for seed in seeds
                ),
                candidate,
            ),
        )
        seeds.append(next_seed)

    clusters: dict[str, list[str]] = {seed: [seed] for seed in seeds}
    assignment_order = sorted(
        (area_id for area_id in component if area_id not in seeds),
        key=lambda area_id: (
            -min(
                _component_distance(area_id, seed, road_times_seconds, fallback_distance)
                for seed in seeds
            ),
            area_id,
        ),
    )
    for area_id in assignment_order:
        under_target = [
            seed for seed in seeds if len(clusters[seed]) < config.target_cluster_size
        ]
        eligible = under_target or [
            seed for seed in seeds if len(clusters[seed]) < config.max_cluster_size
        ]
        seed = min(
            eligible,
            key=lambda candidate: (
                _component_distance(
                    area_id, candidate, road_times_seconds, fallback_distance
                ),
                len(clusters[candidate]),
                candidate,
            ),
        )
        clusters[seed].append(area_id)
    return [tuple(sorted(clusters[seed])) for seed in sorted(seeds)]


def _merge_small_groups(
    groups: list[tuple[str, ...]],
    road_times_seconds: dict[tuple[str, str], int],
    config: ClusterConfig,
) -> list[tuple[str, ...]]:
    """Merge undersized groups with the nearest group that stays below the hard maximum."""
    groups = sorted((tuple(sorted(group)) for group in groups), key=lambda group: group[0])
    fallback_distance = config.max_interarea_travel_minutes + 1
    while len(groups) > 1:
        small_indexes = [
            index for index, group in enumerate(groups) if len(group) < config.min_cluster_size
        ]
        if not small_indexes:
            break
        source_index = min(small_indexes, key=lambda index: (len(groups[index]), groups[index][0]))
        source = groups[source_index]
        targets = [
            index
            for index, group in enumerate(groups)
            if index != source_index and len(group) + len(source) <= config.max_cluster_size
        ]
        if not targets:
            break
        target_index = min(
            targets,
            key=lambda index: (
                min(
                    _component_distance(first, second, road_times_seconds, fallback_distance)
                    for first in source
                    for second in groups[index]
                ),
                len(groups[index]),
                groups[index][0],
            ),
        )
        merged = tuple(sorted((*source, *groups[target_index])))
        groups = [
            group
            for index, group in enumerate(groups)
            if index not in {source_index, target_index}
        ]
        groups.append(merged)
        groups.sort(key=lambda group: group[0])
    return groups


def build_geographic_partition(
    areas: list[dict[str, object]],
    road_times_seconds: dict[tuple[str, str], int],
    *,
    strategy: ClusterStrategy = "HYBRID_CLUSTER",
    provider_area_pairs: Iterable[tuple[str, str]] = (),
    config: ClusterConfig | None = None,
) -> GeographicPartition:
    """Partition areas deterministically using directed roads, administration and reachability.

    Provider-area pairs must already have passed hard service, availability, route,
    travel-limit and time-window compatibility checks. A provider may therefore
    appear in several clusters; the partition never assigns a provider exclusively.
    """
    config = config or ClusterConfig()
    if strategy not in {
        "ADMINISTRATIVE_CLUSTER",
        "DISTANCE_CLUSTER",
        "PROVIDER_REACHABILITY_CLUSTER",
        "HYBRID_CLUSTER",
    }:
        raise ValueError("unsupported geographic cluster strategy")
    area_ids = tuple(sorted(str(area["id"]) for area in areas))
    if len(area_ids) != len(set(area_ids)):
        raise ValueError("area ids must be unique")
    ids = set(area_ids)
    area_by_id = {str(area["id"]): area for area in areas}
    administrative_keys = {
        area_id: next(
            (
                str(area_by_id[area_id][field])
                for field in ADMINISTRATIVE_FIELDS
                if area_by_id[area_id].get(field) not in (None, "")
            ),
            None,
        )
        for area_id in area_ids
    }
    administrative_fallback_used = strategy == "ADMINISTRATIVE_CLUSTER" and any(
        value is None for value in administrative_keys.values()
    )

    providers_by_area: dict[str, set[str]] = defaultdict(set)
    for provider_id, area_id in provider_area_pairs:
        if str(area_id) in ids:
            providers_by_area[str(area_id)].add(str(provider_id))

    adjacency = {area_id: set() for area_id in area_ids}
    distance_edges: set[tuple[str, str]] = set()
    for index, first in enumerate(area_ids):
        for second in area_ids[index + 1 :]:
            travel_minutes = _road_time_minutes(first, second, road_times_seconds)
            within_distance = (
                travel_minutes is not None
                and travel_minutes <= config.max_interarea_travel_minutes
            )
            if within_distance:
                distance_edges.add((first, second))
            shares_provider = bool(providers_by_area[first] & providers_by_area[second])
            same_administration = (
                administrative_keys[first] is not None
                and administrative_keys[first] == administrative_keys[second]
            )
            connected = (
                same_administration or (
                    (administrative_keys[first] is None or administrative_keys[second] is None)
                    and within_distance
                )
                if strategy == "ADMINISTRATIVE_CLUSTER"
                else within_distance
                if strategy == "DISTANCE_CLUSTER"
                else shares_provider
                if strategy == "PROVIDER_REACHABILITY_CLUSTER"
                else same_administration or (within_distance and shares_provider)
            )
            if connected:
                adjacency[first].add(second)
                adjacency[second].add(first)

    raw_components = _components(area_ids, adjacency)
    grouped = [
        subcluster
        for component in raw_components
        for subcluster in _split_component(component, road_times_seconds, config)
    ]
    grouped = _merge_small_groups(grouped, road_times_seconds, config)
    grouped.sort(key=lambda cluster: cluster[0])
    clusters = tuple(
        GeographicCluster(f"cluster-{index:03d}", tuple(sorted(group)))
        for index, group in enumerate(grouped)
    )
    area_to_cluster = {
        area_id: cluster.cluster_id for cluster in clusters for area_id in cluster.area_ids
    }
    fallback_distance = config.max_interarea_travel_minutes + 1
    boundary: set[str] = set()
    for area_id in area_ids:
        same_cluster = [
            other for other in area_ids
            if other != area_id and area_to_cluster[other] == area_to_cluster[area_id]
        ]
        other_clusters = [
            other for other in area_ids
            if area_to_cluster[other] != area_to_cluster[area_id]
        ]
        internal_distance = min(
            (
                _component_distance(area_id, other, road_times_seconds, fallback_distance)
                for other in same_cluster
            ),
            default=fallback_distance,
        )
        external_distance = min(
            (
                _component_distance(area_id, other, road_times_seconds, fallback_distance)
                for other in other_clusters
            ),
            default=fallback_distance,
        )
        if (
            len(same_cluster) + 1 <= config.min_cluster_size
            or external_distance <= internal_distance
        ):
            boundary.add(area_id)
    return GeographicPartition(
        strategy=strategy,
        clusters=clusters,
        boundary_area_ids=tuple(sorted(boundary)),
        administrative_fallback_used=administrative_fallback_used,
    )
