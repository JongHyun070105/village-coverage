import type {
  Overview,
  PlanningPolicy,
  RegionOption,
  ProviderDetail,
  ProviderParticipationStatus,
  ProviderSummary,
  QualityReport,
  ScenarioKey,
  SchedulePlan,
  SurveyInput,
  SurveyRecord,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
export const DEFAULT_REGION_ID = "pilot:홍성군 장곡면";
const REGION_STORAGE_KEY = "villagecoverage.selectedRegionId";

export function readSelectedRegionId() {
  if (typeof window === "undefined") return DEFAULT_REGION_ID;
  try {
    return window.localStorage.getItem(REGION_STORAGE_KEY) || DEFAULT_REGION_ID;
  } catch {
    return DEFAULT_REGION_ID;
  }
}

export function saveSelectedRegionId(regionId: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(REGION_STORAGE_KEY, regionId);
  } catch {
    // Keep the region selection for this page even when browser storage is unavailable.
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "API 연결을 확인해 주세요.");
  }
  return response.json() as Promise<T>;
}

export function fetchOverview(
  budget: number,
  policy: PlanningPolicy,
  regionId: string = DEFAULT_REGION_ID,
) {
  const params = new URLSearchParams({
    budget: String(budget),
    region_id: regionId,
    minimum_services_per_area: String(policy.minimum_services_per_area),
    elderly_priority_weight: String(policy.elderly_priority_weight),
    single_elderly_household_priority_weight: String(policy.single_elderly_household_priority_weight),
    survey_required_protection_weight: String(policy.survey_required_protection_weight),
    minimum_provider_compensation_won: String(policy.minimum_provider_compensation_won),
  });
  if (policy.maximum_round_trip_travel_minutes !== null) {
    params.set("maximum_round_trip_travel_minutes", String(policy.maximum_round_trip_travel_minutes));
  }
  policy.allowed_services.forEach((service) => params.append("allowed_services", service));
  return request<Overview>(`/api/overview?${params.toString()}`);
}

export function fetchQuality() {
  return request<QualityReport>("/api/data-quality");
}

export function fetchRegions() {
  return request<{ regions: RegionOption[]; default_region_id: string; provenance: string }>(
    "/api/regions",
  );
}

export function fetchVillage(id: string, budget: number) {
  return request<{
    area: Overview["areas"][number];
    scenario_assessments: Record<ScenarioKey, Overview["scenario_results"][ScenarioKey]["assignments"][number]>;
    evidence: {
      observation_count: number;
      survey_count: number;
      source_diversity: number;
      missingness: number;
      deterministic_confidence: number;
      combined_confidence: number;
      status: string;
      needs_survey: boolean;
      limited_planning_allowed: boolean;
      evidence_reasons: string[];
    };
    surveys: SurveyRecord[];
    survey_recommendation: string;
  }>(`/api/villages/${encodeURIComponent(id)}?budget=${budget}`);
}

export function createSurvey(id: string, payload: SurveyInput) {
  return request<{ survey: SurveyRecord; evidence: Awaited<ReturnType<typeof fetchVillage>>["evidence"]; message: string }>(
    `/api/villages/${encodeURIComponent(id)}/surveys`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function fetchProviders(regionId: string = DEFAULT_REGION_ID) {
  const params = new URLSearchParams({ region_id: regionId });
  return request<{
    region_id: string;
    region: string;
    providers: ProviderSummary[];
    provenance: string;
  }>(`/api/providers?${params.toString()}`);
}

export function fetchProvider(id: string) {
  return request<ProviderDetail>(`/api/providers/${encodeURIComponent(id)}`);
}

export function updateProviderParticipation(
  providerId: string,
  roundId: string,
  status: Extract<ProviderParticipationStatus, "OPTED_IN" | "DECLINED" | "UNAVAILABLE" | "AVAILABLE">,
) {
  return request<{ provider: ProviderDetail; message: string; provenance: string }>(
    `/api/providers/${encodeURIComponent(providerId)}/rounds/${encodeURIComponent(roundId)}/participation`,
    { method: "POST", body: JSON.stringify({ status }) },
  );
}

export function createSchedulePlan(
  scenario: ScenarioKey,
  budgetWon: number,
  planningPolicy: PlanningPolicy,
  regionId: string = DEFAULT_REGION_ID,
) {
  return request<SchedulePlan>("/api/schedules", {
    method: "POST",
    body: JSON.stringify({
      scenario,
      budget_won: budgetWon,
      planning_policy: planningPolicy,
      region_id: regionId,
    }),
  });
}

export function fetchSchedulePlan(id: string) {
  return request<SchedulePlan>(`/api/schedules/${encodeURIComponent(id)}`);
}

export function structureDemand(text: string) {
  return request<{
    requests: Array<{
      service_type: string;
      requested_period: string | null;
      frequency_per_month: number | null;
      preferred_days: string[];
      excluded_days: string[];
      constraints: string[];
    }>;
    confidence: number | null;
    needs_followup_survey: boolean;
    followup_reason: string | null;
    source_text_was_redacted: boolean;
    method: string;
    evidence_assessment: {
      observation_count: number;
      model_confidence: number | null;
      deterministic_confidence: number;
      combined_confidence: number;
      status: string;
      needs_survey: boolean;
      evidence_reasons: string[];
    };
  }>("/api/demand/structure", { method: "POST", body: JSON.stringify({ text }) });
}

export function apiBase() {
  return API_BASE;
}
