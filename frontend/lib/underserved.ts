import { apiRequest } from "./api";

export type UnderservedStatus = "RECENTLY_SERVED" | "WAITING" | "LONG_UNSERVED" | "CHRONICALLY_UNSERVED" | "UNKNOWN";

export const UNDERSERVED_STATUS_LABEL: Record<UnderservedStatus, string> = {
  RECENTLY_SERVED: "최근 서비스",
  WAITING: "대기 중",
  LONG_UNSERVED: "장기 미서비스",
  CHRONICALLY_UNSERVED: "만성 미서비스",
  UNKNOWN: "이력 없음(미확인)",
};

export type UnderservedComparisonRow = {
  policy: string;
  label_ko: string;
  served_units: number | null;
  ZERO_SERVICE_AREA_COUNT: number;
  REDUCED_EXCLUSION_COUNT: number;
  underserved_points_covered: number;
  underserved_points_total: number;
  excluded_areas_served_count: number;
  excluded_area_count: number;
};

export type UnderservedComparison = {
  region_id: string;
  budget_won: number;
  label: "SIMULATION";
  notice: string;
  kpi_definitions: Record<string, string>;
  status_counts: Record<UnderservedStatus, number>;
  rows: UnderservedComparisonRow[];
};

export function fetchUnderservedComparison(regionId: string, budgetWon: number): Promise<UnderservedComparison> {
  return apiRequest<UnderservedComparison>(
    `/api/regions/${encodeURIComponent(regionId)}/underserved/comparison?budget=${budgetWon}`,
  );
}

export function seedUnderservedDemo(regionId: string): Promise<{ rows_written: number; notice: string }> {
  return apiRequest(`/api/regions/${encodeURIComponent(regionId)}/underserved/demo-seed`, { method: "POST" });
}
