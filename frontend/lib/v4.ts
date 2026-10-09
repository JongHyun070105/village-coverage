import { apiBase, apiRequest } from "./api";
import type { PlanningPolicy, ScenarioKey } from "./types";

export type SourceEntry = {
  source_id: string;
  name_ko: string;
  publisher: string;
  role: string;
  reality: "REAL" | "REFERENCE" | "SIMULATED";
  reference_date: string;
  spatial_scope: string;
  update_cycle: string;
  purpose: string;
  limitations: string[];
  must_not: string[];
  license_status: string;
  reuse_allowed: boolean;
  source_url: string;
  checked_at: string;
  ingest_status: "INGEST_ALLOWED" | "INGEST_BLOCKED";
  snapshot_status?: string;
  cache_status?: string | null;
  snapshot_date?: string | null;
  last_success?: string | null;
  failure_reason?: string | null;
  snapshot_generated_at?: string | null;
  cache_note?: string | null;
  record_count?: number | null;
  table_count?: number;
};

export type ExternalPrior = {
  service_type: string | null;
  service_label: string;
  category: string;
  need_rate: number;
  usage_rate: number;
  unmet_rate: number;
  unmet_rate_program_area: number;
  unmet_rate_non_program_area: number;
  source_title: string;
  publisher: string;
  report_id: string;
  published_date: string;
  table_id: string;
  definition: string;
  population_scope: string;
  source_scope: string;
  provenance: string;
  confidence_class: string;
  display_label: string;
  interpretation_warning: string;
  definitions: Record<string, string>;
};

export type LaundryCase = {
  case_id: string;
  name: string;
  location: string;
  operation_type: string;
  operator: string;
  funding_sources: string[];
  vehicle_count: number | null;
  daily_capacity: string | null;
  eligible_population: string | null;
  general_fee: string | null;
  staffing: string | null;
  care_linkage: boolean;
  notes: string;
  usage: string;
  source_table: string;
};

export type PriorsPayload = {
  source: Record<string, string | number | boolean>;
  definitions: Record<string, string>;
  not_intended_uses: string[];
  demo_services: ExternalPrior[];
  laundry_cases: LaundryCase[];
  service_design_reference_models: Array<{ model_id: string; label: string; rationale: string; usage: string }>;
};

export type KosisTable = {
  table_id: string;
  status: string;
  cache_note: string | null;
  retrieved_at: string | null;
  data: null | {
    table_name: string;
    period: string;
    unit: string[];
    dimensions: string[];
    last_updated: string;
    definition: string | null;
    scope_note: string;
    records: Array<{ period: string; item: string; dimensions: Record<string, string>; value: number | null }>;
  };
};

export type DemandRange = {
  p10: number;
  p50: number;
  p90: number;
  local_weight: number;
  unit?: string;
  label?: string;
};

export type ServiceDemandV4 = {
  service_type: string;
  forecast_status: "FORECAST_ALLOWED" | "FORECAST_NOT_ALLOWED";
  gate_reasons: string[];
  calibration_status: string;
  monthly_count_range: DemandRange | null;
  need_propensity: (DemandRange & { external_need_rate: number; warning: string; local_respondents: number }) | null;
  external_prior: ExternalPrior | null;
  synthetic_prior_monthly: number | null;
  modifiers: Array<{ modifier: string; status: string; badge: string | null }>;
  local_evidence: {
    observation_count: number;
    unique_periods: number;
    source_types: string[];
    latest_observed_on: string | null;
    unresolved_conflicts: number;
    unresolved_duplicates: number;
  };
};

export type MinimumCoverageComparison = {
  theoretical_minimum_cost: { value_won: number | null; status: string; label: string };
  schedule_feasible_minimum_cost: { value_won: number | null; status: string; label: string };
  legacy_monthly_estimate: { value_won: number | null; status: string; label: string };
  difference_won: number | null;
  additional_budget_needed_won: number | null;
  money_alone_insufficient: boolean | null;
  money_alone_message: string;
  non_monetary_scope: string;
  non_monetary_failures: Array<{ code: string; label: string; area_count: number | null }>;
};

export type AreaExplanation = {
  area_id: string;
  included: boolean;
  rounds: number;
  reasons: string[];
  reasons_ko: string[];
  suggested_action?: string;
  money_resolvable?: boolean;
};

export type Fairness = {
  coverage_gap_areas: number;
  max_min_fulfillment_gap: number | null;
  min_fulfillment_ratio: number | null;
  allocation_concentration_gini: number | null;
  waiting_time_disparity_days: number | null;
  note: string;
};

export type AuditEvent = {
  event_id: string;
  event_type: string;
  subject_type: string;
  subject_id: string;
  actor_role: string;
  occurred_at: string;
  details: Record<string, unknown>;
};

export type PolicyPreset = {
  preset_id: string;
  label: string;
  scenario: ScenarioKey;
  policy: Pick<PlanningPolicy, "minimum_services_per_area" | "elderly_priority_weight" | "single_elderly_household_priority_weight" | "survey_required_protection_weight">;
};

export const fetchEvidenceSources = () =>
  apiRequest<{ sources: SourceEntry[]; value_labels: Record<string, string>; calibration_status_labels: Record<string, string> }>("/api/evidence/sources");
export const fetchEvidencePriors = () => apiRequest<PriorsPayload>("/api/evidence/priors");
export const fetchKosis = () => apiRequest<{ tables: KosisTable[]; topics_not_found: Array<{ topic: string; status: string; closest_table: string | null }>; scope_rule: string; generated_at: string }>("/api/evidence/kosis");
export const fetchHomeDoctor = () =>
  apiRequest<{ status: string; retrieved_at: string | null; snapshot_date: string | null; last_success: string | null; failure_reason: string | null; cache_note: string | null; live_verified: boolean; summary: Record<string, unknown> & { national_monthly?: Array<{ period: string; total: number; complex_count: number }>; official_limitation?: string; periods?: string[] } }>("/api/evidence/home-doctor");
export const fetchVillageDemandV4 = (areaId: string) =>
  apiRequest<{ area_id: string; as_of: string; services: ServiceDemandV4[]; quality_vs_demand_note: string }>(`/api/villages/${encodeURIComponent(areaId)}/demand-v4`);
export const analyzeMinimumCoverage = (regionId: string, budget: number) =>
  apiRequest<{ schedule_id: string; comparison: MinimumCoverageComparison }>("/api/minimum-coverage/analysis", {
    method: "POST",
    body: JSON.stringify({ region_id: regionId, budget_won: budget }),
  });
export const transitionPlan = (
  scheduleId: string,
  action: "submit" | "approve" | "return" | "request_changes",
  role: "PLANNER" | "REVIEWER",
  comment?: string,
  expectedPlanVersion?: number,
) =>
  apiRequest<{ approval_status: string; label: string; superseded_schedule_ids: string[] }>(`/api/schedules/${encodeURIComponent(scheduleId)}/approval`, {
    method: "POST",
    body: JSON.stringify({ action, role, comment, expected_plan_version: expectedPlanVersion }),
  });
export const fetchAuditEvents = (subjectId?: string) =>
  apiRequest<{ events: AuditEvent[] }>(`/api/audit-events${subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : ""}`);
export const fetchPolicyPresets = () =>
  apiRequest<{ presets: PolicyPreset[]; notice: string; balanced_objective_weights: Record<string, number>; weight_semantics: Record<string, string> }>("/api/policy/presets");
export const fetchPlanExplanations = (scheduleId: string) =>
  apiRequest<{ areas: AreaExplanation[]; fairness: Fairness; method: string }>(`/api/schedules/${encodeURIComponent(scheduleId)}/explanations`);
export const exportUrl = (scheduleId: string, kind: "budget.csv" | "unmet.csv" | "summary.pdf") =>
  `${apiBase()}/api/schedules/${encodeURIComponent(scheduleId)}/export/${kind}`;
export const decisionMemoUrl = (scheduleId: string, format: "pdf" | "html") =>
  `${apiBase()}/api/schedules/${encodeURIComponent(scheduleId)}/decision-memo.${format}`;

export const CALIBRATION_LABELS: Record<string, string> = {
  SYNTHETIC_ONLY: "모의 기준값만 있음",
  EXTERNAL_EMPIRICAL: "외부 조사 기준값 적용 (지역 조사 없음)",
  LOCAL_LIMITED: "지역 조사 반영 (표본 제한)",
  LOCAL_CALIBRATED: "지역 조사로 보정됨",
  LOCAL_OPERATIONAL_VALIDATED: "실제 운영기록으로 검증됨",
};

export const GATE_LABELS: Record<string, string> = {
  MIN_OBSERVATION_COUNT: "조사 건수 부족 (3건 미만)",
  MIN_UNIQUE_PERIODS: "조사 시기 다양성 부족 (2개월 미만)",
  EVIDENCE_STALE: "최근 조사 없음",
  UNRESOLVED_CONFLICT: "미해결 충돌",
  UNRESOLVED_DUPLICATE: "미해결 중복",
  SOURCE_QUALITY: "출처 품질 부족",
};

export const SERVICE_LABELS_V4: Record<string, string> = {
  laundry: "청소·세탁",
  daily_necessities: "반찬·장보기 / 생활물품",
  home_repair: "간단 집수리",
};

export type AreaV4 = {
  area_id: string;
  name: string;
  legal_code: string;
  region_id: string;
  needs_survey: boolean;
  population_total: number | null;
  population_65_plus: number | null;
  single_households_65_plus: number | null;
  facility_count: number | null;
  anchor_lat: number | null;
  anchor_lng: number | null;
  simulated_monthly_demand: number | null;
};
export const fetchAreasV4 = (regionId: string) =>
  apiRequest<{ areas: AreaV4[]; field_provenance: Record<string, string> }>(`/api/areas?region_id=${encodeURIComponent(regionId)}`);
