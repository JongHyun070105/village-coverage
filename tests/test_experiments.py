from __future__ import annotations

import json
from pathlib import Path

from scripts.run_experiments import _pilot_experiment_data


def test_pilot_experiment_uses_default_region_scope_without_mutating_source() -> None:
    source = json.loads(Path("data/demo.json").read_text(encoding="utf-8"))
    original_area_ids = [area["id"] for area in source["areas"]]
    selected = _pilot_experiment_data(source)

    assert selected["region_id"] == source["default_region_id"]
    assert len(selected["areas"]) == next(
        region["area_count"]
        for region in source["regions"]
        if region["region_id"] == source["default_region_id"]
    )
    assert all(area["region_id"] == selected["region_id"] for area in selected["areas"])
    assert [area["id"] for area in source["areas"]] == original_area_ids
