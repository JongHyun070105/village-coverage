import { apiRequest } from "./api";

export type FeedbackStatus =
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "NEEDS_MORE_INFO"
  | "ACCEPTED_AS_EVIDENCE"
  | "REJECTED"
  | "RESOLVED";

export type FeedbackType =
  | "DATA_CORRECTION"
  | "SERVICE_REQUEST"
  | "ACCESSIBILITY_ISSUE"
  | "UNMET_SERVICE"
  | "SCHEDULE_CONCERN"
  | "OTHER";

export type FeedbackConflict = {
  conflict_id: string;
  conflict_type: "RESIDENT_CLAIM_VS_NO_OFFICIAL_DEMAND" | "RESIDENT_CLAIM_VS_SURVEY_FREQUENCY";
  status: "REVIEW_REQUIRED" | "RESOLVED";
  resolution_method: string | null;
  official: { survey_id?: string; survey_date?: string; frequency_per_month?: number | null };
  claim: { claimed_frequency_per_month?: number; claims_demand?: boolean };
};

export type FeedbackDuplicateCandidate = {
  feedback_id: string;
  similarity: number;
  decision: "UNREVIEWED" | "LINKED_DUPLICATE" | "CONFIRMED_DISTINCT";
};

export type FeedbackItem = {
  feedback_id: string;
  region_id: string;
  area_id: string;
  service_type: string | null;
  feedback_type: FeedbackType;
  submitted_at: string;
  submitter_role: string;
  intake_channel: string;
  description: string;
  description_was_redacted: boolean;
  requested_change: string | null;
  claim: { claimed_frequency_per_month?: number; claims_demand?: boolean };
  status: FeedbackStatus;
  status_label_ko: string;
  freshness: "FRESH" | "AGING" | "STALE";
  resolution: string | null;
  reviewer_id: string | null;
  has_contact?: boolean;
  conflicts?: FeedbackConflict[];
  duplicate_candidates?: FeedbackDuplicateCandidate[];
  stale_plan_ids?: string[];
};

export type FeedbackSignal = {
  accepted_claim_count: number;
  unverified_claim_count: number;
  bounded_observation_contribution: number;
  pending_feedback_count: number;
  open_conflict_count: number;
  needs_survey: boolean;
  evidence_grade: string;
  calibrated: boolean;
};

export type AreaFeedbackSummary = {
  area_id: string;
  counts: Record<FeedbackStatus, number>;
  total: number;
  recent: FeedbackItem[];
  signal: FeedbackSignal;
  note: string;
};

export type FeedbackSubmitInput = {
  area_id: string;
  service_type?: string | null;
  feedback_type: FeedbackType;
  description: string;
  requested_change?: string | null;
  claim?: { claimed_frequency_per_month?: number; claims_demand?: boolean };
  submitter_role: "RESIDENT" | "VILLAGE_LEADER" | "STAFF_ASSISTED" | "OTHER";
  intake_channel: "PUBLIC_FORM" | "STAFF_ASSISTED";
  contact?: string | null;
};

export type FeedbackAction = "start_review" | "request_info" | "accept" | "reject" | "resolve";

export const FEEDBACK_STATUS_LABEL: Record<FeedbackStatus, string> = {
  SUBMITTED: "접수됨",
  UNDER_REVIEW: "검토 중",
  NEEDS_MORE_INFO: "추가 확인 필요",
  ACCEPTED_AS_EVIDENCE: "근거로 채택(검증 전)",
  REJECTED: "반려",
  RESOLVED: "처리 완료",
};

export const FEEDBACK_TYPE_LABEL: Record<FeedbackType, string> = {
  DATA_CORRECTION: "정보 정정",
  SERVICE_REQUEST: "서비스 요청",
  ACCESSIBILITY_ISSUE: "접근성 문제",
  UNMET_SERVICE: "서비스 미제공",
  SCHEDULE_CONCERN: "일정 관련",
  OTHER: "기타",
};

export const FRESHNESS_LABEL = { FRESH: "최근", AGING: "시간 경과", STALE: "오래됨" } as const;

export function submitFeedback(input: FeedbackSubmitInput) {
  return apiRequest<FeedbackItem>("/api/feedback", { method: "POST", body: JSON.stringify(input) });
}

export function fetchFeedbackList(params: { regionId?: string; areaId?: string; status?: string }) {
  const query = new URLSearchParams();
  if (params.regionId) query.set("region_id", params.regionId);
  if (params.areaId) query.set("area_id", params.areaId);
  if (params.status) query.set("status", params.status);
  return apiRequest<{ items: FeedbackItem[] }>(`/api/feedback?${query.toString()}`);
}

export function fetchFeedback(feedbackId: string) {
  return apiRequest<FeedbackItem>(`/api/feedback/${encodeURIComponent(feedbackId)}`);
}

export function actOnFeedback(feedbackId: string, action: FeedbackAction, role: "PLANNER" | "REVIEWER", note?: string) {
  return apiRequest<FeedbackItem>(`/api/feedback/${encodeURIComponent(feedbackId)}/action`, {
    method: "POST",
    body: JSON.stringify({ action, role, note: note || null }),
  });
}

export function resolveFeedbackConflict(
  conflictId: string,
  resolutionMethod: "KEEP_OFFICIAL_EVIDENCE" | "FURTHER_SURVEY" | "ACCEPT_AS_RANGE",
  role: "PLANNER" | "REVIEWER",
  reason: string,
) {
  return apiRequest<FeedbackConflict>(`/api/feedback/conflicts/${encodeURIComponent(conflictId)}/resolve`, {
    method: "POST",
    body: JSON.stringify({ resolution_method: resolutionMethod, role, reason }),
  });
}

export function decideFeedbackDuplicate(
  feedbackId: string,
  otherId: string,
  state: "LINKED_DUPLICATE" | "CONFIRMED_DISTINCT",
  role: "PLANNER" | "REVIEWER",
  reason: string,
) {
  return apiRequest<{ feedback: FeedbackItem }>(`/api/feedback/${encodeURIComponent(feedbackId)}/duplicates`, {
    method: "POST",
    body: JSON.stringify({ other_feedback_id: otherId, state, role, reason }),
  });
}

export function fetchAreaFeedback(areaId: string) {
  return apiRequest<AreaFeedbackSummary>(`/api/villages/${encodeURIComponent(areaId)}/feedback`);
}
