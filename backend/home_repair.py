"""SIMPLE_HOME_REPAIR demo profile: regulation gate, job catalog, job-based demand, provider fit.

Everything numeric here is a SIMULATED planning assumption, not an observed rate. The only
external anchor is the KREI need rate, which is a need share and not a job count. Regulated or
risky work is never accepted as simple repair, even when a simple job is mentioned alongside it.
"""

from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from backend.empirical_priors import prior_for_service

PROFILE_ID = "SIMPLE_HOME_REPAIR"
PROVENANCE = "SIMULATED: DEMO PLANNING ASSUMPTION"
MATERIAL_LEVELS = ("NONE", "LOW", "MEDIUM", "HIGH")
_MATERIAL_RANK = {level: rank for rank, level in enumerate(MATERIAL_LEVELS)}
CAPABILITY_PROVENANCES = ("UNSPECIFIED", "SIMULATED", "PROVIDER_REPORTED")


@dataclass(frozen=True, slots=True)
class JobSpec:
    job_id: str
    label_ko: str
    keywords: tuple[str, ...]
    minutes_min: int
    minutes_likely: int
    minutes_max: int
    material_level: str
    material_cost_won: tuple[int, int]
    share: float


# Shares sum to 1.0 and describe a simulated job mix, not an observed one.
JOB_CATALOG: tuple[JobSpec, ...] = (
    JobSpec("bulb_replace", "전구·형광등 교체", ("전구", "형광등"), 10, 15, 30,
            "LOW", (2_000, 10_000), 0.30),
    JobSpec("screen_door_patch", "방충망 보수", ("방충망",), 20, 40, 90,
            "LOW", (5_000, 30_000), 0.20),
    JobSpec("door_handle", "문고리·손잡이 교체", ("문고리", "손잡이", "도어락 건전지"), 20, 35, 70,
            "LOW", (8_000, 40_000), 0.20),
    JobSpec("faucet_part", "수전·세면대 부속 교체", ("수전", "세면대", "패킹"), 30, 50, 120,
            "MEDIUM", (5_000, 50_000), 0.15),
    JobSpec("hinge_adjust", "문짝·경첩 조정", ("경첩", "문짝"), 15, 30, 60,
            "LOW", (3_000, 20_000), 0.15),
)
GENERIC_JOB_ID = "generic_unspecified"
GENERIC_MINUTES = (15, 45, 180)

# category -> (terms, regulation level, reason). Terms are matched with whitespace removed.
RISK_CATEGORIES: dict[str, tuple[tuple[str, ...], str, str]] = {
    "GAS_BOILER": (
        ("보일러", "가스", "도시가스", "가스레인지", "연통"),
        "LICENSE_REQUIRED",
        "가스·보일러 작업은 자격 보유자가 해야 합니다.",
    ),
    "ELECTRICAL": (
        ("누전", "전기배선", "배선공사", "전기수리", "전기공사", "차단기", "콘센트", "합선",
         "스위치교체"),
        "LICENSE_REQUIRED",
        "전기 공사·배선 작업은 자격 보유자가 해야 합니다.",
    ),
    "PLUMBING_WATERPROOF": (
        ("누수", "방수", "배관", "하수구막힘", "동파"),
        "LICENSE_REQUIRED",
        "배관·방수 작업은 전문 시공 범위입니다.",
    ),
    "STRUCTURAL": (
        ("지붕", "철거", "구조보강", "벽체", "기둥", "슬레이트"),
        "LICENSE_REQUIRED",
        "구조·지붕 작업은 전문 시공 범위입니다.",
    ),
    "HAZARD": (
        ("석면", "고소작업", "사다리작업", "추락위험"),
        "EXCLUDED",
        "석면·고소 작업은 초기 시범사업 범위에서 제외합니다.",
    ),
}
GENERIC_REPAIR_TERMS = ("수리", "고장", "고쳐", "교체", "보수", "손봐")


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def licensed_terms() -> tuple[str, ...]:
    seen: list[str] = []
    for terms, _, _ in RISK_CATEGORIES.values():
        for term in terms:
            if term not in seen:
                seen.append(term)
    return tuple(seen)


def classify_repair_text(text: str) -> dict[str, Any]:
    """Return a gate decision; only SIMPLE_REPAIR may enter the simple-repair plan."""
    squashed = _squash(text or "")
    blocked: list[dict[str, str]] = []
    for category, (terms, level, reason) in RISK_CATEGORIES.items():
        hits = [term for term in terms if term in squashed]
        if hits:
            blocked.append(
                {"category": category, "regulation_level": level, "reason": reason,
                 "matched_terms": ",".join(hits)}
            )
    simple = [job for job in JOB_CATALOG if any(_squash(k) in squashed for k in job.keywords)]
    if blocked:
        level = (
            "EXCLUDED"
            if any(item["regulation_level"] == "EXCLUDED" for item in blocked)
            else "LICENSE_REQUIRED"
        )
        return {
            "classification": level,
            "regulation_level": level,
            "matched_jobs": [],
            "simple_jobs_detected": [job.job_id for job in simple],
            "blocked": blocked,
            "reason": (
                "위험·규제 작업이 포함되어 간단 수리로 접수하지 않습니다. "
                "담당자 분리 검토가 필요합니다."
            ),
        }
    if simple:
        return {
            "classification": "SIMPLE_REPAIR",
            "regulation_level": "LIMITED",
            "matched_jobs": [job.job_id for job in simple],
            "simple_jobs_detected": [job.job_id for job in simple],
            "blocked": [],
            "reason": "간단 수리 목록에 해당합니다.",
        }
    if any(term in squashed for term in GENERIC_REPAIR_TERMS):
        return {
            "classification": "NEEDS_REVIEW",
            "regulation_level": "LIMITED",
            "matched_jobs": [],
            "simple_jobs_detected": [],
            "blocked": [],
            "reason": "작업 내용이 불명확해 간단 수리 여부를 담당자가 확인해야 합니다.",
        }
    return {
        "classification": "NOT_REPAIR",
        "regulation_level": "UNREGULATED",
        "matched_jobs": [],
        "simple_jobs_detected": [],
        "blocked": [],
        "reason": "수리 요청으로 보이지 않습니다.",
    }


def job_by_id(job_id: str) -> JobSpec:
    for job in JOB_CATALOG:
        if job.job_id == job_id:
            return job
    raise KeyError(job_id)


def job_payload(job: JobSpec) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "label_ko": job.label_ko,
        "duration_minutes": {
            "min": job.minutes_min, "likely": job.minutes_likely, "max": job.minutes_max,
        },
        "material_level": job.material_level,
        "material_cost_won": {"low": job.material_cost_won[0], "high": job.material_cost_won[1]},
        "mix_share": job.share,
        "provenance": PROVENANCE,
    }


def profile_payload() -> dict[str, Any]:
    return {
        "profile_id": PROFILE_ID,
        "unit_type": "JOB",
        "regulation_level": "LIMITED",
        "jobs": [job_payload(job) for job in JOB_CATALOG],
        "blocked_categories": [
            {"category": category, "regulation_level": level, "reason": reason}
            for category, (_, level, reason) in RISK_CATEGORIES.items()
        ],
        "uncertainty": {
            "duration": "min/likely/max 분 단위 시뮬레이션 가정",
            "material": (
                "NONE/LOW/MEDIUM/HIGH/UNKNOWN. "
                "불명확한 요청은 UNKNOWN으로 두고 0원으로 계산하지 않습니다."
            ),
        },
        "provenance": PROVENANCE,
        "notice": "수치는 데모용 가정이며 관측값이 아닙니다.",
    }


# Simulated scenario bounds (not statistical quantiles): LOW / MID / HIGH.
JOBS_PER_NEEDING_HOUSEHOLD_YEAR = {"low": 0.5, "mid": 1.0, "high": 2.0}
PUBLIC_UPTAKE_SHARE = {"low": 0.20, "mid": 0.35, "high": 0.60}


def estimate_area_job_demand(area: dict[str, Any]) -> dict[str, Any]:
    """Monthly job-count and workload range from eligible households; independent of laundry."""
    eligible = int(area.get("single_households_65_plus", 0) or 0)
    prior = prior_for_service("home_repair")
    need_rate = (prior.need_rate / 100.0) if prior else None
    if need_rate is None or eligible <= 0:
        return {
            "area_id": area.get("id"),
            "eligible_households": eligible,
            "jobs_per_month": None,
            "status": "INSUFFICIENT_INPUT",
            "provenance": PROVENANCE,
        }
    jobs = {
        key: eligible
        * need_rate
        * JOBS_PER_NEEDING_HOUSEHOLD_YEAR[key]
        / 12.0
        * PUBLIC_UPTAKE_SHARE[key]
        for key in ("low", "mid", "high")
    }
    mix_minutes = {
        "low": sum(job.share * job.minutes_min for job in JOB_CATALOG),
        "mid": sum(job.share * job.minutes_likely for job in JOB_CATALOG),
        "high": sum(job.share * job.minutes_max for job in JOB_CATALOG),
    }
    mix_cost = {
        "low": sum(job.share * job.material_cost_won[0] for job in JOB_CATALOG),
        "high": sum(job.share * job.material_cost_won[1] for job in JOB_CATALOG),
    }
    return {
        "area_id": area.get("id"),
        "eligible_households": eligible,
        "need_rate_external": need_rate,
        "need_rate_scope": "EXTERNAL EMPIRICAL (KREI): 농촌 외부 조사 기준값, 마을 실측 아님",
        "jobs_per_month": {key: round(value, 2) for key, value in jobs.items()},
        "work_minutes_per_job": {key: round(value, 1) for key, value in mix_minutes.items()},
        "work_hours_per_month": {
            key: round(jobs[key] * mix_minutes[key] / 60.0, 2) for key in ("low", "mid", "high")
        },
        "material_cost_won_per_job": {
            "low": round(mix_cost["low"]), "high": round(mix_cost["high"]),
        },
        "material_cost_won_per_month": {
            "low": round(jobs["low"] * mix_cost["low"]),
            "high": round(jobs["high"] * mix_cost["high"]),
        },
        "material_level_mix": "LOW 중심, 일부 MEDIUM",
        "bounds_are_quantiles": False,
        "status": "ESTIMATED",
        "provenance": PROVENANCE,
    }


def planned_visit_minutes(job_ids: list[str] | None = None) -> int:
    """Planning duration for one repair visit: likely minutes of the job (or mix), 5-min steps."""
    if job_ids:
        likely = sum(job_by_id(job_id).minutes_likely for job_id in job_ids)
    else:
        likely = round(sum(job.share * job.minutes_likely for job in JOB_CATALOG))
    return int(math.ceil(max(likely, 1) / 5.0) * 5)


def apply_to_area(area: dict[str, Any]) -> dict[str, Any]:
    """Opt-in: use job-based duration for a home_repair area. Other services are untouched."""
    if area.get("service_type") != "home_repair":
        return area
    area["service_duration_minutes"] = planned_visit_minutes()
    area["home_repair_profile"] = PROFILE_ID
    return area


def provider_job_fit(capability: dict[str, Any], job: JobSpec) -> dict[str, Any]:
    """Classify a provider's declared capability against a job; unknown stays UNVERIFIED."""
    reasons: list[str] = []
    status = "FIT"
    max_minutes = capability.get("max_job_minutes")
    handling = capability.get("material_handling") or "UNKNOWN"
    tools = capability.get("tools_available")
    if tools == 0:
        return {"job_id": job.job_id, "status": "NOT_FIT", "reasons": ["TOOLS_MISSING"]}
    if handling in _MATERIAL_RANK and _MATERIAL_RANK[handling] < _MATERIAL_RANK[job.material_level]:
        return {"job_id": job.job_id, "status": "NOT_FIT", "reasons": ["MATERIAL_HANDLING_LOW"]}
    if max_minutes is not None and int(max_minutes) < job.minutes_likely:
        return {"job_id": job.job_id, "status": "NOT_FIT", "reasons": ["JOB_TOO_LONG"]}
    if max_minutes is None:
        status = "UNVERIFIED"
        reasons.append("MAX_JOB_MINUTES_UNKNOWN")
    elif int(max_minutes) < job.minutes_max:
        status = "FIT_WITH_DURATION_RISK"
        reasons.append("MAX_DURATION_EXCEEDS_LIMIT")
    if handling == "UNKNOWN":
        status = "UNVERIFIED" if status in ("FIT", "UNVERIFIED") else status
        reasons.append("MATERIAL_HANDLING_UNKNOWN")
    if tools is None:
        status = "UNVERIFIED" if status in ("FIT", "UNVERIFIED") else status
        reasons.append("TOOLS_UNKNOWN")
    return {"job_id": job.job_id, "status": status, "reasons": reasons}


def provider_profile_fit(capability: dict[str, Any]) -> dict[str, Any]:
    fits = [provider_job_fit(capability, job) for job in JOB_CATALOG]
    eligible = [fit["job_id"] for fit in fits if fit["status"] in ("FIT", "FIT_WITH_DURATION_RISK")]
    return {
        "capability": capability,
        "job_fits": fits,
        "eligible_job_ids": eligible,
        "all_jobs_verified": all(fit["status"] != "UNVERIFIED" for fit in fits),
    }


def get_capability(connection: sqlite3.Connection, provider_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT max_job_minutes, material_handling, tools_available, capability_provenance "
        "FROM provider_services WHERE provider_id=? AND service_type='home_repair'",
        (provider_id,),
    ).fetchone()
    return dict(row) if row else None


def set_capability(
    connection: sqlite3.Connection,
    provider_id: str,
    *,
    max_job_minutes: int | None,
    material_handling: str,
    tools_available: bool | None,
    provenance: str,
) -> bool:
    cursor = connection.execute(
        "UPDATE provider_services SET max_job_minutes=?, material_handling=?, tools_available=?, "
        "capability_provenance=? WHERE provider_id=? AND service_type='home_repair'",
        (
            max_job_minutes,
            material_handling,
            None if tools_available is None else int(tools_available),
            provenance,
            provider_id,
        ),
    )
    return cursor.rowcount > 0
