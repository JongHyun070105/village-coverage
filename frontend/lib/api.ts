import type { Overview, QualityReport, ScenarioKey } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

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

export function fetchOverview(budget: number) {
  return request<Overview>(`/api/overview?budget=${budget}`);
}

export function fetchQuality() {
  return request<QualityReport>("/api/data-quality");
}

export function fetchVillage(id: string, budget: number) {
  return request<{
    area: Overview["areas"][number];
    scenario_assessments: Record<ScenarioKey, Overview["scenario_results"][ScenarioKey]["assignments"][number]>;
    evidence: {
      observation_count: number;
      source_diversity: number;
      missingness: number;
      deterministic_confidence: number;
      combined_confidence: number;
      status: string;
      needs_survey: boolean;
      evidence_reasons: string[];
    };
    survey_recommendation: string;
  }>(`/api/villages/${encodeURIComponent(id)}?budget=${budget}`);
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
