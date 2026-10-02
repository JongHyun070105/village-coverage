"""Provider participation and policy weight sensitivity analysis (§15, §16)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend import scheduling
from backend.plan_changes import build_plan_change_explanation
from backend.settings import PlanningPolicy


def _hhi_concentration(round_counts: list[int]) -> float:
    """Herfindahl-Hirschman Index for round allocation concentration (0.0 to 1.0)."""
    total = sum(round_counts)
    if total == 0:
        return 0.0
    shares = [count / total for count in round_counts]
    return round(sum(s * s for s in shares), 4)


def run_provider_participation_sensitivity(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    connection: Any,
    budget_won: int,
    *,
    policy: PlanningPolicy | None = None,
) -> dict[str, Any]:
    """Evaluate deterministic provider participation scenarios (§15).
    
    Distinguishes whether an unmet plan is resolvable by money alone or bounded by capacity.
    """
    effective_policy = policy or PlanningPolicy()
    
    # Sort providers by monthly rounds descending to identify top capacity provider
    sorted_providers = sorted(
        providers, key=lambda p: int(p.get("max_monthly_rounds", 0)), reverse=True
    )
    
    scenarios_def: list[dict[str, Any]] = [
        {
            "key": "ALL_AVAILABLE",
            "name": "전체 공급자 참여 (100%)",
            "active_providers": deepcopy(providers),
            "declined_names": [],
        }
    ]
    
    if len(providers) >= 2:
        # Scenario 2: One normal provider drops out (the last one)
        drop_one = deepcopy(providers[:-1])
        scenarios_def.append(
            {
                "key": "ONE_PROVIDER_DECLINED",
                "name": "1개 공급자 불참",
                "active_providers": drop_one,
                "declined_names": [str(providers[-1].get("name", providers[-1]["provider_id"]))],
            }
        )
        
        # Scenario 3: Top capacity provider drops out
        top_p = sorted_providers[0]
        drop_top = [p for p in deepcopy(providers) if p["provider_id"] != top_p["provider_id"]]
        scenarios_def.append(
            {
                "key": "TOP_CAPACITY_PROVIDER_DECLINED",
                "name": "최대 공급자 불참",
                "active_providers": drop_top,
                "declined_names": [str(top_p.get("name", top_p["provider_id"]))],
            }
        )
    
    if len(providers) >= 3:
        # Scenario 4: Multiple providers drop out (keep only top 1 or ~50%)
        keep_count = max(1, len(providers) // 2)
        drop_multiple = deepcopy(sorted_providers[:keep_count])
        declined = [
            str(p.get("name", p["provider_id"])) for p in sorted_providers[keep_count:]
        ]
        scenarios_def.append(
            {
                "key": "MULTIPLE_DECLINED",
                "name": "다수 공급자 불참 (50% 수준)",
                "active_providers": drop_multiple,
                "declined_names": declined,
            }
        )
    
    results: list[dict[str, Any]] = []
    baseline_rounds: list[dict[str, Any]] = []
    
    for idx, scen in enumerate(scenarios_def):
        active_p = scen["active_providers"]
        plan = scheduling.generate_provider_schedule(
            areas,
            active_p,
            connection,
            budget_won,
            scenario="balanced",
            policy=effective_policy,
            allow_route_fallback=True,
            include_timing=True,
        )
        
        rounds = plan.get("rounds", [])
        if idx == 0:
            baseline_rounds = rounds
            replan_changes = {"change_count": 0, "changes": []}
        else:
            replan_changes = build_plan_change_explanation(
                baseline_rounds,
                rounds,
                reason="PROVIDER_DECLINED_OR_UNAVAILABLE",
                context=[{"declined": scen["declined_names"]}],
            )
            
        covered_count = plan.get("covered_areas", 0)
        total_demand = sum(int(a.get("simulated_monthly_demand", 0)) for a in areas)
        served_units = plan.get("served_units", 0) or 0
        missing_capacity = max(0, total_demand - served_units)
        budget_gap = int(plan.get("budget_gap_won") or 0)
        total_avail_cap = sum(int(p.get("max_monthly_rounds", 0)) for p in active_p)
        
        # Classification: Money Resolvable vs Non-Monetary (Capacity Shortage)
        if plan.get("minimum_coverage_met", False):
            bottleneck = "FEASIBLE"
            bottleneck_explanation = "최소 보장 요건을 모두 충족했습니다."
            money_resolvable = True
        elif total_avail_cap < sum(effective_policy.minimum_services_per_area for _ in areas):
            bottleneck = "CAPACITY_SHORTAGE"
            bottleneck_explanation = (
                f"총 가용 용량({total_avail_cap}회)이 권역별 최소 보장 기준에 미달하여 "
                "예산 증액만으로는 해결 불가합니다 (추가 공급자 필요)."
            )
            money_resolvable = False
        elif budget_gap > 0 and total_avail_cap >= total_demand:
            bottleneck = "MONEY_SHORTAGE"
            bottleneck_explanation = f"추가 예산({budget_gap:,}원) 확보 시 해결 가능합니다."
            money_resolvable = True
        else:
            bottleneck = "CAPACITY_SHORTAGE"
            bottleneck_explanation = (
                "공급자 서비스 유형 불일치 또는 특정 서비스 용량 한계로 "
                "예산 증액만으로 미충족됩니다."
            )
            money_resolvable = False
            
        results.append(
            {
                "scenario_key": scen["key"],
                "scenario_name": scen["name"],
                "active_provider_count": len(active_p),
                "declined_providers": scen["declined_names"],
                "covered_areas": covered_count,
                "total_areas": len(areas),
                "served_rounds": len(rounds),
                "served_units": served_units,
                "missing_capacity_units": missing_capacity,
                "minimum_coverage_met": plan.get("minimum_coverage_met", False),
                "budget_spent_won": plan.get("budget_spent_won", 0),
                "budget_gap_won": budget_gap,
                "route_cost_won": plan.get("travel_cost_won", 0),
                "replan_change_count": replan_changes.get("change_count", 0),
                "replan_service_delta": replan_changes.get("service_units_delta", 0),
                "bottleneck": bottleneck,
                "money_resolvable": money_resolvable,
                "bottleneck_explanation": bottleneck_explanation,
            }
        )
        
    return {
        "analysis_type": "PROVIDER_PARTICIPATION_SENSITIVITY",
        "budget_won": budget_won,
        "scenarios": results,
    }


def run_policy_sensitivity_analysis(
    areas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    connection: Any,
    budget_won: int,
    grid_points: list[tuple[str, int, int, int]] | None = None,
) -> dict[str, Any]:
    """Evaluate balanced policy parameter sensitivity (§16).
    
    Explores elderly, single elderly, and survey required protection weights.
    Detects high sensitivity / instability.
    """
    # Grid specifications: One-at-a-time variations from default (500, 500, 1000)
    if grid_points is None:
        grid_points = [
            # Baseline
            ("baseline_default", 500, 500, 1000),
        # Elderly priority variation
        ("elderly_zero", 0, 500, 1000),
        ("elderly_low", 250, 500, 1000),
        ("elderly_high", 1000, 500, 1000),
        # Single elderly variation
        ("single_elderly_zero", 500, 0, 1000),
        ("single_elderly_low", 500, 250, 1000),
        ("single_elderly_high", 500, 1000, 1000),
        # Survey protection variation
        ("survey_prot_zero", 500, 500, 0),
        ("survey_prot_low", 500, 500, 250),
        ("survey_prot_mid", 500, 500, 500),
        ("survey_prot_high", 500, 500, 1000),
        # Joint edge interactions
        ("all_weights_zero", 0, 0, 0),
        ("all_weights_high", 1000, 1000, 1000),
        ("elderly_focused", 1000, 1000, 0),
        ("survey_focused", 0, 0, 1000),
    ]

    runs: list[dict[str, Any]] = []
    survey_area_ids = {str(a["id"]) for a in areas if a.get("needs_survey", False)}
    
    baseline_run: dict[str, Any] = {}

    for name, e_w, se_w, s_w in grid_points:
        pol = PlanningPolicy(
            elderly_priority_weight=e_w,
            single_elderly_household_priority_weight=se_w,
            survey_required_protection_weight=s_w,
        )
        plan = scheduling.generate_provider_schedule(
            areas,
            providers,
            connection,
            budget_won,
            scenario="balanced",
            policy=pol,
            allow_route_fallback=True,
            include_timing=True,
        )
        
        rounds = plan.get("rounds", [])
        covered_ids = {r["area_id"] for r in rounds}
        
        # Survey coverage
        if survey_area_ids:
            survey_cov_pct = round(
                len(covered_ids.intersection(survey_area_ids)) / len(survey_area_ids) * 100, 2
            )
        else:
            survey_cov_pct = 100.0

        # Vulnerability-weighted coverage
        vuln_score = sum(
            float(a.get("elderly_ratio_65", 0)) * int(a.get("population_total", 0))
            for a in areas
            if str(a["id"]) in covered_ids
        )

        # Allocation concentration
        area_visit_counts = [
            sum(1 for r in rounds if r["area_id"] == str(a["id"])) for a in areas
        ]
        hhi = _hhi_concentration(area_visit_counts)

        rec = {
            "config_name": name,
            "elderly_priority_weight": e_w,
            "single_elderly_priority_weight": se_w,
            "survey_protection_weight": s_w,
            "served_rounds": len(rounds),
            "covered_areas": len(covered_ids),
            "survey_required_coverage_pct": survey_cov_pct,
            "vulnerability_weighted_coverage": round(vuln_score, 1),
            "travel_cost_won": plan.get("travel_cost_won", 0),
            "travel_duration_minutes": round(plan.get("travel_time_s", 0) / 60.0, 1),
            "allocation_concentration_hhi": hhi,
            "solver_status": plan.get("solver_status", "UNKNOWN"),
        }
        if name == "baseline_default":
            baseline_run = rec
        runs.append(rec)

    # Detect instability / sensitivity relative to baseline
    max_area_delta_pct = 0.0
    max_cost_delta_pct = 0.0
    
    base_areas = baseline_run.get("covered_areas", 1) or 1
    base_cost = baseline_run.get("travel_cost_won", 1) or 1

    for r in runs:
        area_delta = abs(r["covered_areas"] - base_areas) / base_areas * 100
        cost_delta = abs(r["travel_cost_won"] - base_cost) / base_cost * 100
        r["covered_areas_delta_pct"] = round(area_delta, 2)
        r["travel_cost_delta_pct"] = round(cost_delta, 2)
        max_area_delta_pct = max(max_area_delta_pct, area_delta)
        max_cost_delta_pct = max(max_cost_delta_pct, cost_delta)

    # Instability threshold: if a small weight shift causes >25% change
    is_high_sensitivity = (max_area_delta_pct > 25.0) or (max_cost_delta_pct > 30.0)

    return {
        "analysis_type": "POLICY_WEIGHT_SENSITIVITY",
        "baseline_config": baseline_run,
        "max_area_delta_pct": round(max_area_delta_pct, 2),
        "max_cost_delta_pct": round(max_cost_delta_pct, 2),
        "instability_flag": "HIGH_SENSITIVITY" if is_high_sensitivity else "STABLE",
        "sensitivity_level": "HIGH" if is_high_sensitivity else "MODERATE_OR_LOW",
        "user_guidance": (
            "이 정책 설정은 결과 민감도가 높습니다."
            if is_high_sensitivity
            else "정책 가중치 조정에 따른 계획 변동이 안정적입니다."
        ),
        "configurations": runs,
    }
