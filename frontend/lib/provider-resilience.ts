import { apiRequest } from "./api";
import type { ScenarioKey } from "./types";

export type FallbackCandidateResult = {
  round_count: number;
  rounds_without_fallback: number;
  fallback_coverage: number | null;
  status: "CANDIDATES_ONLY";
  notice: string;
  rounds: Array<{
    area_id: string;
    service_type: string;
    scheduled_date: string;
    primary_provider_id: string;
    fallbacks: Array<{
      provider_id: string;
      provider_name: string;
      tier: "SECONDARY" | "TERTIARY";
      estimated_total_cost_won: number;
      extra_cost_vs_primary_won: number;
      requires_provider_confirmation: true;
      auto_contract: false;
    }>;
    has_fallback: boolean;
  }>;
};

export type ReserveComparison = {
  scenario: ScenarioKey;
  budget_won: number;
  reserve_pct: number;
  reserve_chosen_by: "PLANNER";
  label: "SIMULATION";
  notice: string;
  options: Array<{
    option: "NO_RESERVE" | "BUDGET_RESERVE" | "PROVIDER_FALLBACK" | "BOTH";
    planned_budget_won: number;
    no_decline: { served_units: number; covered_areas: number; zero_service_areas: number };
    worst_zero_service_after_decline: number | null;
    worst_served_units_after_decline: number | null;
    worst_spend_after_decline_won: number;
    worst_extra_cost_vs_no_decline_won: number;
    unused_budget_at_worst_case_won: number;
    decline_cases_with_recovery: number;
    decline_case_count: number;
    replan_success_rate: number | null;
    budget_never_exceeded: boolean;
  }>;
};

export function fetchFallbackCandidates(
  regionId: string,
  budgetWon: number,
  scenario: ScenarioKey = "balanced",
) {
  return apiRequest<FallbackCandidateResult>(
    `/api/regions/${encodeURIComponent(regionId)}/fallback-candidates`,
    { method: "POST", body: JSON.stringify({ budget_won: budgetWon, scenario, depth: 2 }) },
  );
}

export function fetchReserveComparison(
  regionId: string,
  budgetWon: number,
  reservePct: number,
  scenario: ScenarioKey = "balanced",
) {
  const params = new URLSearchParams({
    budget_won: String(budgetWon),
    reserve_pct: String(reservePct),
    scenario,
  });
  return apiRequest<ReserveComparison>(
    `/api/regions/${encodeURIComponent(regionId)}/reserve-comparison?${params.toString()}`,
  );
}
