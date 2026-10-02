"""Explain provider operating constraints and the limits of historical signals."""

from __future__ import annotations

from typing import Any

_COUNTED_STATUSES = ("COMPLETED", "OPTED_IN", "DECLINED", "CANCELLED", "UNAVAILABLE")


def provider_realism_profile(
    provider: dict[str, Any], history: list[dict[str, Any]]
) -> dict[str, Any]:
    counts = {status: 0 for status in _COUNTED_STATUSES}
    for row in history:
        status = str(row.get("status", ""))
        if status in counts:
            counts[status] += 1
    opportunities = sum(counts.values())
    accepted = counts["COMPLETED"] + counts["OPTED_IN"] + counts["CANCELLED"]
    all_synthetic = bool(history) and all(
        row.get("provenance")
        and row.get("round_provenance")
        and "SIMULATED FOR PRE-R&D" in str(row["provenance"])
        and "SIMULATED FOR PRE-R&D" in str(row["round_provenance"])
        for row in history
    )
    if not history:
        sample_status = "NO_HISTORY"
        history_scope = "NO_HISTORY"
    elif all_synthetic:
        sample_status = "SYNTHETIC_ONLY"
        history_scope = "SYNTHETIC FOR PRE-R&D"
    else:
        sample_status = "UNVERIFIED_OR_MIXED"
        history_scope = "UNVERIFIED OR MIXED PROVENANCE"

    return {
        "model_version": "PROVIDER_REALISM_V2",
        "history_scope": history_scope,
        "sample_status": sample_status,
        "history_opportunities": opportunities,
        "accepted_opportunities": accepted,
        "declined_opportunities": counts["DECLINED"],
        "unavailable_opportunities": counts["UNAVAILABLE"],
        "cancelled_opportunities": counts["CANCELLED"],
        "completed_opportunities": counts["COMPLETED"],
        "acceptance_rate": accepted / opportunities if opportunities else None,
        "decline_rate": counts["DECLINED"] / opportunities if opportunities else None,
        "completion_rate_after_acceptance": (
            counts["COMPLETED"] / accepted if accepted else None
        ),
        "operating_constraints": {
            "supported_services": sorted(provider.get("supported_services", [])),
            "weekly_windows": len(provider.get("availability", [])),
            "date_specific_windows": len(provider.get("date_availability", [])),
            "maximum_daily_hours": float(provider.get("max_daily_hours", 0)),
            "maximum_monthly_rounds": int(provider.get("max_monthly_rounds", 0)),
            "maximum_travel_time_minutes": int(provider.get("max_travel_time_minutes", 0)),
            "minimum_compensation_won": int(provider.get("minimum_compensation_won", 0)),
        },
        "planner_treatment": {
            "operating_constraints": "HARD_CONSTRAINTS",
            "provider_opt_in": "PREFERENCE_TIE_BREAK_ONLY",
            "unconfirmed_available_status": "NOT_A_PROVIDER_COMMITMENT",
            "historical_outcome_objective_weight": 0,
        },
        "provenance": "DESCRIPTIVE HISTORY; NOT A REAL-WORLD ACCEPTANCE FORECAST",
    }


def summarize_provider_realism(providers: list[dict[str, Any]]) -> dict[str, Any]:
    profiles = [provider.get("realism", {}) for provider in providers]
    return {
        "model_version": "PROVIDER_REALISM_V2",
        "provider_count": len(providers),
        "synthetic_history_only_count": sum(
            profile.get("sample_status") == "SYNTHETIC_ONLY" for profile in profiles
        ),
        "unverified_or_mixed_history_count": sum(
            profile.get("sample_status") == "UNVERIFIED_OR_MIXED" for profile in profiles
        ),
        "no_history_count": sum(
            profile.get("sample_status", "NO_HISTORY") == "NO_HISTORY"
            for profile in profiles
        ),
        "historical_outcomes_used_for_optimization": False,
        "planner_treatment": (
            "DECLARED SERVICE, AVAILABILITY, TIME, TRAVEL, CAPACITY AND COMPENSATION "
            "ARE HARD CONSTRAINTS; OPT-IN IS A PREFERENCE TIE-BREAK; AVAILABLE IS NOT A COMMITMENT"
        ),
        "provenance": "DESCRIPTIVE PROVIDER HISTORY; SIMULATED INPUTS REMAIN LABELED",
    }
