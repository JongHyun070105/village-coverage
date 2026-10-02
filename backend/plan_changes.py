"""Deterministic summaries for immutable schedule plan revisions."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _assignment_summary(rounds: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for round_item in rounds:
        key = (
            str(round_item["area_id"]),
            str(round_item["service_type"]),
            str(round_item["provider_id"]),
        )
        grouped[key].append(round_item)

    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, items in grouped.items():
        result[key] = {
            "scheduled_slots": sorted(
                (
                    str(item["scheduled_date"]),
                    str(item.get("service_start_time", "")),
                    int(item.get("service_units", 0)),
                    int(item.get("total_cost_won", 0)),
                )
                for item in items
            ),
            "service_units": sum(int(item.get("service_units", 0)) for item in items),
            "total_cost_won": sum(int(item.get("total_cost_won", 0)) for item in items),
        }
    return result


def build_plan_change_explanation(
    previous_rounds: list[dict[str, Any]],
    next_rounds: list[dict[str, Any]],
    *,
    reason: str,
    context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare provider allocations without fuzzy matching or hidden aggregation."""
    previous = _assignment_summary(previous_rounds)
    current = _assignment_summary(next_rounds)
    changes: list[dict[str, Any]] = []
    labels: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    for item in (*previous_rounds, *next_rounds):
        key = (str(item["area_id"]), str(item["service_type"]), str(item["provider_id"]))
        labels[key] = (
            str(item.get("area_name", key[0])),
            str(item.get("service_type", key[1])),
            str(item.get("provider_name", key[2])),
        )

    for key in sorted(set(previous) | set(current)):
        before = previous.get(key)
        after = current.get(key)
        if before == after:
            continue
        change_type = "ADDED" if before is None else "REMOVED" if after is None else "CHANGED"
        area_name, _service_type, provider_name = labels[key]
        changes.append(
            {
                "change_type": change_type,
                "area_id": key[0],
                "area_name": area_name,
                "service_type": key[1],
                "provider_id": key[2],
                "provider_name": provider_name,
                "previous": before,
                "current": after,
                "service_units_delta": (after["service_units"] if after else 0)
                - (before["service_units"] if before else 0),
                "total_cost_delta_won": (after["total_cost_won"] if after else 0)
                - (before["total_cost_won"] if before else 0),
            }
        )

    previous_units = sum(item["service_units"] for item in previous.values())
    current_units = sum(item["service_units"] for item in current.values())
    previous_cost = sum(item["total_cost_won"] for item in previous.values())
    current_cost = sum(item["total_cost_won"] for item in current.values())
    return {
        "version": "DETERMINISTIC_PLAN_CHANGE_V1",
        "reason": reason,
        "provenance": "DETERMINISTIC SCHEDULE ALLOCATION COMPARISON",
        "change_count": len(changes),
        "added_assignment_count": sum(change["change_type"] == "ADDED" for change in changes),
        "removed_assignment_count": sum(change["change_type"] == "REMOVED" for change in changes),
        "changed_assignment_count": sum(change["change_type"] == "CHANGED" for change in changes),
        "previous_service_units": previous_units,
        "current_service_units": current_units,
        "service_units_delta": current_units - previous_units,
        "previous_total_cost_won": previous_cost,
        "current_total_cost_won": current_cost,
        "total_cost_delta_won": current_cost - previous_cost,
        "context": sorted(
            context or [],
            key=lambda item: tuple(str(item.get(key, "")) for key in sorted(item)),
        ),
        "changes": changes,
    }
