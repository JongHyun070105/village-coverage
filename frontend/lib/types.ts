export type ScenarioKey = "efficiency" | "balanced" | "minimum_coverage";
export type SurveyType = "phone" | "village_meeting" | "proxy" | "field";
export type SurveyServiceType = "laundry" | "daily_necessities" | "home_repair";
export type ServicePolicyStatus = "ALLOWED" | "REGULATED" | "EXCLUDED" | "UNCLASSIFIED";
export type ServiceTypePolicy = {
  service_type_id: string;
  label_ko: string;
  policy_status: ServicePolicyStatus;
  policy_reason: string;
  provenance: string;
};

export type DemandAreaOption = {
  area_id: string;
  name: string;
  legal_code: string;
  region_id: string;
};

export type StructuredDemandRequest = {
  service_type: string;
  requested_period: string | null;
  frequency_per_month: number | null;
  desired_date: string | null;
  desired_time: string | null;
  recurring_pattern: "weekly" | "monthly" | "seasonal" | "one_time" | null;
  urgency: "urgent" | null;
  urgency_evidence: string | null;
  preferred_days: string[];
  excluded_days: string[];
  constraints: string[];
  service_policy: ServiceTypePolicy;
};

export type DemandStructureResult = {
  requests: StructuredDemandRequest[];
  service_registry: ServiceTypePolicy[];
  requires_service_scope_review: boolean;
  confidence: number | null;
  needs_followup_survey: boolean;
  followup_reason: string | null;
  source_text_was_redacted: boolean;
  method: string;
  evidence_assessment: {
    observation_count: number;
    fresh_evidence_count: number;
    aging_evidence_count: number;
    stale_evidence_count: number;
    model_confidence: number | null;
    deterministic_confidence: number;
    combined_confidence: number;
    status: string;
    needs_survey: boolean;
    evidence_reasons: string[];
  };
};

export type DemandDraft = {
  draft_id: string;
  area_id: string;
  survey_type: SurveyType;
  survey_date: string;
  source_text_redacted: string;
  source_text_was_redacted: boolean;
  status: "DRAFT" | "APPROVED" | "REJECTED" | "APPROVING";
  provenance: string;
  structured: DemandStructureResult;
};

export type ReviewedDemandRequest = {
  service_type: SurveyServiceType;
  requested_period: string | null;
  frequency_per_month: number | null;
  desired_date: string | null;
  desired_time: string | null;
  recurring_pattern: "weekly" | "monthly" | "seasonal" | "one_time" | null;
  urgency: "urgent" | null;
  urgency_evidence: string | null;
  preferred_days: string[];
  excluded_days: string[];
  constraints: string[];
};

export type DemandApproval = {
  requests: ReviewedDemandRequest[];
  needs_followup_survey: boolean;
  followup_reason: string | null;
};

export type DemandApprovalResult = {
  draft_id: string;
  status: "APPROVED";
  approved_requests: ReviewedDemandRequest[];
  survey_ids: string[];
  evidence_assessments: Record<string, { observation_count: number; status: string }>;
  provenance: string;
};
export type PlanningPolicy = {
  minimum_services_per_area: number;
  elderly_priority_weight: number;
  single_elderly_household_priority_weight: number;
  survey_required_protection_weight: number;
  maximum_round_trip_travel_minutes: number | null;
  allowed_services: SurveyServiceType[];
  minimum_provider_compensation_won: number;
};

export type RegionOption = {
  region_id: string;
  province: string;
  county: string;
  town: string;
  name: string;
  area_count: number;
  household_join_rate?: number | null;
  facility_area_count?: number;
  coordinate_anchor_count?: number;
  facility_area_coverage?: number;
  full_source_join_rate: number | null;
  provenance?: string;
};

export type SurveyInput = {
  survey_type: SurveyType;
  survey_date: string;
  service_type: SurveyServiceType;
  frequency_per_month: number | null;
  preferred_period: string | null;
  preferred_days: string[];
  constraints: string[];
  free_text_note: string;
};

export type SurveyRecord = SurveyInput & {
  survey_id: string;
  source_text_was_redacted: boolean;
  provenance: string;
  canonical_survey_id?: string;
  duplicate_group_id?: string | null;
  duplicate_status?: "UNREVIEWED" | "LINKED_DUPLICATE";
  observation_id?: string | null;
  occurred_on?: string | null;
  observation_source_type?: SurveyType | null;
  evidence_id?: string | null;
  evidence_type?: string | null;
  evidence_payload?: Record<string, unknown>;
  approved_draft_id?: string | null;
  source_text_redacted?: string | null;
  structured_data?: Record<string, unknown>;
};

export type EvidenceReviewRecord = SurveyRecord & {
  legal_code: string;
  note_fingerprint: string | null;
  evidence_age_days: number;
  freshness_status: "FRESH" | "AGING" | "STALE";
  evidence_status: "UNREVIEWED" | "POSSIBLE_DUPLICATE" | "LINKED_DUPLICATE" | "CONFIRMED_DISTINCT";
};

export type DuplicateEvidenceCandidate = {
  survey_id_a: string;
  survey_id_b: string;
  date_gap_days: number;
  match_reasons: string[];
  status: "POSSIBLE_DUPLICATE" | "LINKED_DUPLICATE" | "CONFIRMED_DISTINCT";
};

export type EvidenceConflict = {
  conflict_id: string;
  area_id: string;
  service_type: string | null;
  conflict_type:
    | "FREQUENCY_CONFLICT"
    | "DATE_CONFLICT"
    | "TIME_CONFLICT"
    | "PREFERRED_DAY_CONFLICT"
    | "EXCLUDED_DAY_CONFLICT"
    | "SERVICE_TYPE_CONFLICT"
    | "CONSTRAINT_CONFLICT";
  evidence_survey_ids: string[];
  values: Record<string, unknown>;
  status: "NO_CONFLICT" | "REVIEW_REQUIRED" | "RESOLVED" | "ACCEPTED_AS_RANGE";
  resolution_method: "SELECT_EVIDENCE" | "ACCEPTED_AS_RANGE" | "LATEST_EVIDENCE" | "FURTHER_SURVEY" | null;
  selected_survey_id: string | null;
  frequency_min: number | null;
  frequency_max: number | null;
  actor_type: "SYSTEM" | "DEMO_PLANNER" | null;
  reason: string | null;
  provenance: string;
  evidence: EvidenceReviewRecord[];
};

export type EvidenceReviewAudit = {
  audit_id: string;
  area_id: string;
  subject_type: "DUPLICATE_PAIR" | "CONFLICT";
  subject_id: string;
  action: "LINK_DUPLICATE" | "CONFIRM_DISTINCT" | "RESOLVE_CONFLICT";
  actor_type: "SYSTEM" | "DEMO_PLANNER";
  action_at: string;
  previous_state: string;
  new_state: string;
  selected_survey_id: string | null;
  reason: string;
  provenance: string;
};

export type DemandEvidenceReview = {
  area_id: string;
  evidence: EvidenceReviewRecord[];
  duplicate_candidates: DuplicateEvidenceCandidate[];
  conflicts: EvidenceConflict[];
  conflict_state: "NO_CONFLICT" | "REVIEW_REQUIRED";
  frequency_planning_policy: "CONSERVATIVE_LOW";
  freshness_policy: {
    fresh_max_age_days: number;
    aging_max_age_days: number;
    stale_after_days: number;
    forecast_max_evidence_age_days: number;
    planning_eligible_through_days: number;
  };
  freshness_summary: { FRESH: number; AGING: number; STALE: number };
  resurvey_recommended: boolean;
  audit: EvidenceReviewAudit[];
};

export type ForecastBacktestMetrics = {
  evaluation_case_count: number;
  accuracy_scored_count: number;
  forecast_unavailable_count: number;
  actual_unavailable_count: number;
  forecast_availability_rate: number | null;
  insufficient_data_rate: number | null;
  mae: number | null;
  wape: number | null;
  wape_status: "DEFINED" | "UNDEFINED_ZERO_ACTUAL_TOTAL" | "NO_AVAILABLE_FORECASTS";
  bias: number | null;
  interval_coverage: number | null;
  interval_scored_count: number;
  accuracy_scope: string;
};

export type ForecastBacktestReport = {
  region_id: string;
  region_name: string;
  service_type: string;
  backtest_type: string;
  same_cutoff_and_evidence_gate: boolean;
  comparison_policy: string;
  model_results: {
    model: string;
    model_parameters: Record<string, unknown>;
    origin_count: number;
    holdout_case_count: number;
    observed_holdout_case_count: number;
    metrics: ForecastBacktestMetrics;
    metrics_by_horizon: Record<string, ForecastBacktestMetrics>;
  }[];
};

export type ForecastBacktestResponse = {
  status: "AVAILABLE" | "DATA_INSUFFICIENT";
  method: string;
  provenance: string;
  models: string[];
  comparison_policy: string;
  reports: ForecastBacktestReport[];
};

export type ProviderParticipationStatus =
  | "AVAILABLE"
  | "OPTED_IN"
  | "DECLINED"
  | "UNAVAILABLE"
  | "COMPLETED"
  | "CANCELLED";

export type ProviderSummary = {
  provider_id: string;
  name: string;
  region_id: string;
  region_name: string;
  base_location: string;
  max_monthly_rounds: number;
  service_capacity: number;
  max_travel_time_minutes: number;
  minimum_compensation_won: number;
  service_count: number;
  provenance: string;
};

export type ProviderRound = {
  round_id: string;
  round_date: string;
  start_time?: string;
  area_id: string;
  area_name: string;
  service_type: string;
  duration_minutes: number;
  estimated_compensation_won: number;
  travel_time_minutes: number | null;
  travel_distance_km: number | null;
  status: ProviderParticipationStatus;
  participation_source?: "ROUND" | "WEEK" | "MONTH" | null;
  provenance: string;
};

export type ProviderParticipationPreference = {
  scope: "MONTH" | "WEEK";
  period_start: string;
  status: Extract<ProviderParticipationStatus, "OPTED_IN" | "DECLINED" | "AVAILABLE">;
  updated_at: string;
  provenance: string;
};

export type ProviderForecastMonth = {
  region_id: string;
  region_name: string;
  service_type: string;
  month: string;
  expected_rounds_low: number | null;
  expected_rounds_mid: number | null;
  expected_rounds_high: number | null;
  confidence: "LOW" | "MEDIUM" | "HIGH" | null;
  evidence_status: "SUFFICIENT_OBSERVED" | "DATA_INSUFFICIENT";
  survey_required: boolean;
  observation_count: number;
  history_month_count: number;
  observed_area_count: number;
  region_area_count: number;
  source_diversity: number;
  model_basis: string | null;
  model_version: string;
  input_fingerprint: string;
  insufficiency_reasons: string[];
  provenance: string;
};

export type ProviderDetail = ProviderSummary & {
  base_lat: number;
  base_lng: number;
  max_daily_hours: number;
  minimum_compensation_won: number;
  supported_services: string[];
  availability: Array<{ weekday: string; start_time: string; end_time: string }>;
  date_availability: Array<{
    available_date: string;
    service_type: string;
    start_time: string;
    end_time: string;
    provenance: string;
  }>;
  history: ProviderRound[];
  participation: {
    opportunities: number;
    accepted: number;
    completed: number;
    declined: number;
    cancelled: number;
    completion_rate: number | null;
    reliability_label: string;
    long_term_agreement_candidate: boolean;
  };
  upcoming_rounds: ProviderRound[];
  participation_preferences: ProviderParticipationPreference[];
  forecast: {
    status: "DATA_INSUFFICIENT" | "AVAILABLE";
    survey_required: boolean;
    months: ProviderForecastMonth[];
    message: string;
    provenance: string;
    model_version: string;
  };
};

export type ScheduleRound = {
  scheduled_round_id: string;
  schedule_id: string;
  service_round_id: string;
  route_id: string | null;
  route_sequence: number;
  route_type: "HUB_ROUND_TRIP" | "MULTI_STOP";
  provider_id: string;
  provider_name: string;
  area_id: string;
  area_name: string;
  service_type: string;
  scheduled_date: string;
  departure_time: string;
  service_start_time: string;
  service_end_time: string;
  duration_minutes: number;
  service_units: number;
  travel_before_s: number;
  travel_after_s: number;
  travel_distance_m: number;
  service_cost_won: number;
  travel_cost_won: number;
  minimum_compensation_topup_won: number;
  total_cost_won: number;
  participation_status: ProviderParticipationStatus;
  participation_source: "ROUND" | "WEEK" | "MONTH" | null;
  provenance: string;
};

export type ScheduleRouteStop = {
  route_stop_id: string;
  route_id: string;
  service_round_id: string;
  incoming_from_area_id: string;
  incoming_from_area_name: string;
  area_id: string;
  area_name: string;
  outgoing_to_area_id: string;
  outgoing_to_area_name: string;
  sequence: number;
  service_start_time: string;
  service_end_time: string;
  incoming_time_s: number;
  outgoing_time_s: number;
  incoming_distance_m: number;
  outgoing_distance_m: number;
};

export type ScheduleRoute = {
  route_id: string;
  schedule_id: string;
  provider_id: string;
  provider_name: string;
  scheduled_date: string;
  route_type: "HUB_ROUND_TRIP" | "MULTI_STOP";
  base_area_id: string;
  distance_m: number;
  duration_s: number;
  cost_won: number;
  old_distance_m: number;
  old_duration_s: number;
  old_cost_won: number;
  distance_savings_m: number;
  duration_savings_s: number;
  cost_savings_won: number;
  provenance: string;
  stops: ScheduleRouteStop[];
};

export type PlanningDemandInput = {
  area_id: string;
  area_name: string;
  service_type: string;
  source_baseline_units: number;
  population_total: number | null;
  population_reference_date: string | null;
  population_prior_floor_units: number | null;
  population_adjusted_baseline_units: number;
  population_rate_per_1000_simulated_rounds: number | null;
  population_prior_status: string;
  population_prior_model: string;
  population_prior_provenance: string;
  survey_frequency_floor_monthly: number | null;
  survey_frequency_observation_count: number;
  gross_planning_demand_units: number;
  existing_service_rounds_deducted: number;
  existing_service_status: "CURRENT_REPORTED_SNAPSHOT" | "STALE" | "UNKNOWN";
  planning_demand_units: number;
  policy: string;
  provenance: string;
};

export type SchedulePlan = {
  schedule_id: string;
  scenario_key: ScenarioKey;
  budget_won: number;
  region_id: string;
  region_name: string;
  planning_policy: PlanningPolicy;
  provenance: string;
  created_at: string;
  summary: {
    scenario: ScenarioKey;
    balanced_objective_weights?: Record<string, number> | null;
    balanced_objective_policy_weights?: {
      elderly_priority_weight: number;
      single_elderly_household_priority_weight: number;
      survey_required_protection_weight: number;
    } | null;
    budget_won: number;
    budget_spent_won: number;
    budget_remaining_won: number;
    budget_gap_won: number | null;
    required_budget_won: number | null;
    required_budget_status: "CALCULATED" | "INFEASIBLE" | "NOT_PROVEN";
    required_budget_reason: string | null;
    required_budget_model:
      | "PROVIDER_CP_SAT_INTEGRATED_KAKAO_VRPTW"
      | "PROVIDER_CP_SAT_KAKAO_VRPTW_WITH_HUB_FALLBACK"
      | "PROVIDER_CP_SAT_HUB_ROUND_TRIP";
    service_cost_won: number;
    travel_cost_won: number;
    minimum_compensation_topup_won: number;
    minimum_services_per_area: number;
    total_cost_won: number;
    travel_distance_m: number;
    travel_time_s: number;
    total_demand_units: number;
    planning_demand_inputs?: PlanningDemandInput[];
    served_units: number;
    covered_areas: number;
    uncovered_areas: number;
    minimum_coverage_met: boolean;
    minimum_frequency_met_areas: number;
    unmet_minimum_frequency_areas: number;
    minimum_frequency_gaps: Array<{
      area_id: string;
      area_name: string;
      required_rounds: number;
      scheduled_rounds: number;
      missing_rounds: number;
      reason: string;
      reasons?: string[];
    }>;
    required_capacity: number;
    available_capacity: number;
    capacity_basis: "ELIGIBLE_PROVIDER_MONTH_LIMIT_UPPER_BOUND";
    missing_capacity: number;
    minimum_capacity_diagnostic: {
      status:
        | "CAPACITY_FEASIBLE"
        | "PROVEN_CAPACITY_GAP"
        | "CAPACITY_GAP_BOUNDED"
        | "NOT_PROVEN"
        | "DEMAND_BELOW_MINIMUM";
      required_areas: number;
      maximum_feasible_areas: number | null;
      maximum_feasible_areas_upper_bound: number | null;
      minimum_rounds_supplied: number | null;
      minimum_rounds_supplied_upper_bound: number | null;
      missing_rounds_lower_bound: number | null;
      missing_rounds_upper_bound: number | null;
      minimum_services_per_area: number;
      solver_status: string;
      budget_constraint_included: false;
      scope: "FOUR_WEEK_PROVIDER_DATE_ROUTE_MODEL";
    } | null;
    unmet_criteria: Array<{
      area_id: string;
      area_name: string;
      units: number;
      reason: string;
      reasons?: string[];
    }>;
    travel_source: string;
    solver_objective_model?: string;
    route_assignment_model?: string;
    route_matrix_complete?: boolean;
    exact_route_group_count?: number;
    hub_fallback_group_count?: number;
    route_savings_proxy_pair_count?: number;
    route_savings_proxy?: string;
    global_route_optimality_proven?: boolean;
    solver_status: string;
    optimality_proven: boolean;
    routing_comparison: {
      baseline_name: string;
      actual_name: string;
      old_distance_m: number;
      actual_distance_m: number;
      distance_savings_m: number;
      old_duration_s: number;
      actual_duration_s: number;
      duration_savings_s: number;
      old_cost_won: number;
      actual_cost_won: number;
      cost_savings_won: number;
      multi_stop_route_count: number;
    };
  };
  rounds: ScheduleRound[];
  routes: ScheduleRoute[];
};

export type ScheduleHistoryEntry = Omit<SchedulePlan, "rounds" | "routes"> & {
  round_count: number;
};

export type Area = {
  id: string;
  legal_code: string;
  name: string;
  province: string;
  county: string;
  town: string;
  village_name: string;
  population_total: number;
  population_65_plus: number;
  population_75_plus: number;
  population_80_plus: number;
  elderly_ratio_65: number | null;
  elderly_ratio_75: number | null;
  elderly_ratio_80: number | null;
  single_households_total: number;
  single_households_65_plus: number;
  single_households_75_plus: number;
  single_households_80_plus: number;
  facility_count: number;
  anchor_lat: number;
  anchor_lng: number;
  public_data_reference_date: string;
  household_data_reference_date: string;
  demand_observation_count: number;
  demand_data_count: number;
  demand_confidence: string;
  needs_survey: boolean;
  simulated_monthly_demand: number;
  baseline_monthly_demand?: number;
  survey_frequency_floor_monthly?: number | null;
  survey_frequency_observation_count?: number;
  existing_service_monthly_rounds?: number | null;
  existing_service_status?: "CURRENT_REPORTED_SNAPSHOT" | "STALE" | "UNKNOWN";
  existing_service_as_of_date?: string | null;
  existing_service_program_count?: number;
  planning_demand_provenance?: string;
  service_type: string;
  data_provenance: string;
};

export type Assignment = {
  area_id: string;
  served_units: number;
  demand_units: number;
  covered: boolean;
  visits: number;
  provider_assignments: Record<string, number>;
  cost_won: number;
  travel_time_s: number;
  travel_distance_m: number;
  status: "충족" | "부분충족" | "미충족";
  needs_survey: boolean;
  constraint_reason?: string | null;
};

export type ProviderScenarioCost = {
  provider_id: string;
  provider_name: string;
  service_rounds: number;
  service_cost_won: number;
  travel_distance_m: number;
  travel_time_s: number;
  travel_cost_won: number;
  minimum_compensation_floor_won: number;
  compensation_paid_won: number;
  compensation_topup_won: number;
  total_cost_won: number;
};

export type ScenarioResult = {
  scenario: ScenarioKey;
  budget_won: number;
  required_budget_won: number | null;
  additional_budget_won: number | null;
  budget_gap_won?: number;
  budget_spent_won: number;
  budget_remaining_won: number;
  total_demand_units: number;
  served_units: number;
  service_fulfillment_rate: number;
  covered_villages: number;
  uncovered_villages: number;
  minimum_services_per_area: number | null;
  minimum_coverage_met: boolean;
  minimum_frequency_met_areas: number;
  unmet_minimum_frequency_areas: number;
  guarantee_capacity_feasible: boolean | null;
  guarantee_feasible?: boolean;
  guarantee_failure_reason?: string | null;
  guarantee_scope?: "MONTHLY_AGGREGATE_CAPACITY_ESTIMATE";
  guarantee_travel_model?: "CENTRAL_HUB_ROUND_TRIP_ESTIMATE";
  service_cost_won: number;
  provider_minimum_compensation_won: number;
  minimum_compensation_topup_won: number;
  provider_cost_breakdown: ProviderScenarioCost[];
  provider_travel_model: "CENTRAL_HUB_ROUND_TRIP_ESTIMATE";
  additional_public_subsidy_won: number | null;
  full_demand_required_budget_won: number | null;
  full_demand_budget_gap_won: number | null;
  full_demand_budget_status: "CALCULATED" | "INFEASIBLE" | "NOT_PROVEN";
  full_demand_failure_reason: string | null;
  full_demand_budget_model: "CENTRAL_HUB_ROUND_TRIP_ESTIMATE";
  required_capacity: number | null;
  available_capacity: number | null;
  minimum_compatible_capacity?: number | null;
  capacity_basis?: "MONTHLY_SERVICE_COMPATIBLE_CAPACITY_UPPER_BOUND";
  missing_capacity: number | null;
  travel_time_s: number;
  travel_distance_m: number;
  max_area_demand_saturation_basis_points: number;
  travel_time_added_vs_efficiency_s?: number;
  travel_cost_won: number;
  service_gap: number | null;
  assignments: Assignment[];
  solver_status: string;
  optimality_proven: boolean;
};

export type Overview = {
  region: string;
  region_id: string;
  regions: RegionOption[];
  budget_won: number;
  planning_defaults: {
    seed: number;
    monthly_budget: number;
    minimum_services_per_area: number;
    simulation_notice: string;
  };
  planning_policy: PlanningPolicy;
  areas: Area[];
  scenario_results: Record<ScenarioKey, ScenarioResult>;
  request_count_baseline: {
    served_units: number;
    covered_villages: number;
    uncovered_villages: number;
    survey_required_areas: number;
    survey_required_covered: number;
    budget_spent_won: number;
    travel_cost_won: number;
    travel_time_s: number;
  };
  hub_area_id: string;
  travel_source: string;
  scenario_labels: Record<ScenarioKey, string>;
};

export type QualityReport = {
  region: string;
  regions: Array<{
    region_id: string;
    province: string;
    county: string;
    town: string;
    name: string;
    area_count: number;
    household_join_rate: number;
    facility_area_count: number;
    coordinate_anchor_count: number;
    facility_area_coverage: number;
    full_source_join_rate: number;
    population_reference_date: string;
    household_reference_date: string;
    facility_latest_update_date: string;
    facility_detail_row_count: number;
    facility_detail_area_count: number;
    provenance: string;
  }>;
  sources: Record<string, string | number | null>;
  metrics: Record<string, number | boolean | string | string[]>;
  interpretation: string[];
};

export type CSVImportType =
  | "demand_observations"
  | "provider_availability"
  | "existing_service_history";
export type CSVImportRow = {
  row_id: string;
  batch_id: string;
  row_number: number;
  status: "IMPORTED" | "NEEDS_REVIEW" | "FAILED";
  record: Record<string, string>;
  issues: string[];
  redacted: boolean;
  imported_record_id: string | null;
  reviewed_at: string | null;
};
export type CSVImportBatch = {
  batch_id: string;
  import_type: CSVImportType;
  total_rows: number;
  valid_rows: number;
  needs_review_rows: number;
  failed_rows: number;
  provenance: string;
  created_at: string;
  already_imported?: boolean;
  rows?: CSVImportRow[];
};
