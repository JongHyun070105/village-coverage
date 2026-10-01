export type ScenarioKey = "efficiency" | "balanced" | "minimum_coverage";
export type SurveyType = "phone" | "village_meeting" | "proxy" | "field";
export type SurveyServiceType = "laundry" | "daily_necessities" | "home_repair";

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
  guarantee_capacity_feasible: boolean | null;
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
