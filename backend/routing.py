"""Time-windowed provider routes over the exact directed road cache."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from backend.optimization import TRAVEL_LABOR_WON_PER_HOUR, TRAVEL_RATE_WON_PER_KM


class MissingRoadLegError(ValueError):
    """A directed Kakao road leg needed to compare a route is not cached."""


def _minute(value: str) -> int:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def _hhmm(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def _leg_cost(distance_m: int, duration_s: int) -> int:
    return math.ceil(distance_m / 1000 * TRAVEL_RATE_WON_PER_KM) + math.ceil(
        duration_s / 3600 * TRAVEL_LABOR_WON_PER_HOUR
    )


def optimize_multi_stop_route(
    base_area_id: str,
    stops: list[dict[str, Any]],
    roads: dict[tuple[str, str], tuple[int, int]],
    *,
    available_from: str,
    available_until: str,
    max_daily_hours: float,
    time_limit_seconds: float = 0.5,
    fixed_order: list[str] | None = None,
) -> dict[str, Any] | None:
    """Find a feasible Kakao-road order for all stops; return None if none is found."""
    if len(stops) < 2:
        return None
    if len({str(stop["area_id"]) for stop in stops}) != len(stops):
        raise ValueError("multi-stop route cannot contain the same area twice")

    location_ids = [base_area_id, *(str(stop["area_id"]) for stop in stops)]
    count = len(location_ids)
    distance_matrix: list[list[int]] = []
    duration_matrix: list[list[int]] = []
    for origin in location_ids:
        distance_row: list[int] = []
        duration_row: list[int] = []
        for destination in location_ids:
            leg = roads.get((origin, destination))
            if origin == destination and leg is None:
                # A matrix diagonal is a zero movement, not an estimated road route.
                leg = (0, 0)
            if leg is None:
                raise MissingRoadLegError(
                    f"provider road route missing for {origin} and {destination}"
                )
            distance_row.append(int(leg[0]))
            duration_row.append(int(leg[1]))
        distance_matrix.append(distance_row)
        duration_matrix.append(duration_row)

    manager = pywrapcp.RoutingIndexManager(count, 1, 0)
    routing = pywrapcp.RoutingModel(manager)
    service_minutes = [0, *(max(1, int(stop["duration_minutes"])) for stop in stops)]

    def cost_callback(from_index: int, to_index: int) -> int:
        origin = manager.IndexToNode(from_index)
        destination = manager.IndexToNode(to_index)
        return _leg_cost(distance_matrix[origin][destination], duration_matrix[origin][destination])

    cost_index = routing.RegisterTransitCallback(cost_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(cost_index)

    def time_callback(from_index: int, to_index: int) -> int:
        origin = manager.IndexToNode(from_index)
        destination = manager.IndexToNode(to_index)
        travel_minutes = math.ceil(duration_matrix[origin][destination] / 60)
        return service_minutes[origin] + travel_minutes

    time_index = routing.RegisterTransitCallback(time_callback)
    available_start = _minute(available_from)
    available_end = _minute(available_until)
    work_limit = min(available_end, available_start + int(max_daily_hours * 60))
    routing.AddDimension(
        time_index,
        max(0, available_end - available_start),
        24 * 60,
        False,
        "Time",
    )
    time_dimension = routing.GetDimensionOrDie("Time")
    time_dimension.CumulVar(routing.Start(0)).SetRange(available_start, available_start)
    time_dimension.CumulVar(routing.End(0)).SetRange(available_start, work_limit)
    for node in range(1, len(stops) + 1):
        service_end_bound = available_end - service_minutes[node]
        stop = stops[node - 1]
        window_start = stop.get("service_start_window_start")
        window_end = stop.get("service_start_window_end")
        earliest_start = max(
            available_start,
            _minute(str(window_start)) if window_start else available_start,
        )
        latest_start = min(
            service_end_bound,
            _minute(str(window_end)) if window_end else service_end_bound,
        )
        if earliest_start > latest_start:
            return None
        time_dimension.CumulVar(manager.NodeToIndex(node)).SetRange(
            earliest_start, latest_start
        )

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    # Greedy descent stops at a local optimum instead of always consuming the time
    # limit (guided local search never stops early). With a fixed order there is
    # nothing to search; the time limit remains only as a safety cap.
    search.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GREEDY_DESCENT
    )
    search.time_limit.FromMilliseconds(max(1, round(time_limit_seconds * 1000)))
    if fixed_order is not None:
        node_by_area = {str(stop["area_id"]): index + 1 for index, stop in enumerate(stops)}
        if len(fixed_order) != len(stops) or set(fixed_order) != set(node_by_area):
            raise ValueError("fixed route order must contain every selected area exactly once")
        index = routing.Start(0)
        for area_id in fixed_order:
            next_index = manager.NodeToIndex(node_by_area[area_id])
            routing.NextVar(index).SetValue(next_index)
            index = next_index
        routing.NextVar(index).SetValue(routing.End(0))
    solution = routing.SolveWithParameters(search)
    if solution is None:
        return None

    sequence: list[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if node:
            sequence.append(node - 1)
        index = solution.Value(routing.NextVar(index))

    if len(sequence) != len(stops):
        return None
    ordered_stops: list[dict[str, Any]] = []
    legs: list[dict[str, Any]] = []
    route_nodes = [0, *(index + 1 for index in sequence), 0]
    for from_node, to_node in zip(route_nodes[:-1], route_nodes[1:], strict=True):
        legs.append(
            {
                "from_area_id": location_ids[from_node],
                "to_area_id": location_ids[to_node],
                "distance_m": distance_matrix[from_node][to_node],
                "duration_s": duration_matrix[from_node][to_node],
                "cost_won": _leg_cost(
                    distance_matrix[from_node][to_node], duration_matrix[from_node][to_node]
                ),
            }
        )
    for sequence_number, node in enumerate(sequence, start=1):
        stop = dict(stops[node])
        route_index = manager.NodeToIndex(node + 1)
        service_start = solution.Value(time_dimension.CumulVar(route_index))
        service_end = service_start + service_minutes[node + 1]
        incoming = legs[sequence_number - 1]
        outgoing = legs[sequence_number]
        stop.update(
            {
                "route_sequence": sequence_number,
                "service_start_time": _hhmm(service_start),
                "service_end_time": _hhmm(service_end),
                "departure_time": _hhmm(
                    available_start
                    if sequence_number == 1
                    else service_start - math.ceil(incoming["duration_s"] / 60)
                ),
                "travel_before_s": incoming["duration_s"],
                "travel_after_s": outgoing["duration_s"],
                "travel_distance_m": incoming["distance_m"] + outgoing["distance_m"],
                "travel_before_distance_m": incoming["distance_m"],
                "travel_after_distance_m": outgoing["distance_m"],
                "travel_cost_won": incoming["cost_won"],
                "route_from_area_id": incoming["from_area_id"],
                "route_to_area_id": outgoing["to_area_id"],
            }
        )
        ordered_stops.append(stop)

    distance_m = sum(leg["distance_m"] for leg in legs)
    duration_s = sum(leg["duration_s"] for leg in legs)
    cost_won = sum(leg["cost_won"] for leg in legs)
    ordered_stops[-1]["travel_cost_won"] += legs[-1]["cost_won"]
    return {
        "stops": ordered_stops,
        "legs": legs,
        "distance_m": distance_m,
        "duration_s": duration_s,
        "cost_won": cost_won,
        "available_from": available_from,
        "available_until": available_until,
    }
