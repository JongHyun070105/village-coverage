"""Compare demand estimators under controlled low-sample conditions (V4 §18).

A. Current deterministic (median of observed months; none below 3 months)
B. Weighted prior + local mean (convex mix)
C. Gamma-Poisson conjugate (posterior predictive P10/P50/P90)

True monthly rates are known (seeded). The prior is a deliberately imperfect
synthetic planning prior, as in production. Output: artifacts/demand_model_benchmark.json
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.demand_model_v4 import (  # noqa: E402
    DEFAULT_CONFIG,
    gamma_poisson_range,
    need_propensity_range,
    weighted_prior_estimate,
)
from backend.source_snapshots import utc_now  # noqa: E402
from scripts.run_forecast_backtest import poisson_sample  # noqa: E402

SEED = 2026
AREAS = 400
SAMPLE_SIZES = (1, 2, 3, 6, 12)
PRIOR_PSEUDO_MONTHS = DEFAULT_CONFIG.count_prior_pseudo_months


def run() -> dict:
    rng = random.Random(SEED)
    truths = [rng.choice([0.5, 1, 2, 4, 6, 10, 15]) for _ in range(AREAS)]
    # Synthetic prior is off by a random factor in [0.5, 2] (imperfect, as in reality).
    priors = [t * rng.choice([0.5, 0.75, 1.0, 1.5, 2.0]) for t in truths]
    results = {}
    for n in SAMPLE_SIZES:
        rows = {"A_DETERMINISTIC_MEDIAN": [], "B_WEIGHTED_PRIOR": [], "C_GAMMA_POISSON": []}
        coverage, widths, extreme = [], [], {k: 0 for k in rows}
        for truth, prior in zip(truths, priors, strict=True):
            observed = [poisson_sample(rng, truth) for _ in range(n)]
            next_month = poisson_sample(rng, truth)
            a = statistics.median(observed) if n >= 3 else None
            b = weighted_prior_estimate(observed, prior_mean=prior,
                                        prior_pseudo_months=PRIOR_PSEUDO_MONTHS)
            c = gamma_poisson_range(observed, prior_mean=prior,
                                    prior_pseudo_months=PRIOR_PSEUDO_MONTHS)
            for key, estimate in (("A_DETERMINISTIC_MEDIAN", a), ("B_WEIGHTED_PRIOR", b),
                                  ("C_GAMMA_POISSON", c["posterior_mean"])):
                if estimate is None:
                    continue
                rows[key].append(abs(estimate - truth))
                if abs(estimate - truth) > max(2.0, truth):  # >100% off (or >2 visits)
                    extreme[key] += 1
            coverage.append(c["p10"] <= next_month <= c["p90"])
            widths.append(c["p90"] - c["p10"])
        results[str(n)] = {
            key: {
                "availability": round(len(errs) / AREAS, 3),
                "mae_vs_true_rate": round(statistics.fmean(errs), 3) if errs else None,
                "extreme_error_rate": round(extreme[key] / len(errs), 3) if errs else None,
            }
            for key, errs in rows.items()
        }
        results[str(n)]["C_GAMMA_POISSON"]["p10_p90_next_month_coverage"] = round(
            sum(coverage) / AREAS, 3)
        results[str(n)]["C_GAMMA_POISSON"]["mean_interval_width"] = round(
            statistics.fmean(widths), 3)
    need_examples = {
        f"{needers}/{respondents}": need_propensity_range(
            "laundry", local_respondents=respondents, local_needers=needers)
        for respondents, needers in ((0, 0), (2, 2), (10, 5), (50, 10), (500, 300))
    }
    return {
        "generated_at": utc_now(),
        "seed": SEED,
        "areas": AREAS,
        "provenance": "SIMULATION (controlled truth); not evidence about real villages",
        "prior_pseudo_months": PRIOR_PSEUDO_MONTHS,
        "prior_misspecification_factors": [0.5, 0.75, 1.0, 1.5, 2.0],
        "by_observed_months": results,
        "need_propensity_examples_laundry": {
            key: {k: v[k] for k in ("p10", "p50", "p90", "local_weight", "provenance")}
            for key, v in need_examples.items()
        },
        "recommendation": (
            "저표본(1~2개월)에서는 감마-포아송/가중 사전이 극단 추정을 줄이고, 표본이 늘면 "
            "지역 관측이 지배한다. 계획에는 범위(P10/P50/P90)만 노출하고, 게이트 미충족 시 "
            "전망을 만들지 않는다."
        ),
    }


def main() -> None:
    report = run()
    out = ROOT / "artifacts" / "demand_model_benchmark.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for n, r in report["by_observed_months"].items():
        print(n, {k: (v["mae_vs_true_rate"], v["extreme_error_rate"]) for k, v in r.items()})
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
