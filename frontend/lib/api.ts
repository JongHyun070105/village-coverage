import type {
  Overview,
  CSVImportBatch,
  CSVImportType,
  PlanningPolicy,
  RegionOption,
  RegionComparisonReport,
  ProviderDetail,
  ProviderDataBadges,
  ProviderDirectoryEntry,
  ProviderSourceRecord,
  ProviderDuplicateCandidate,
  ProviderServiceMappingReview,
  ProviderParticipationStatus,
  ProviderSummary,
  QualityReport,
  ScenarioKey,
  SchedulePlan,
  ScheduleHistoryEntry,
  SurveyInput,
  SurveyRecord,
  DemandAreaOption,
  DemandApproval,
  DemandApprovalResult,
  DemandDraft,
  DemandEvidenceReview,
  DemandStructureResult,
  ForecastBacktestResponse,
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
    const message = body.error?.message || (typeof body.detail === "string" ? body.detail : "") || "API 연결을 확인해 주세요.";
    throw new ApiError(message, body.error?.code || `HTTP_${response.status}`, response.status, Boolean(body.error?.retryable));
  }
  return response.json() as Promise<T>;
}

/** API failure with the backend's machine-readable code (see backend/errors.py). */
export class ApiError extends Error {
  constructor(message: string, readonly code: string, readonly status: number, readonly retryable = false) {
    super(message);
    this.name = "ApiError";
  }
}

export { request as apiRequest };

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

export function fetchForecastBacktest(regionId?: string) {
  const query = regionId ? `?region_id=${encodeURIComponent(regionId)}` : "";
  return request<ForecastBacktestResponse>(`/api/forecasts/backtest${query}`);
}

export function uploadCSVImport(importType: CSVImportType, csvContent: string | ArrayBuffer) {
  return request<CSVImportBatch>(`/api/imports/${importType}`, {
    method: "POST",
    headers: { "Content-Type": "text/csv; charset=utf-8" },
    body: csvContent,
  });
}

export function fetchImportBatches() {
  return request<{ batches: CSVImportBatch[] }>("/api/imports");
}

export function fetchImportBatch(batchId: string) {
  return request<CSVImportBatch>(`/api/imports/${encodeURIComponent(batchId)}`);
}

export function approveCSVImportRow(batchId: string, rowNumber: number, note?: string) {
  return request<CSVImportBatch>(
    `/api/imports/${encodeURIComponent(batchId)}/rows/${rowNumber}/approve`,
    { method: "POST", body: JSON.stringify({ note }) },
  );
}

export type PilotImportIssue = { code: string; severity: "ERROR" | "WARNING" | "INFO"; detail: string };
export type PilotImportRow = {
  row_number: number;
  status: "VALID" | "WARNING" | "ERROR";
  normalized_record: Record<string, string>;
  issues: PilotImportIssue[];
};
export type PilotImportBatch = {
  batch_id: string;
  file_name: string;
  template_type: string;
  status: "PREVIEWED" | "IMPORTED" | "IMPORTED_WITH_ERRORS";
  rows_total: number;
  rows_valid: number;
  rows_warning: number;
  rows_error: number;
  rows_imported: number;
  already_exists?: boolean;
  already_confirmed?: boolean;
  rows: PilotImportRow[];
};
export type PilotImportTemplates = {
  templates: Record<string, { filename: string; fields: Record<string, { type: string; required: boolean; example: string; description: string; pii_risk: string; provenance_interpretation: string }> }>;
  source_types: string[];
};

export function fetchPilotImportTemplates() {
  return request<PilotImportTemplates>("/api/pilot-imports/templates");
}

export function previewPilotImport(
  templateType: string,
  fileName: string,
  content: ArrayBuffer,
  sourceType: string,
) {
  const query = new URLSearchParams({ file_name: fileName, source_type: sourceType });
  return request<PilotImportBatch>(`/api/pilot-imports/${encodeURIComponent(templateType)}/preview?${query}`, {
    method: "POST",
    headers: { "Content-Type": "text/csv" },
    body: content,
  });
}

export function confirmPilotImport(batchId: string) {
  return request<PilotImportBatch>(`/api/pilot-imports/${encodeURIComponent(batchId)}/confirm`, {
    method: "POST",
    body: JSON.stringify({ confirm: true }),
  });
}

export async function downloadPilotImportErrors(batchId: string) {
  const response = await fetch(`${API_BASE}/api/pilot-imports/${encodeURIComponent(batchId)}/failed.csv`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error("실패 행 파일을 내려받지 못했습니다.");
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `pilot-import-${batchId}-failed.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export type PilotSetupReadiness = {
  workspace_label: string;
  planning_gate: string;
  dimensions: { id: string; label: string; status: string; records: number; detail?: string }[];
  calibration: { status: string; missing_requirements: string[]; operational_missing_requirements: string[]; dimensions: Record<string, { status: string; [key: string]: unknown }> };
  steps: { step: number; label: string; status: string }[];
  note: string;
};

export function fetchPilotSetupReadiness(
  serviceType = "laundry",
  areaCode?: string,
  regionCode?: string,
) {
  const query = new URLSearchParams({ service_type: serviceType });
  if (areaCode) query.set("area_code", areaCode);
  if (regionCode) query.set("region_code", regionCode);
  return request<PilotSetupReadiness>(`/api/pilot-setup/readiness?${query}`);
}

export function fetchRegions() {
  return request<{ regions: RegionOption[]; default_region_id: string; provenance: string }>(
    "/api/regions",
  );
}

export function fetchProviderDirectoryEntries(search = "", offset = 0) {
  const query = new URLSearchParams({ limit: "50", offset: String(offset) });
  if (search) query.set("search", search);
  return request<{ entries: ProviderDirectoryEntry[]; note: string }>(`/api/provider-directory/entries?${query}`);
}

export function fetchProviderDirectorySources() {
  return request<{ sources: ProviderSourceRecord[]; note: string }>("/api/provider-directory/sources");
}

export async function fetchProviderDirectoryReviews() {
  const [duplicates, mappings] = await Promise.all([
    request<{ candidates: ProviderDuplicateCandidate[] }>("/api/provider-directory/duplicates?status=POSSIBLE_DUPLICATE"),
    request<{ mappings: ProviderServiceMappingReview[] }>("/api/provider-directory/service-mappings"),
  ]);
  return { duplicates: duplicates.candidates, mappings: mappings.mappings };
}

export function reviewProviderDuplicate(candidateId: string, status: "CONFIRMED_SAME" | "CONFIRMED_DISTINCT") {
  return request<{ candidate_id: string; status: string; automatic_merge: false }>(
    `/api/provider-directory/duplicates/${encodeURIComponent(candidateId)}/review`,
    { method: "POST", body: JSON.stringify({ status }) },
  );
}

export function reviewProviderServiceMapping(mappingId: string, status: "VERIFIED_MAPPING" | "REJECTED_MAPPING") {
  return request<{ mapping_id: string; status: string }>(
    `/api/provider-directory/service-mappings/${encodeURIComponent(mappingId)}/review`,
    { method: "POST", body: JSON.stringify({ status, review_note: "파일럿 담당자 검토" }) },
  );
}

export function fetchRegionComparison() {
  return request<RegionComparisonReport>("/api/regions/comparison");
}

export function fetchDemandAreas(regionId: string) {
  const params = new URLSearchParams({ region_id: regionId });
  return request<{ region_id: string; areas: DemandAreaOption[]; provenance: string }>(
    `/api/areas?${params.toString()}`,
  );
}

export function createDemandDraft(input: {
  area_id: string;
  survey_type: "phone" | "village_meeting" | "proxy" | "field";
  survey_date: string;
  text: string;
}) {
  return request<DemandDraft>("/api/demand/drafts", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchDemandDrafts(areaId: string) {
  const params = new URLSearchParams({ area_id: areaId });
  return request<{ drafts: DemandDraft[] }>(`/api/demand/drafts?${params.toString()}`);
}

export function approveDemandDraft(draftId: string, input: DemandApproval) {
  return request<DemandApprovalResult>(
    `/api/demand/drafts/${encodeURIComponent(draftId)}/approve`,
    { method: "POST", body: JSON.stringify(input) },
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
    evidence_review: DemandEvidenceReview;
    facilities: {
      facility_id: string;
      area_id: string;
      facility_type: string;
      operating_status: string | null;
      latitude: number;
      longitude: number;
      built_date: string | null;
      floor_area_sqm: number | null;
      source_reference_date: string;
      source_dataset_id: string;
      provenance: string;
    }[];
    facility_detail_status: "DETAILS_AVAILABLE" | "AGGREGATE_ONLY";
    survey_recommendation: string;
  }>(`/api/villages/${encodeURIComponent(id)}?budget=${budget}`);
}

export function fetchDemandEvidenceReview(areaId: string) {
  return request<DemandEvidenceReview>(
    `/api/villages/${encodeURIComponent(areaId)}/evidence-review`,
  );
}

export function resolveDuplicateEvidence(
  areaId: string,
  input: {
    first_survey_id: string;
    second_survey_id: string;
    decision: "LINKED_DUPLICATE" | "CONFIRMED_DISTINCT";
    reason: string;
  },
) {
  return request<{ decision: Record<string, unknown>; review: DemandEvidenceReview }>(
    `/api/villages/${encodeURIComponent(areaId)}/evidence-review/duplicates`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function resolveEvidenceConflict(
  areaId: string,
  conflictId: string,
  input: {
    method: "SELECT_EVIDENCE" | "ACCEPTED_AS_RANGE" | "LATEST_EVIDENCE" | "FURTHER_SURVEY";
    selected_survey_id?: string;
    reason: string;
  },
) {
  return request<{ conflict: Record<string, unknown>; review: DemandEvidenceReview }>(
    `/api/villages/${encodeURIComponent(areaId)}/evidence-review/conflicts/${encodeURIComponent(conflictId)}/resolve`,
    { method: "POST", body: JSON.stringify(input) },
  );
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

export function fetchProviderBadges(id: string) {
  return request<{
    provider_id: string;
    badges: ProviderDataBadges;
    directory_entry: ProviderDirectoryEntry | null;
    note: string;
  }>(
    `/api/providers/${encodeURIComponent(id)}/badges`,
  );
}

export function updateProviderParticipation(
  providerId: string,
  roundId: string,
  status: Extract<ProviderParticipationStatus, "OPTED_IN" | "DECLINED" | "UNAVAILABLE" | "AVAILABLE" | "CANCELLED">,
) {
  return request<{ provider: ProviderDetail; message: string; provenance: string }>(
    `/api/providers/${encodeURIComponent(providerId)}/rounds/${encodeURIComponent(roundId)}/participation`,
    { method: "POST", body: JSON.stringify({ status }) },
  );
}

export function updateProviderParticipationPreference(
  providerId: string,
  scope: "MONTH" | "WEEK",
  period: string,
  status: Extract<ProviderParticipationStatus, "OPTED_IN" | "DECLINED" | "AVAILABLE">,
) {
  return request<{
    provider: ProviderDetail;
    preference: { scope: "MONTH" | "WEEK"; period_start: string; status: string; provenance: string };
    affected_round_count: number;
    message: string;
    provenance: string;
  }>(`/api/providers/${encodeURIComponent(providerId)}/participation-preferences`, {
    method: "POST",
    body: JSON.stringify({ scope, period, status }),
  });
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

export function replanSchedule(id: string) {
  return request<SchedulePlan>(`/api/schedules/${encodeURIComponent(id)}/replan`, {
    method: "POST",
  });
}

export function reviseSchedule(
  id: string,
  plan: Pick<SchedulePlan, "scenario_key" | "budget_won" | "planning_policy" | "region_id">,
) {
  return request<SchedulePlan>(`/api/schedules/${encodeURIComponent(id)}/revision`, {
    method: "POST",
    body: JSON.stringify({
      scenario: plan.scenario_key,
      budget_won: plan.budget_won,
      planning_policy: plan.planning_policy,
      region_id: plan.region_id,
    }),
  });
}

export function fetchScheduleHistory(regionId: string = DEFAULT_REGION_ID) {
  const params = new URLSearchParams({ region_id: regionId, limit: "30" });
  return request<{ plans: ScheduleHistoryEntry[]; provenance: string }>(
    `/api/schedules?${params.toString()}`,
  );
}

export function scheduleExportUrl(id: string) {
  return `${API_BASE}/api/schedules/${encodeURIComponent(id)}/export.csv`;
}

export function structureDemand(text: string) {
  return request<DemandStructureResult>("/api/demand/structure", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function apiBase() {
  return API_BASE;
}
