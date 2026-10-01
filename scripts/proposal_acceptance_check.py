"""Run the mapped R1-R13 regression evidence and report traceability honestly."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRACEABILITY_PATH = ROOT / "docs" / "PROPOSAL_REQUIREMENTS_TRACEABILITY.md"
REPORT_PATH = ROOT / "artifacts" / "proposal_acceptance_report.json"

EVIDENCE: dict[str, dict[str, list[str]]] = {
    "R1": {
        "files": [
            "backend/demand.py",
            "backend/database.py",
            "backend/csv_imports.py",
            "backend/main.py",
            "frontend/app/imports/page.tsx",
            "frontend/app/villages/[id]/page.tsx",
        ],
        "tests": [
            "tests/test_demand.py::test_deterministic_evidence_keeps_low_data_at_survey_required",
            "tests/test_demand.py::test_recent_baseline_survey_moves_low_data_to_limited_planning",
            "tests/test_database.py::test_app_database_migrates_once_and_contains_traceable_v11_tables",
            "tests/test_database.py::test_v10_import_batch_migration_preserves_existing_rows_and_foreign_keys",
            "tests/test_api.py::test_survey_persists_synthetic_evidence_and_refreshes_low_data_assessment",
            "tests/test_api.py::test_survey_endpoints_accept_korean_today_before_utc_date_rollover",
            "tests/test_api.py::test_demand_csv_import_tracks_rows_redacts_notes_updates_evidence_and_is_idempotent",
            "tests/test_api.py::test_existing_service_history_import_refreshes_planning_demand_and_reviews_stale_rows",
            "tests/test_csv_imports.py::test_csv_validation_distinguishes_invalid_codes_and_review_rows",
            "tests/test_csv_imports.py::test_existing_service_history_validates_pilot_service_rounds_and_freshness",
        ],
    },
    "R2": {
        "files": [
            "backend/demand.py",
            "backend/database.py",
            "backend/main.py",
            "frontend/app/demand/page.tsx",
            "frontend/lib/api.ts",
            "frontend/lib/types.ts",
        ],
        "tests": [
            "tests/test_demand.py::test_explicit_request_is_schema_valid_and_separated_from_route_planning",
            "tests/test_demand.py::test_explicit_date_time_recurrence_and_urgency_are_canonicalized",
            "tests/test_demand.py::test_year_time_and_monthly_frequency_are_explicit_without_inference",
            "tests/test_demand.py::test_exact_period_and_weekday_preferences_are_not_inferred_from_mentions",
            "tests/test_demand.py::test_single_explicit_date_also_identifies_calendar_period",
            "tests/test_demand.py::test_conflicting_explicit_date_or_time_stays_unknown_and_requires_review",
            "tests/test_demand.py::test_negated_urgency_is_not_marked_urgent",
            "tests/test_demand.py::test_model_cannot_invent_date_time_recurrence_or_urgency",
            "tests/test_demand.py::test_model_constraint_must_be_an_exact_source_phrase_or_known_constraint_id",
            "tests/test_demand.py::test_model_output_must_match_locally_supported_facts",
            "tests/test_demand.py::test_remote_output_uses_json_schema_and_returns_canonical_verified_facts",
            "tests/test_api.py::test_demand_api_uses_schema_valid_local_fallback_without_credentials",
            "tests/test_api.py::test_demand_draft_requires_a_verified_area_and_non_future_survey_date",
            "tests/test_api.py::test_demand_draft_preserves_each_evidence_source",
            "tests/test_api.py::test_demand_draft_approval_persists_redacted_source_human_edits_and_evidence",
            "tests/test_api.py::test_demand_draft_cannot_approve_a_regulated_service_or_unsupported_urgency",
            "tests/test_database.py::test_survey_creates_observation_and_evidence_rows",
        ],
    },
    "R3": {
        "files": [
            "backend/forecast.py",
            "backend/database.py",
            "frontend/app/providers/[id]/page.tsx",
        ],
        "tests": [
            "tests/test_forecast.py::test_insufficient_history_returns_no_forecast_values",
            "tests/test_forecast.py::test_sufficient_balanced_history_returns_deterministic_three_month_ranges",
            "tests/test_forecast.py::test_sparse_area_panel_is_not_extrapolated_to_a_region_forecast",
        ],
    },
    "R4": {
        "files": [
            "backend/forecast.py",
            "backend/database.py",
            "frontend/app/providers/[id]/page.tsx",
        ],
        "tests": [
            "tests/test_database.py::test_sufficient_provider_forecast_is_returned_and_persisted",
            "tests/test_api.py::test_provider_directory_detail_and_round_opt_in_are_persistent",
            "tests/test_regions.py::test_region_catalog_and_filter_keep_only_exact_selected_town",
        ],
    },
    "R5": {
        "files": [
            "backend/database.py",
            "backend/main.py",
            "backend/scheduling.py",
            "backend/routing.py",
            "frontend/app/providers/[id]/page.tsx",
            "frontend/app/imports/page.tsx",
        ],
        "tests": [
            "tests/test_scheduling.py::test_provider_date_availability_overrides_weekly_windows_for_that_service",
            "tests/test_scheduling.py::test_provider_schedule_enforces_monthly_daily_time_window_and_preferred_days",
            "tests/test_scheduling.py::test_provider_schedule_honors_approved_requested_date_and_service_start_time",
            "tests/test_scheduling.py::test_provider_schedule_excludes_requested_dates_when_provider_cannot_meet_exact_time",
            "tests/test_scheduling.py::test_provider_schedule_never_uses_an_explicitly_excluded_weekday",
            "tests/test_scheduling.py::test_provider_schedule_reports_a_requested_date_outside_the_four_week_horizon",
            "tests/test_scheduling.py::test_provider_schedule_passes_exact_times_into_multi_stop_route",
            "tests/test_routing.py::test_multi_stop_route_respects_explicit_service_start_windows",
            "tests/test_api.py::test_provider_availability_csv_validates_provider_and_persists_date_override",
            "tests/test_api.py::test_schedule_plan_passes_only_approved_village_time_windows_to_optimizer",
            "tests/test_api.py::test_provider_month_week_preferences_persist_and_round_choice_has_precedence",
            "tests/test_api.py::test_provider_group_preference_rejects_invalid_periods_and_empty_opportunities",
            "tests/test_database.py::test_provider_opt_in_rejects_unsupported_service_unavailability_and_capacity",
        ],
    },
    "R6": {
        "files": ["backend/database.py", "frontend/app/providers/[id]/page.tsx"],
        "tests": [
            "tests/test_database.py::test_provider_profiles_history_availability_and_opt_in_persist",
            "tests/test_api.py::test_provider_directory_detail_and_round_opt_in_are_persistent",
        ],
    },
    "R7": {
        "files": [
            "backend/optimization.py",
            "backend/scheduling.py",
            "frontend/app/calendar/page.tsx",
        ],
        "tests": [
            "tests/test_optimization.py::test_scenarios_obey_budget_capacity_demand_and_seed_invariants",
            "tests/test_scheduling.py::test_provider_schedule_assigns_eligible_rounds_with_kakao_costs_and_minimum_pay",
            "tests/test_scheduling.py::test_provider_schedule_combines_same_day_stops_when_cached_route_saves_travel",
        ],
    },
    "R8": {
        "files": [
            "backend/optimization.py",
            "backend/scheduling.py",
            "frontend/app/page.tsx",
            "frontend/app/calendar/page.tsx",
            "frontend/lib/types.ts",
        ],
        "tests": [
            "tests/test_optimization.py::test_scenarios_have_distinct_policy_outcomes",
            "tests/test_optimization.py::test_scenarios_report_hub_round_trip_distance_and_max_area_saturation",
            "tests/test_optimization.py::test_balanced_policy_weights_change_the_selected_vulnerable_area",
            "tests/test_scheduling.py::test_provider_balanced_policy_weights_change_vulnerable_area",
        ],
    },
    "R9": {
        "files": [
            "backend/optimization.py",
            "backend/scheduling.py",
            "frontend/app/calendar/page.tsx",
        ],
        "tests": [
            "tests/test_optimization.py::test_minimum_frequency_changes_guarantee_budget_and_truthful_gap",
            "tests/test_optimization.py::test_minimum_guarantee_reports_provider_service_mix_capacity_gap",
            "tests/test_scheduling.py::test_provider_schedule_applies_minimum_round_policy_and_reports_capacity_gap",
        ],
    },
    "R10": {
        "files": [
            "backend/optimization.py",
            "backend/scheduling.py",
            "backend/database.py",
            "backend/main.py",
            "frontend/app/page.tsx",
            "frontend/app/calendar/page.tsx",
            "frontend/lib/types.ts",
        ],
        "tests": [
            "tests/test_optimization.py::test_scenarios_report_hub_round_trip_distance_and_max_area_saturation",
            "tests/test_optimization.py::test_provider_cost_breakdown_reconciles_to_aggregate_scenario_totals",
            "tests/test_optimization.py::test_provider_compensation_floor_is_in_budget_and_cost_breakdown",
            "tests/test_database.py::test_schedule_plan_persists_round_cost_provenance_and_provider_opportunity",
            "tests/test_api.py::test_schedule_history_and_csv_export_are_region_scoped_and_auditable",
        ],
    },
    "R11": {
        "files": [
            "backend/optimization.py",
            "backend/scheduling.py",
            "frontend/app/page.tsx",
            "frontend/app/calendar/page.tsx",
        ],
        "tests": [
            "tests/test_optimization.py::test_allowed_services_and_hub_travel_policy_explain_ineligible_areas",
            "tests/test_optimization.py::test_unmet_minimum_reason_identifies_budget_capacity_and_shared_competition",
            "tests/test_scheduling.py::test_provider_schedule_reports_service_availability_travel_and_budget_gaps",
            "tests/test_scheduling.py::test_provider_schedule_applies_allowed_service_travel_and_compensation_policies",
        ],
    },
    "R12": {
        "files": ["backend/demand.py", "backend/optimization.py", "backend/travel.py"],
        "tests": [
            "tests/test_demand.py::test_explicit_request_is_schema_valid_and_separated_from_route_planning",
            "tests/test_optimization.py::test_scenarios_obey_budget_capacity_demand_and_seed_invariants",
        ],
    },
    "R13": {
        "files": [
            "backend/service_registry.py",
            "backend/database.py",
            "backend/demand.py",
            "backend/csv_imports.py",
            "backend/settings.py",
            "backend/optimization.py",
            "backend/main.py",
            "frontend/app/demand/page.tsx",
            "frontend/lib/api.ts",
            "frontend/lib/types.ts",
        ],
        "tests": [
            "tests/test_database.py::test_reference_seed_keeps_public_snapshots_and_excluded_service_policy",
            "tests/test_demand.py::test_regulated_and_excluded_service_notes_remain_explicit",
            "tests/test_api.py::test_service_registry_marks_regulated_and_excluded_requests_before_planning",
            "tests/test_csv_imports.py::test_csv_validation_rejects_regulated_and_excluded_service_codes",
            "tests/test_api.py::test_overview_rejects_regulated_or_unknown_allowed_services",
            "tests/test_api.py::test_schedule_rejects_services_outside_the_policy_registry",
        ],
    },
}


def read_traceability() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in TRACEABILITY_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 7 and cells[0] in EVIDENCE:
            rows[cells[0]] = {"status": cells[3], "gap": cells[4]}
    return rows


def main() -> int:
    trace = read_traceability()
    all_nodes = sorted({node for item in EVIDENCE.values() for node in item["tests"]})
    missing_nodes = [node for node in all_nodes if not (ROOT / node.split("::", 1)[0]).is_file()]
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *all_nodes],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    test_output = (test_result.stdout + test_result.stderr).strip()
    test_passed = test_result.returncode == 0 and not missing_nodes
    requirements: dict[str, dict[str, Any]] = {}
    technical_failures = bool(missing_nodes) or set(trace) != set(EVIDENCE) or not test_passed

    for requirement_id, evidence in EVIDENCE.items():
        trace_row = trace.get(requirement_id)
        missing_files = [
            relative for relative in evidence["files"] if not (ROOT / relative).is_file()
        ]
        requirement_nodes = evidence["tests"]
        trace_status = trace_row["status"] if trace_row else "MISSING"
        evidence_ok = trace_row is not None and not missing_files and test_passed
        if not evidence_ok:
            status = "FAIL"
        elif trace_status == "COMPLETE":
            status = "PASS"
        elif trace_status in {"PARTIAL", "MISSING", "BLOCKED"}:
            status = trace_status
        else:
            status = "FAIL"
        requirements[requirement_id] = {
            "status": status,
            "traceability_status": trace_status,
            "test_run": "PASS" if test_passed else "FAIL",
            "tests": requirement_nodes,
            "evidence_files": evidence["files"],
            "missing_files": missing_files,
            "remaining_gap": trace_row["gap"] if trace_row else "추적성 표 항목 없음",
        }

    overall = (
        "FAIL"
        if technical_failures or any(item["status"] == "FAIL" for item in requirements.values())
        else "PASS"
        if all(item["status"] == "PASS" for item in requirements.values())
        else "PARTIAL"
    )
    source_files = {
        TRACEABILITY_PATH,
        Path(__file__).resolve(),
        *[ROOT / relative for item in EVIDENCE.values() for relative in item["files"]],
        *[ROOT / node.split("::", 1)[0] for node in all_nodes],
    }
    source_hashes = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source_files)
        if path.is_file()
    }
    fingerprint_material = "\n".join(
        f"{path}:{digest}" for path, digest in sorted(source_hashes.items())
    ).encode("utf-8")
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checked_out_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
        ).stdout.strip(),
        "source_fingerprint_sha256": hashlib.sha256(fingerprint_material).hexdigest(),
        "source_file_sha256": source_hashes,
        "overall_status": overall,
        "pytest_exit_code": test_result.returncode,
        "pytest_output": test_output[-12000:],
        "missing_test_files": missing_nodes,
        "requirements": requirements,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for requirement_id, item in requirements.items():
        print(f"{requirement_id}  {item['status']}")
    print(f"OVERALL: {overall}")
    print(f"REPORT: {REPORT_PATH.relative_to(ROOT)}")
    if test_output:
        print(test_output[-3000:])
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
