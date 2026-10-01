export type ScenarioKey = "efficiency" | "balanced" | "minimum_coverage";
export type SurveyType = "phone" | "village_meeting" | "proxy" | "field";
export type SurveyServiceType = "laundry" | "daily_necessities" | "home_repair";
export type PlanningPolicy = {
  minimum_services_per_area: number;
  elderly_priority_weight: number;
  single_elderly_household_priority_weight: number;
  survey_required_protection_weight: number;
  maximum_round_trip_travel_minutes: number | null;
  allowed_services: SurveyServiceType[];
  minimum_provider_compensation_won: number;
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

export type SchedulePlan = {
  schedule_id: string;
  scenario_key: ScenarioKey;
  budget_won: number;
  provenance: string;
  created_at: string;
  summary: {
    scenario: ScenarioKey;
    budget_won: number;
    budget_spent_won: number;
    budget_remaining_won: number;
    budget_gap_won: number | null;
    required_budget_won: number | null;
    service_cost_won: number;
    travel_cost_won: number;
    minimum_compensation_topup_won: number;
    total_cost_won: number;
    travel_distance_m: number;
    travel_time_s: number;
    total_demand_units: number;
    served_units: number;
    covered_areas: number;
    uncovered_areas: number;
    minimum_coverage_met: boolean;
    unmet_criteria: Array<{ area_id: string; area_name: string; units: number; reason: string }>;
    travel_source: string;
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
  status: "충족" | "부분충족" | "미충족";
  needs_survey: boolean;
  constraint_reason?: string | null;
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
  service_cost_won: number;
  provider_minimum_compensation_won: number;
  minimum_compensation_topup_won: number;
  additional_public_subsidy_won: number | null;
  required_capacity: number | null;
  available_capacity: number | null;
  missing_capacity: number | null;
  travel_time_s: number;
  travel_time_added_vs_efficiency_s?: number;
  travel_cost_won: number;
  service_gap: number | null;
  assignments: Assignment[];
  solver_status: string;
};

export type Overview = {
  region: string;
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
  sources: Record<string, string | number | null>;
  metrics: Record<string, number | boolean | string | string[]>;
  interpretation: string[];
};
