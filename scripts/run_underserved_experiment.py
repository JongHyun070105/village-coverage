#!/usr/bin/env python3
"""Counterfactual experiment v2: request-count-only vs four planning policies (SIMULATED)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BUDGETS_WON = (1_000_000, 2_000_000, 3_000_000, 5_000_000)
OUTPUT = ROOT / "artifacts" / "underserved_experiment_v2.json"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vc-underserved-") as directory:
        os.environ["VILLAGECOVERAGE_APP_DB"] = str(Path(directory) / "app.sqlite")
        from backend import database, underserved
        from backend import main as app_main
        from backend.regions import region_catalog, select_region
        from backend.source_snapshots import utc_now
        from backend.timeutils import korea_today

        demo = app_main._load_demo()
        report: dict = {
            "generated_at": utc_now(),
            "label": "SIMULATION",
            "history_provenance": "SIMULATED",
            "notice": underserved.COMPARISON_NOTICE,
            "policy": underserved.policy_payload(),
            "runs": [],
        }
        for region in region_catalog(demo):
            region_id = region["region_id"]
            connection = database.connect()
            database.seed_reference_data(connection, demo)
            underserved.seed_simulated_history(
                connection, select_region(demo, region_id)["areas"],
                as_of_month=underserved.current_month(korea_today()),
            )
            connection.close()
            for budget in BUDGETS_WON:
                try:
                    _, scenarios = app_main._scenario_data(budget, region_id=region_id)
                except Exception as exc:  # noqa: BLE001 - recorded, not hidden
                    report["runs"].append(
                        {"region_id": region_id, "budget_won": budget, "error": type(exc).__name__}
                    )
                    continue
                report["runs"].append(
                    {
                        "region_id": region_id,
                        "budget_won": budget,
                        "status_counts": scenarios["underserved_comparison"]["status_counts"],
                        "rows": [
                            {
                                key: row[key]
                                for key in (
                                    "policy", "served_units", "ZERO_SERVICE_AREA_COUNT",
                                    "REDUCED_EXCLUSION_COUNT", "underserved_points_covered",
                                    "underserved_points_total", "excluded_areas_served_count",
                                    "excluded_area_count",
                                )
                            }
                            for row in scenarios["underserved_comparison"]["rows"]
                        ],
                    }
                )
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(report['runs'])} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
