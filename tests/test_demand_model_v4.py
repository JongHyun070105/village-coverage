from datetime import date

import pytest

from backend.demand_model_v4 import (
    DemandModelConfig,
    estimate_area_service_demand,
    gamma_poisson_range,
    need_propensity_range,
    weighted_prior_estimate,
)
from backend.stats_dist import beta_quantile, negbin_quantiles, poisson_quantiles

AS_OF = date(2026, 10, 3)
AREA = {"id": "a1", "population_total": 300, "population_65_plus": 120}


def obs(month: str, freq: int, source: str = "phone", day: int = 10) -> dict:
    return {"occurred_on": f"{month}-{day:02d}", "frequency_per_month": freq,
            "source_type": source}


def test_beta_and_count_quantiles_match_known_values():
    assert beta_quantile(0.5, 2, 2) == pytest.approx(0.5, abs=1e-9)
    assert poisson_quantiles(5, (0.1, 0.5, 0.9)) == (2, 5, 8)
    # Gamma-Poisson with a very confident prior converges to Poisson.
    assert negbin_quantiles(5000, 1000, (0.1, 0.5, 0.9)) == (2, 5, 8)


def test_need_prior_without_local_data_is_the_external_value():
    result = need_propensity_range("laundry")
    assert result["external_need_rate"] == 19.0
    assert result["p10"] < 19.0 < result["p90"]
    assert result["provenance"] == "EXTERNAL_EMPIRICAL_PRIOR"
    assert result["quantity"] == "NEED_PROPENSITY_PERCENT"
    assert "회차가 아닙니다" in result["warning"]


def test_small_local_sample_is_shrunk_toward_prior():
    # 2 of 2 respondents need laundry: raw rate 100% would be an extreme estimate.
    result = need_propensity_range("laundry", local_respondents=2, local_needers=2)
    assert result["p50"] < 40
    assert result["local_weight"] < 0.1


def test_large_local_sample_dominates_prior():
    result = need_propensity_range("laundry", local_respondents=2000, local_needers=1200)
    assert result["p50"] == pytest.approx(60.0, abs=1.0)
    assert result["local_weight"] > 0.98


def test_invalid_local_counts_are_rejected():
    with pytest.raises(ValueError):
        need_propensity_range("laundry", local_respondents=2, local_needers=3)


def test_count_shrinkage_prevents_extreme_low_sample_estimates():
    shrunk = gamma_poisson_range([30], prior_mean=4.0, prior_pseudo_months=3.0)
    assert shrunk["posterior_mean"] < 30
    large = gamma_poisson_range([30] * 60, prior_mean=4.0, prior_pseudo_months=3.0)
    assert large["posterior_mean"] == pytest.approx(30, abs=1.5)
    assert large["local_weight"] > 0.9
    assert weighted_prior_estimate([30], prior_mean=4.0, prior_pseudo_months=3.0) == 10.5


def test_output_is_a_range_not_a_point():
    result = gamma_poisson_range([4, 5, 6], prior_mean=5.0, prior_pseudo_months=1.0)
    assert result["p10"] <= result["p50"] <= result["p90"]
    assert result["p10"] < result["p90"]


def good_observations():
    return [obs("2026-07", 4), obs("2026-08", 5, "village_meeting"), obs("2026-09", 6)]


def test_sufficient_fresh_evidence_produces_local_limited_range():
    result = estimate_area_service_demand(
        area=AREA, service_type="laundry", observations=good_observations(), as_of=AS_OF,
        synthetic_prior_monthly=5.0,
    )
    assert result["forecast_status"] == "FORECAST_ALLOWED"
    assert result["calibration_status"] == "LOCAL_LIMITED"
    rng = result["monthly_count_range"]
    assert rng["p10"] <= rng["p50"] <= rng["p90"]
    assert result["external_prior"]["need_rate"] == 19.0


def test_conflicting_evidence_blocks_forecast():
    result = estimate_area_service_demand(
        area=AREA, service_type="laundry", observations=good_observations(), as_of=AS_OF,
        synthetic_prior_monthly=5.0, unresolved_conflicts=1,
    )
    assert result["forecast_status"] == "FORECAST_NOT_ALLOWED"
    assert "UNRESOLVED_CONFLICT" in result["gate_reasons"]
    assert result["monthly_count_range"] is None


def test_unresolved_duplicates_block_forecast():
    result = estimate_area_service_demand(
        area=AREA, service_type="laundry", observations=good_observations(), as_of=AS_OF,
        synthetic_prior_monthly=5.0, unresolved_duplicates=2,
    )
    assert "UNRESOLVED_DUPLICATE" in result["gate_reasons"]


def test_stale_evidence_reduces_eligibility():
    stale = [obs("2024-01", 4), obs("2024-02", 5), obs("2024-03", 6)]
    result = estimate_area_service_demand(
        area=AREA, service_type="laundry", observations=stale, as_of=AS_OF,
        synthetic_prior_monthly=5.0,
    )
    assert "EVIDENCE_STALE" in result["gate_reasons"]
    assert result["calibration_status"] == "EXTERNAL_EMPIRICAL"


def test_low_data_keeps_no_forecast_and_external_prior_does_not_calibrate():
    result = estimate_area_service_demand(
        area=AREA, service_type="laundry", observations=[obs("2026-09", 4)], as_of=AS_OF,
        synthetic_prior_monthly=5.0,
    )
    assert result["forecast_status"] == "FORECAST_NOT_ALLOWED"
    assert set(result["gate_reasons"]) >= {"MIN_OBSERVATION_COUNT", "MIN_UNIQUE_PERIODS"}
    assert result["calibration_status"] == "EXTERNAL_EMPIRICAL"


def test_future_observations_are_ignored():
    future = [*good_observations(), obs("2026-11", 99)]
    with_future = estimate_area_service_demand(
        area=AREA, service_type="laundry", observations=future, as_of=AS_OF,
        synthetic_prior_monthly=5.0,
    )
    without = estimate_area_service_demand(
        area=AREA, service_type="laundry", observations=good_observations(), as_of=AS_OF,
        synthetic_prior_monthly=5.0,
    )
    assert with_future["monthly_count_range"] == without["monthly_count_range"]


def test_same_input_is_deterministic():
    kwargs = dict(area=AREA, service_type="laundry", observations=good_observations(),
                  as_of=AS_OF, synthetic_prior_monthly=5.0)
    assert estimate_area_service_demand(**kwargs) == estimate_area_service_demand(**kwargs)


def test_modifiers_default_to_no_effect_and_configured_are_experimental():
    default = estimate_area_service_demand(
        area=AREA, service_type="laundry", observations=good_observations(), as_of=AS_OF,
        synthetic_prior_monthly=5.0,
    )
    assert all(m["status"] == "NO_EFFECT" for m in default["modifiers"])
    configured = estimate_area_service_demand(
        area=AREA, service_type="laundry", observations=good_observations(), as_of=AS_OF,
        synthetic_prior_monthly=5.0,
        config=DemandModelConfig(modifiers={"population_75_plus": 1.2}),
    )
    flagged = [m for m in configured["modifiers"] if m["status"] == "CONFIGURED_EFFECT"]
    assert flagged and flagged[0]["badge"] == "EXPERIMENTAL" and not flagged[0]["validated"]


def test_unmapped_service_has_no_external_prior():
    result = estimate_area_service_demand(
        area=AREA, service_type="medical_service", observations=[], as_of=AS_OF,
        synthetic_prior_monthly=None,
    )
    assert result["external_prior"] is None
    assert result["calibration_status"] == "SYNTHETIC_ONLY"
