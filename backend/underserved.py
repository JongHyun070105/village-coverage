"""Underserved-history model: how long an area has gone without service.

Statuses and priority points come from ``UnderservedPolicy``; nothing is hard-coded in the
solver. Missing months are unknown, never zero. See docs/UNDERSERVED_POLICY.md.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

UNDERSERVED_STATUSES = (
    "RECENTLY_SERVED",
    "WAITING",
    "LONG_UNSERVED",
    "CHRONICALLY_UNSERVED",
    "UNKNOWN",
)


@dataclass(frozen=True)
class UnderservedPolicy:
    window_months: int = 12
    min_known_months: int = 3
    stale_after_months: int = 3
    recently_served_max_months: int = 2
    waiting_max_months: int = 5
    long_unserved_max_months: int = 11
    status_points: dict[str, int] = field(
        default_factory=lambda: {
            "RECENTLY_SERVED": 0,
            "WAITING": 1,
            "LONG_UNSERVED": 3,
            "CHRONICALLY_UNSERVED": 5,
            "UNKNOWN": 0,
        }
    )

    def validate(self) -> None:
        ordered = (
            self.recently_served_max_months,
            self.waiting_max_months,
            self.long_unserved_max_months,
        )
        if list(ordered) != sorted(set(ordered)) or ordered[0] < 0:
            raise ValueError("underserved thresholds must be strictly increasing")
        if self.min_known_months < 1 or self.window_months < self.min_known_months:
            raise ValueError("underserved window must cover the minimum known months")
        if set(self.status_points) != set(UNDERSERVED_STATUSES):
            raise ValueError("status_points must define every underserved status")
        if any(points < 0 for points in self.status_points.values()):
            raise ValueError("status points must be nonnegative")


DEFAULT_UNDERSERVED_POLICY = UnderservedPolicy()
DEFAULT_UNDERSERVED_POLICY.validate()


@dataclass(frozen=True)
class AreaServiceHistoryMetric:
    area_id: str
    service_type: str
    as_of_month: str
    known_months: int
    served_months: int
    months_since_last_service: int | None
    unserved_share: float | None
    status: str
    points: int
    provenance: str
    basis: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "area_id": self.area_id,
            "service_type": self.service_type,
            "as_of_month": self.as_of_month,
            "known_months": self.known_months,
            "served_months": self.served_months,
            "months_since_last_service": self.months_since_last_service,
            "unserved_share": self.unserved_share,
            "underserved_status": self.status,
            "underserved_points": self.points,
            "provenance": self.provenance,
            "basis": self.basis,
        }


def month_index(month: str) -> int:
    year, value = month.split("-")
    return int(year) * 12 + int(value) - 1


def month_label(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def current_month(today: date) -> str:
    return f"{today.year:04d}-{today.month:02d}"


def compute_metric(
    area_id: str,
    service_type: str,
    rows: list[dict[str, Any]],
    *,
    as_of_month: str,
    policy: UnderservedPolicy = DEFAULT_UNDERSERVED_POLICY,
) -> AreaServiceHistoryMetric:
    as_of = month_index(as_of_month)
    window = {
        month_index(str(row["month"])): int(row["rounds_delivered"])
        for row in rows
        if as_of - policy.window_months < month_index(str(row["month"])) <= as_of
    }
    provenances = sorted({str(row["provenance"]) for row in rows}) or ["NONE"]
    provenance = "+".join(provenances)

    def unknown(basis: str) -> AreaServiceHistoryMetric:
        return AreaServiceHistoryMetric(
            area_id, service_type, as_of_month, len(window),
            sum(1 for value in window.values() if value > 0), None, None,
            "UNKNOWN", policy.status_points["UNKNOWN"], provenance, basis,
        )

    if len(window) < policy.min_known_months:
        return unknown("TOO_FEW_KNOWN_MONTHS")
    newest = max(window)
    if as_of - newest > policy.stale_after_months:
        return unknown("HISTORY_STALE")
    served = [index for index, value in window.items() if value > 0]
    if served:
        months_since = as_of - max(served)
        basis = "LAST_SERVICE_MONTH"
    else:
        months_since = as_of - min(window) + 1
        basis = "NO_SERVICE_IN_KNOWN_WINDOW_LOWER_BOUND"
    if months_since <= policy.recently_served_max_months:
        status = "RECENTLY_SERVED"
    elif months_since <= policy.waiting_max_months:
        status = "WAITING"
    elif months_since <= policy.long_unserved_max_months:
        status = "LONG_UNSERVED"
    else:
        status = "CHRONICALLY_UNSERVED"
    return AreaServiceHistoryMetric(
        area_id, service_type, as_of_month, len(window), len(served), months_since,
        round(1 - len(served) / len(window), 4), status, policy.status_points[status],
        provenance, basis,
    )


def upsert_history_month(
    connection: sqlite3.Connection,
    *,
    area_id: str,
    service_type: str,
    month: str,
    rounds_delivered: int,
    provenance: str,
) -> None:
    connection.execute(
        """INSERT INTO area_service_history(
             area_id, service_type, month, rounds_delivered, provenance, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(area_id, service_type, month) DO UPDATE SET
             rounds_delivered=excluded.rounds_delivered,
             provenance=excluded.provenance""",
        (
            area_id, service_type, month, rounds_delivered, provenance,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )


def history_rows(
    connection: sqlite3.Connection, area_id: str, service_type: str
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            """SELECT month, rounds_delivered, provenance FROM area_service_history
               WHERE area_id=? AND service_type=? ORDER BY month""",
            (area_id, service_type),
        ).fetchall()
    ]


def area_metric(
    connection: sqlite3.Connection,
    area_id: str,
    service_type: str,
    *,
    as_of_month: str,
    policy: UnderservedPolicy = DEFAULT_UNDERSERVED_POLICY,
) -> AreaServiceHistoryMetric:
    return compute_metric(
        area_id, service_type, history_rows(connection, area_id, service_type),
        as_of_month=as_of_month, policy=policy,
    )


_DEMO_PATTERNS = (
    "RECENT",
    "WAITING",
    "LONG",
    "CHRONIC",
    "NO_DATA",
)


def demo_pattern(area_id: str) -> str:
    digest = hashlib.sha256(f"underserved-demo:{area_id}".encode()).digest()
    return _DEMO_PATTERNS[digest[0] % len(_DEMO_PATTERNS)]


def simulated_history(area_id: str, as_of_month: str, window_months: int = 12) -> list[int | None]:
    """Deterministic SIMULATED monthly rounds (oldest first); None means no record."""
    pattern = demo_pattern(area_id)
    last_service_ago = {"RECENT": 1, "WAITING": 4, "LONG": 8, "CHRONIC": None}.get(pattern)
    values: list[int | None] = []
    for months_ago in range(window_months - 1, -1, -1):
        if pattern == "NO_DATA":
            values.append(None)
        elif last_service_ago is None:
            values.append(0)
        else:
            values.append(2 if months_ago >= last_service_ago else 0)
    return values


def seed_simulated_history(
    connection: sqlite3.Connection,
    areas: list[dict[str, Any]],
    *,
    as_of_month: str,
    window_months: int = 12,
) -> int:
    """Insert deterministic SIMULATED history; never overwrites REAL_REPORTED rows."""
    base = month_index(as_of_month)
    inserted = 0
    for area in areas:
        area_id = str(area["id"])
        service_type = str(area["service_type"])
        values = simulated_history(area_id, as_of_month, window_months)
        for offset, value in enumerate(values):
            if value is None:
                continue
            month = month_label(base - (window_months - 1 - offset))
            existing = connection.execute(
                """SELECT provenance FROM area_service_history
                   WHERE area_id=? AND service_type=? AND month=?""",
                (area_id, service_type, month),
            ).fetchone()
            if existing is not None and existing["provenance"] != "SIMULATED":
                continue
            upsert_history_month(
                connection, area_id=area_id, service_type=service_type, month=month,
                rounds_delivered=value, provenance="SIMULATED",
            )
            inserted += 1
    connection.commit()
    return inserted


def apply_to_area(
    area: dict[str, Any],
    connection: sqlite3.Connection,
    *,
    today: date,
    policy: UnderservedPolicy = DEFAULT_UNDERSERVED_POLICY,
) -> None:
    metric = area_metric(
        connection, str(area["id"]), str(area["service_type"]),
        as_of_month=current_month(today), policy=policy,
    )
    area["underserved_status"] = metric.status
    area["underserved_points"] = metric.points
    area["underserved_metric"] = metric.as_dict()


def policy_payload(policy: UnderservedPolicy = DEFAULT_UNDERSERVED_POLICY) -> dict[str, Any]:
    return {
        "window_months": policy.window_months,
        "min_known_months": policy.min_known_months,
        "stale_after_months": policy.stale_after_months,
        "thresholds_months": {
            "RECENTLY_SERVED": f"<= {policy.recently_served_max_months}",
            "WAITING": f"<= {policy.waiting_max_months}",
            "LONG_UNSERVED": f"<= {policy.long_unserved_max_months}",
            "CHRONICALLY_UNSERVED": f"> {policy.long_unserved_max_months}",
        },
        "status_points": dict(policy.status_points),
        "unknown_rule": "UNKNOWN은 가점 0이며, 서비스 이력이 없다는 뜻이 아닙니다.",
    }


EXCLUDED_STATUSES = frozenset({"LONG_UNSERVED", "CHRONICALLY_UNSERVED"})


def plan_outcome(areas: list[dict[str, Any]], served_units: dict[str, int]) -> dict[str, Any]:
    """Simulated underserved KPIs of one plan. Counts only; no per-resident claims."""
    demand_areas = [a for a in areas if int(a.get("simulated_monthly_demand", 0)) > 0]
    zero_service = [str(a["id"]) for a in demand_areas if served_units.get(str(a["id"]), 0) <= 0]
    excluded = [a for a in demand_areas if a.get("underserved_status") in EXCLUDED_STATUSES]
    excluded_served = [a for a in excluded if served_units.get(str(a["id"]), 0) > 0]
    points = sum(
        int(a.get("underserved_points", 0) or 0)
        for a in demand_areas
        if served_units.get(str(a["id"]), 0) > 0
    )
    return {
        "ZERO_SERVICE_AREA_COUNT": len(zero_service),
        "zero_service_area_ids": sorted(zero_service),
        "underserved_points_covered": points,
        "underserved_points_total": sum(int(a.get("underserved_points", 0) or 0) for a in areas),
        "excluded_area_count": len(excluded),
        "excluded_areas_served_count": len(excluded_served),
        "excluded_area_ids_served": sorted(str(a["id"]) for a in excluded_served),
        "label": "SIMULATION",
    }


def reduced_exclusion_count(outcome: dict[str, Any], baseline: dict[str, Any]) -> int:
    """Excluded areas served by this plan but not by the baseline plan (simulated count)."""
    return len(
        set(outcome["excluded_area_ids_served"]) - set(baseline["excluded_area_ids_served"])
    )


POLICY_ORDER = ("request_count_only", "efficiency", "balanced", "underserved_first",
                "minimum_coverage")
POLICY_LABELS_KO = {
    "request_count_only": "요청 건수 순(기준선)",
    "efficiency": "효율 우선",
    "balanced": "균형 v3",
    "underserved_first": "소외 최소화",
    "minimum_coverage": "최소 서비스 보장",
}
COMPARISON_NOTICE = (
    "시뮬레이션 비교입니다. 실제 주민 수혜나 감소율을 뜻하지 않으며, "
    "입력된 서비스 이력과 가정에 따라 달라집니다."
)


def compare_policies(
    areas: list[dict[str, Any]],
    baseline_units_by_area: dict[str, int],
    scenario_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    baseline = plan_outcome(areas, baseline_units_by_area)
    rows = [
        {
            "policy": "request_count_only",
            "label_ko": POLICY_LABELS_KO["request_count_only"],
            "served_units": sum(baseline_units_by_area.values()),
            "REDUCED_EXCLUSION_COUNT": 0,
            **baseline,
        }
    ]
    for key in POLICY_ORDER[1:]:
        result = scenario_results.get(key)
        if result is None:
            continue
        outcome = result.get("underserved_outcome") or plan_outcome(areas, {})
        rows.append(
            {
                "policy": key,
                "label_ko": POLICY_LABELS_KO[key],
                "served_units": result.get("served_units"),
                "REDUCED_EXCLUSION_COUNT": reduced_exclusion_count(outcome, baseline),
                **outcome,
            }
        )
    return {
        "label": "SIMULATION",
        "notice": COMPARISON_NOTICE,
        "kpi_definitions": {
            "ZERO_SERVICE_AREA_COUNT": "수요가 있으나 현재 계획에서 서비스가 배정되지 않은 권역 수",
            "REDUCED_EXCLUSION_COUNT": (
                "요청 건수 기준선에서는 서비스가 없고 이 정책에서는 배정된 "
                "장기·만성 미서비스 권역 수"
            ),
        },
        "status_counts": {
            status: sum(1 for a in areas if a.get("underserved_status") == status)
            for status in UNDERSERVED_STATUSES
        },
        "rows": rows,
    }
