"""Hierarchical demand evidence model (V4 §16-§24).

Layers, each kept separately with its provenance:

1. External empirical prior (KREI need/usage/unmet) -> need *propensity* only.
2. Synthetic planning prior (population-scaled demo baseline) -> SYNTHETIC.
3. Local demographic modifiers -> NO_EFFECT unless explicitly configured
   (configured coefficients are EXPERIMENTAL; none are empirically validated).
4. Local evidence (surveys / field counts) -> conjugate updates.
5. Gates: count, periods, freshness, conflicts, duplicates, source quality.

Outputs are P10/P50/P90 ranges or an explicit FORECAST_NOT_ALLOWED. The KREI
need rate is never multiplied by population to produce service visits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from backend.empirical_priors import prior_for_service, prior_payload
from backend.evidence_policy import evidence_age_days, forecast_evidence_eligible
from backend.provenance import calibration_status_v4
from backend.stats_dist import beta_quantile, negbin_quantiles

MODEL_VERSION = "hierarchical_demand_v4.0"
QUANTILES = (0.1, 0.5, 0.9)

ModifierStatus = Literal["NO_EFFECT", "WEAK_EFFECT", "CONFIGURED_EFFECT"]
MODIFIER_FIELDS = (
    "population_total",
    "population_65_plus",
    "population_75_plus",
    "population_80_plus",
    "single_households_total",
    "single_households_65_plus",
    "facility_access",
    "travel_isolation",
    "existing_service_availability",
)


@dataclass(frozen=True)
class DemandModelConfig:
    """Visible, reviewable settings; no hidden coefficients."""

    # Prior strength as pseudo-observations. These are planner-visible settings,
    # not estimated from data, so they are labelled EXPERIMENTAL.
    need_prior_pseudo_respondents: float = 20.0
    count_prior_pseudo_months: float = 1.0
    min_observation_count: int = 3
    min_unique_periods: int = 2
    min_source_types: int = 1
    modifiers: dict[str, float] = field(default_factory=dict)  # name -> multiplier

    def payload(self) -> dict[str, Any]:
        return {
            "need_prior_pseudo_respondents": self.need_prior_pseudo_respondents,
            "count_prior_pseudo_months": self.count_prior_pseudo_months,
            "min_observation_count": self.min_observation_count,
            "min_unique_periods": self.min_unique_periods,
            "min_source_types": self.min_source_types,
            "configured_modifiers": dict(self.modifiers),
            "badge": "EXPERIMENTAL",
            "note": "사전 강도·보정계수는 실증 검증 전의 설정값입니다.",
        }


DEFAULT_CONFIG = DemandModelConfig()


def need_propensity_range(
    service_type: str,
    *,
    local_respondents: int = 0,
    local_needers: int = 0,
    config: DemandModelConfig = DEFAULT_CONFIG,
) -> dict[str, Any] | None:
    """Beta-Binomial update of the KREI need rate with optional local survey counts."""
    prior = prior_for_service(service_type)
    if prior is None:
        return None
    if local_respondents < 0 or not 0 <= local_needers <= local_respondents:
        raise ValueError("local needers must be between 0 and respondents")
    p0 = prior.need_rate / 100.0
    n0 = config.need_prior_pseudo_respondents
    a, b = p0 * n0 + local_needers, (1 - p0) * n0 + (local_respondents - local_needers)
    p10, p50, p90 = (round(beta_quantile(q, a, b) * 100, 1) for q in QUANTILES)
    local_weight = local_respondents / (local_respondents + n0)
    return {
        "service_type": service_type,
        "quantity": "NEED_PROPENSITY_PERCENT",
        "external_need_rate": prior.need_rate,
        "local_respondents": local_respondents,
        "local_needers": local_needers,
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "local_weight": round(local_weight, 3),
        "label": "지역 조사 반영 필요도" if local_respondents else "농촌 외부 조사 기준값",
        "provenance": (
            "EXTERNAL_EMPIRICAL_PRIOR + LOCAL_OBSERVATION"
            if local_respondents
            else "EXTERNAL_EMPIRICAL_PRIOR"
        ),
        "warning": "필요도(%)는 서비스 회차가 아닙니다. 인구에 곱해 수요 건수로 쓰지 않습니다.",
    }


def gamma_poisson_range(
    observed_monthly_counts: list[int],
    *,
    prior_mean: float | None,
    prior_pseudo_months: float,
) -> dict[str, Any]:
    """Posterior predictive P10/P50/P90 for next-month counts."""
    n = len(observed_monthly_counts)
    total = sum(observed_monthly_counts)
    if prior_mean is None or prior_mean <= 0 or prior_pseudo_months <= 0:
        if n == 0:
            raise ValueError("no prior and no observations")
        shape, rate = max(total, 0.5), float(n)  # Jeffreys-like weak start
        prior_used = False
    else:
        shape = prior_mean * prior_pseudo_months + total
        rate = prior_pseudo_months + n
        prior_used = True
    p10, p50, p90 = negbin_quantiles(shape, rate, QUANTILES)
    weight = n / (n + prior_pseudo_months) if prior_used else 1.0
    return {
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "posterior_mean": round(shape / rate, 3),
        "local_weight": round(weight, 3),
        "prior_used": prior_used,
    }


def weighted_prior_estimate(
    observed: list[int], *, prior_mean: float | None, prior_pseudo_months: float
) -> float | None:
    """Model B (benchmark only): convex mix of prior mean and sample mean."""
    if not observed:
        return prior_mean
    sample_mean = sum(observed) / len(observed)
    if prior_mean is None:
        return sample_mean
    w = len(observed) / (len(observed) + prior_pseudo_months)
    return w * sample_mean + (1 - w) * prior_mean


def modifier_states(config: DemandModelConfig) -> list[dict[str, Any]]:
    states = []
    for name in MODIFIER_FIELDS:
        if name in config.modifiers:
            status: ModifierStatus = "CONFIGURED_EFFECT"
            badge = "EXPERIMENTAL"
        else:
            status, badge = "NO_EFFECT", None
        states.append({
            "modifier": name,
            "status": status,
            "multiplier": config.modifiers.get(name, 1.0),
            "badge": badge,
            "validated": False,
        })
    return states


def _gate(
    observations: list[dict[str, Any]],
    *,
    as_of: date,
    unresolved_conflicts: int,
    unresolved_duplicates: int,
    config: DemandModelConfig,
) -> list[str]:
    reasons = []
    counts = [row for row in observations if row.get("frequency_per_month") is not None]
    if len(counts) < config.min_observation_count:
        reasons.append("MIN_OBSERVATION_COUNT")
    periods = {str(row["occurred_on"])[:7] for row in counts}
    if len(periods) < config.min_unique_periods:
        reasons.append("MIN_UNIQUE_PERIODS")
    latest = max((date.fromisoformat(str(row["occurred_on"])[:10]) for row in counts),
                 default=None)
    if latest is None or not forecast_evidence_eligible(latest, as_of=as_of):
        reasons.append("EVIDENCE_STALE")
    if unresolved_conflicts:
        reasons.append("UNRESOLVED_CONFLICT")
    if unresolved_duplicates:
        reasons.append("UNRESOLVED_DUPLICATE")
    if len({row.get("source_type") for row in counts}) < config.min_source_types:
        reasons.append("SOURCE_QUALITY")
    return reasons


def estimate_area_service_demand(
    *,
    area: dict[str, Any],
    service_type: str,
    observations: list[dict[str, Any]],
    as_of: date,
    synthetic_prior_monthly: float | None,
    unresolved_conflicts: int = 0,
    unresolved_duplicates: int = 0,
    local_calibration_status_v3: str = "UNCALIBRATED",
    local_need_counts: tuple[int, int] | None = None,
    config: DemandModelConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Combine all layers into one explainable record for an area/service pair."""
    usable = [
        row for row in observations
        if row.get("frequency_per_month") is not None
        and date.fromisoformat(str(row["occurred_on"])[:10]) <= as_of
    ]
    reasons = _gate(usable, as_of=as_of, unresolved_conflicts=unresolved_conflicts,
                    unresolved_duplicates=unresolved_duplicates, config=config)
    external = prior_for_service(service_type)
    respondents, needers = local_need_counts or (0, 0)
    need = need_propensity_range(service_type, local_respondents=respondents,
                                 local_needers=needers, config=config)
    # Latest report per month; repeated reports in a month do not inflate the count.
    by_month: dict[str, dict[str, Any]] = {}
    for row in sorted(usable, key=lambda r: (str(r["occurred_on"]), str(r.get("created_at", "")))):
        by_month[str(row["occurred_on"])[:7]] = row
    monthly = [int(row["frequency_per_month"]) for _, row in sorted(by_month.items())]
    multiplier = 1.0
    for value in config.modifiers.values():
        multiplier *= value
    prior_mean = synthetic_prior_monthly * multiplier if synthetic_prior_monthly else None

    count_range = None
    if not reasons:
        count_range = gamma_poisson_range(
            monthly, prior_mean=prior_mean, prior_pseudo_months=config.count_prior_pseudo_months
        )
    status = calibration_status_v4(
        has_external_prior=external is not None,
        local_status_v3=local_calibration_status_v3 if not reasons else "UNCALIBRATED",
    )
    if not reasons and status in {"SYNTHETIC_ONLY", "EXTERNAL_EMPIRICAL"}:
        status = "LOCAL_LIMITED"  # gated local counts exist but no calibration profile
    latest = max((str(row["occurred_on"])[:10] for row in usable), default=None)
    return {
        "area_id": str(area.get("id")),
        "service_type": service_type,
        "model_version": MODEL_VERSION,
        "forecast_status": "FORECAST_ALLOWED" if not reasons else "FORECAST_NOT_ALLOWED",
        "gate_reasons": reasons,
        "calibration_status": status,
        "monthly_count_range": (
            {**count_range, "unit": "회/월", "label": "모델 추정",
             "provenance": "MODEL_ESTIMATE (LOCAL_OBSERVATION + SYNTHETIC prior)"}
            if count_range else None
        ),
        "need_propensity": need,
        "external_prior": prior_payload(external) if external else None,
        "synthetic_prior_monthly": synthetic_prior_monthly,
        "synthetic_prior_label": "모의 데이터",
        "modifiers": modifier_states(config),
        "local_evidence": {
            "observation_count": len(usable),
            "unique_periods": len(by_month),
            "source_types": sorted({str(row.get("source_type")) for row in usable}),
            "latest_observed_on": latest,
            "latest_age_days": (evidence_age_days(date.fromisoformat(latest), as_of=as_of)
                                if latest else None),
            "unresolved_conflicts": unresolved_conflicts,
            "unresolved_duplicates": unresolved_duplicates,
        },
        "config": config.payload(),
    }
