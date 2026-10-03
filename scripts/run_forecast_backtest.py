"""Forecast backtest V2: three datasets evaluated separately (never pooled).

A. Synthetic controlled series (seeded, known generating process)
B. HomeDoctor operational monthly counts (EXTERNAL_OPERATIONAL_REFERENCE)
C. Local observations (only real, non-simulated local series are eligible)

Usage: uv run python scripts/run_forecast_backtest.py
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.source_snapshots import utc_now  # noqa: E402
from backend.ts_benchmark import MODELS, evaluate_dataset  # noqa: E402

SEED = 2026
MONTHS = 36


def poisson_sample(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 50:  # normal approximation for large means
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    threshold, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


def synthetic_series(seed: int = SEED, count: int = 40) -> dict[str, list[int]]:
    """Seeded rural-scale monthly counts: level x seasonality, Poisson or NB noise."""
    rng = random.Random(seed)
    series = {}
    for index in range(count):
        level = rng.choice([1.5, 3, 5, 8, 12, 20])
        amplitude = rng.choice([0.0, 0.2, 0.4])
        overdispersed = index % 2 == 1
        values = []
        for month in range(MONTHS):
            lam = level * (1 + amplitude * math.sin(2 * math.pi * month / 12))
            if overdispersed:
                lam = rng.gammavariate(3.0, lam / 3.0)  # Gamma-Poisson mixture
            values.append(poisson_sample(rng, lam))
        kind = "nb" if overdispersed else "poisson"
        series[f"syn-{index:02d}-L{level}-A{amplitude}-{kind}"] = values
    return series


def home_doctor_series() -> tuple[dict[str, list[int]], dict]:
    path = ROOT / "artifacts" / "home_doctor_snapshot.json"
    if not path.exists():
        return {}, {"status": "UNAVAILABLE", "reason": "home_doctor_snapshot.json missing"}
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    summary = snapshot.get("summary") or {}
    series: dict[str, list[int]] = {}
    national = summary.get("national_monthly") or []
    if national:
        series["national_total"] = [int(m["total"]) for m in national]
    for branch, points in (summary.get("branch_monthly") or {}).items():
        values = [p["total"] for p in points]
        if all(v is not None for v in values) and sum(values) > 0:
            series[f"branch:{branch}"] = [int(v) for v in values]
    meta = {
        "status": "AVAILABLE" if series else "UNAVAILABLE",
        "periods": summary.get("periods", [])[:1] + summary.get("periods", [])[-1:],
        "retrieved_at": snapshot.get("retrieved_at"),
        "raw_source_hash": snapshot.get("raw_source_hash"),
        "domain_label": summary.get("domain_label"),
        "domain_note": "임대주택 관리홈닥터 운영 건수; 농촌 수요가 아니며 예측 방법 검증에만 사용",
    }
    return series, meta


def main() -> None:
    synthetic = synthetic_series()
    hd, hd_meta = home_doctor_series()
    datasets = {
        "A_SYNTHETIC_CONTROLLED": {
            "provenance": "SIMULATION",
            "series_count": len(synthetic),
            "months": MONTHS,
            "seed": SEED,
            "result": evaluate_dataset(synthetic),
        },
        "B_HOME_DOCTOR_OPERATIONAL": {
            "provenance": "EXTERNAL_OPERATIONAL_REFERENCE",
            "series_count": len(hd),
            **hd_meta,
            "result": evaluate_dataset(hd) if hd else None,
        },
        "C_LOCAL_OBSERVATIONS": {
            "provenance": "LOCAL_OBSERVATION",
            "status": "NOT_AVAILABLE",
            "series_count": 0,
            "reason": (
                "실제 지역 주민 조사·서비스 수행 월별 시계열이 아직 없음. 데모 DB의 조사 관측은 "
                "SIMULATED FOR PRE-R&D이므로 이 데이터셋에 포함하지 않음."
            ),
            "result": None,
        },
    }
    report = {
        "generated_at": utc_now(),
        "method": "rolling-origin one-step-ahead; history strictly before origin; min_train=12",
        "models": list(MODELS),
        "metrics": ["MAE", "MASE", "WAPE", "bias", "coverage_80", "interval_width",
                    "availability", "error_stability"],
        "pooling": "NONE — datasets are reported separately",
        "datasets": datasets,
    }
    out = ROOT / "artifacts" / "forecast_backtest.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, ds in datasets.items():
        sel = (ds.get("result") or {}).get("selection") or {}
        print(name, ds.get("series_count"), "selected:", sel.get("selected"))
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
