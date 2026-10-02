"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Check, GitMerge, ScanSearch } from "lucide-react";
import {
  fetchDemandEvidenceReview,
  resolveDuplicateEvidence,
  resolveEvidenceConflict,
} from "@/lib/api";
import type {
  DemandEvidenceReview,
  DuplicateEvidenceCandidate,
  EvidenceConflict,
  EvidenceReviewRecord,
} from "@/lib/types";

const sourceLabels: Record<string, string> = {
  phone: "전화조사",
  village_meeting: "마을회의",
  proxy: "대리조사",
  field: "현장조사",
};

const serviceLabels: Record<string, string> = {
  laundry: "세탁",
  daily_necessities: "생활용품 전달·지원",
  home_repair: "간단한 주거생활 지원",
};

const conflictLabels: Record<EvidenceConflict["conflict_type"], string> = {
  FREQUENCY_CONFLICT: "월 빈도",
  DATE_CONFLICT: "희망 날짜",
  TIME_CONFLICT: "희망 시각",
  PREFERRED_DAY_CONFLICT: "선호 요일",
  EXCLUDED_DAY_CONFLICT: "제외 요일",
  SERVICE_TYPE_CONFLICT: "서비스 유형",
  CONSTRAINT_CONFLICT: "제약 조건",
};

const statusLabels: Record<string, string> = {
  UNREVIEWED: "미검토",
  POSSIBLE_DUPLICATE: "중복 후보",
  LINKED_DUPLICATE: "동일 요청으로 연결됨",
  CONFIRMED_DISTINCT: "별도 요청 확인",
  REVIEW_REQUIRED: "검토 필요",
  RESOLVED: "결정 완료",
  ACCEPTED_AS_RANGE: "범위로 유지",
};

const freshnessLabels: Record<EvidenceReviewRecord["freshness_status"], string> = {
  FRESH: "신선",
  AGING: "오래되는 중",
  STALE: "오래된 근거",
};

const fieldLabels: Record<string, string> = {
  frequency_per_month: "월 빈도",
  requested_period: "희망 시기",
  desired_date: "희망 날짜",
  desired_time: "희망 시각",
  recurring_pattern: "반복 방식",
  preferred_days: "선호 요일",
  excluded_days: "제외 요일",
  constraints: "제약 조건",
};

function formatMatchReasons(reasons: string[]) {
  return reasons.map((reason) => {
    if (reason === "SAME_LEGAL_AREA") return "같은 법정동";
    if (reason === "SAME_SERVICE_TYPE") return "같은 서비스";
    if (reason === "SAME_SOURCE_TYPE") return "같은 조사 출처";
    if (reason === "NORMALIZED_NOTE_FINGERPRINT_MATCH") return "정규화한 조사 메모 일치";
    if (reason === "FREQUENCY_WITHIN_ONE_PER_MONTH") return "월 빈도 차이 1회 이하";
    if (reason.startsWith("SURVEY_DATES_WITHIN_")) return "조사일 간격 기준 충족";
    if (reason.startsWith("NORMALIZED_FIELDS_MATCH:")) {
      const fields = reason.slice("NORMALIZED_FIELDS_MATCH:".length).split(",");
      return `구조화 항목 일치: ${fields.map((field) => fieldLabels[field] || field).join("·")}`;
    }
    return reason;
  }).join(" · ");
}

function displayEvidenceValue(conflict: EvidenceConflict, surveyId: string) {
  const item = conflict.evidence.find((record) => record.survey_id === surveyId);
  const structured = item?.structured_data ?? {};
  if (conflict.conflict_type === "DATE_CONFLICT") return String(structured.desired_date ?? "확인 안 됨");
  if (conflict.conflict_type === "TIME_CONFLICT") return String(structured.desired_time ?? "확인 안 됨");
  if (conflict.conflict_type === "PREFERRED_DAY_CONFLICT") {
    return (Array.isArray(structured.preferred_days) ? structured.preferred_days : []).join(", ") || "확인 안 됨";
  }
  if (conflict.conflict_type === "EXCLUDED_DAY_CONFLICT") {
    return (Array.isArray(structured.excluded_days) ? structured.excluded_days : []).join(", ") || "확인 안 됨";
  }
  if (conflict.conflict_type === "SERVICE_TYPE_CONFLICT") {
    return serviceLabels[item?.service_type || ""] || String(item?.service_type || "확인 안 됨");
  }
  if (conflict.conflict_type === "CONSTRAINT_CONFLICT") {
    return (item?.constraints ?? []).join(", ") || "확인 안 됨";
  }
  const value = conflict.values[surveyId];
  if (conflict.conflict_type === "FREQUENCY_CONFLICT") return `월 ${String(value)}회`;
  if (Array.isArray(value)) return value.join(", ");
  return String(value ?? "확인 안 됨");
}

function EvidenceLine({ item }: { item: EvidenceReviewRecord }) {
  const duplicateRole = item.evidence_status === "LINKED_DUPLICATE"
    ? item.survey_id === item.canonical_survey_id ? " · 대표 근거" : " · 계획 산정 제외"
    : "";
  return (
    <div className="evidence-review-record">
      <div>
        <strong>{sourceLabels[item.survey_type] || item.survey_type}</strong>
        <span>{item.survey_date} · 월 {item.frequency_per_month ?? "확인 안 됨"}회</span>
      </div>
      <span className={`evidence-state ${item.evidence_status.toLowerCase()}`}>
        {statusLabels[item.evidence_status]}{duplicateRole}
      </span>
      <span className={`evidence-state freshness-${item.freshness_status.toLowerCase()}`}>
        {freshnessLabels[item.freshness_status]} · {item.evidence_age_days}일 전
      </span>
      {item.free_text_note && <p>{item.free_text_note}</p>}
      {item.approved_draft_id && <small>승인된 AI 초안 {item.approved_draft_id.slice(0, 8)}와 연결</small>}
    </div>
  );
}

export default function EvidenceReviewPanel({ areaId, refreshKey = 0 }: { areaId: string; refreshKey?: number }) {
  const [storedReview, setStoredReview] = useState<DemandEvidenceReview | null>(null);
  const [pending, setPending] = useState("");
  const [storedError, setStoredError] = useState<{ areaId: string; message: string } | null>(null);
  const review = storedReview?.area_id === areaId ? storedReview : null;
  const error = storedError?.areaId === areaId ? storedError.message : "";
  const loading = !review && !error;

  useEffect(() => {
    let active = true;
    fetchDemandEvidenceReview(areaId)
      .then((result) => { if (active) setStoredReview(result); })
      .catch((cause) => {
        if (active) {
          setStoredError({
            areaId,
            message: cause instanceof Error ? cause.message : "근거 검토를 불러오지 못했습니다.",
          });
        }
      })
    return () => { active = false; };
  }, [areaId, refreshKey]);

  async function decideDuplicate(candidate: DuplicateEvidenceCandidate, decision: "LINKED_DUPLICATE" | "CONFIRMED_DISTINCT") {
    const key = `${candidate.survey_id_a}:${candidate.survey_id_b}`;
    setPending(key);
    setStoredError(null);
    try {
      const result = await resolveDuplicateEvidence(areaId, {
        first_survey_id: candidate.survey_id_a,
        second_survey_id: candidate.survey_id_b,
        decision,
        reason: decision === "LINKED_DUPLICATE"
          ? "담당자가 동일 요청으로 연결했습니다."
          : "담당자가 별도 요청으로 유지했습니다.",
      });
      setStoredReview(result.review);
    } catch (cause) {
      setStoredError({
        areaId,
        message: cause instanceof Error ? cause.message : "중복 검토 결과를 저장하지 못했습니다.",
      });
    } finally {
      setPending("");
    }
  }

  async function decideConflict(
    conflict: EvidenceConflict,
    method: "SELECT_EVIDENCE" | "ACCEPTED_AS_RANGE" | "LATEST_EVIDENCE" | "FURTHER_SURVEY",
    selectedSurveyId?: string,
  ) {
    setPending(conflict.conflict_id);
    setStoredError(null);
    const selected = conflict.evidence.find((item) => item.survey_id === selectedSurveyId);
    const sourceLabel = selected ? sourceLabels[selected.survey_type] || selected.survey_type : "";
    try {
      const result = await resolveEvidenceConflict(areaId, conflict.conflict_id, {
        method,
        ...(selectedSurveyId ? { selected_survey_id: selectedSurveyId } : {}),
        reason: method === "SELECT_EVIDENCE"
          ? `담당자가 ${sourceLabel} 근거를 채택했습니다.`
          : method === "ACCEPTED_AS_RANGE"
            ? "담당자가 빈도 차이를 범위로 유지했습니다."
            : method === "LATEST_EVIDENCE"
              ? "담당자가 최신 조사 우선 방식을 선택했습니다."
              : "담당자가 추가 조사를 요청했습니다.",
      });
      setStoredReview(result.review);
    } catch (cause) {
      setStoredError({
        areaId,
        message: cause instanceof Error ? cause.message : "충돌 해결 결과를 저장하지 못했습니다.",
      });
    } finally {
      setPending("");
    }
  }

  const byService = new Map<string, EvidenceReviewRecord[]>();
  for (const item of review?.evidence ?? []) {
    const records = byService.get(item.service_type) ?? [];
    records.push(item);
    byService.set(item.service_type, records);
  }

  return (
    <div className="evidence-review-panel" aria-label="중복 및 상충 근거 검토">
      <div className="evidence-review-heading">
        <div>
          <h3><ScanSearch size={15} /> 중복·충돌 근거 검토</h3>
          <span className="provenance-badge simulated">담당자 결정 전 확정 수요 아님</span>
        </div>
        {(review?.conflict_state === "REVIEW_REQUIRED" || review?.resurvey_recommended) && (
          <span className="evidence-review-alert"><AlertTriangle size={13} />
            {review.conflict_state === "REVIEW_REQUIRED" ? "검토 필요" : "재조사 권장"}
          </span>
        )}
      </div>

      {loading && <p className="evidence-review-empty">근거를 불러오는 중입니다.</p>}
      {error && <p className="request-warning" role="alert">{error}</p>}

      {!loading && review && (
        <>
          <p className={review.resurvey_recommended ? "evidence-freshness-notice" : "evidence-review-empty"}>
            {review.resurvey_recommended
              ? "최근 조사 없음 · 재조사 권장. 과거 근거는 오래된 자료로 보존합니다."
              : `근거 신선도: 신선 ${review.freshness_summary.FRESH}건 · 오래되는 중 ${review.freshness_summary.AGING}건 · 오래됨 ${review.freshness_summary.STALE}건`}
          </p>
          <div className="evidence-review-groups">
            {[...byService.entries()].map(([serviceType, records]) => (
              <section key={serviceType} aria-label={`${serviceLabels[serviceType] || serviceType} 근거`}>
                <h4>{serviceLabels[serviceType] || serviceType}</h4>
                {records.map((record) => <EvidenceLine key={record.survey_id} item={record} />)}
              </section>
            ))}
            {review.evidence.length === 0 && (
              <p className="evidence-review-empty">아직 승인된 조사 근거가 없습니다.</p>
            )}
          </div>

          <div className="evidence-review-decisions">
            <h4><GitMerge size={14} /> 중복 후보</h4>
            {review.duplicate_candidates.length === 0 ? (
              <p className="evidence-review-empty">검토할 중복 후보가 없습니다.</p>
            ) : review.duplicate_candidates.map((candidate) => {
              const first = review.evidence.find((item) => item.survey_id === candidate.survey_id_a);
              const second = review.evidence.find((item) => item.survey_id === candidate.survey_id_b);
              const key = `${candidate.survey_id_a}:${candidate.survey_id_b}`;
              return (
                <article className="evidence-review-decision" key={key}>
                  <div>
                    <strong>{first ? sourceLabels[first.survey_type] : "조사"} ↔ {second ? sourceLabels[second.survey_type] : "조사"}</strong>
                    <span>{candidate.date_gap_days}일 간격 · {statusLabels[candidate.status]}</span>
                    <small>{formatMatchReasons(candidate.match_reasons)}</small>
                  </div>
                  <div className="evidence-review-actions">
                    <button type="button" disabled={pending === key || candidate.status === "LINKED_DUPLICATE"} onClick={() => decideDuplicate(candidate, "LINKED_DUPLICATE")}>동일 요청으로 연결</button>
                    <button type="button" disabled={pending === key || candidate.status === "CONFIRMED_DISTINCT"} onClick={() => decideDuplicate(candidate, "CONFIRMED_DISTINCT")}>별도 요청으로 유지</button>
                  </div>
                </article>
              );
            })}
          </div>

          <div className="evidence-review-decisions">
            <h4><AlertTriangle size={14} /> 상충 근거</h4>
            {review.conflicts.length === 0 ? (
              <p className="evidence-review-empty">서로 다른 결과가 보고되지 않았습니다.</p>
            ) : review.conflicts.map((conflict) => (
              <article className="evidence-review-decision" key={conflict.conflict_id}>
                <div>
                  <strong>{serviceLabels[conflict.service_type || ""] || "서비스"} · {conflictLabels[conflict.conflict_type]}</strong>
                  <span className={conflict.status === "REVIEW_REQUIRED" ? "evidence-review-alert" : "evidence-state resolved"}>
                    {statusLabels[conflict.status]}
                  </span>
                  {conflict.evidence.map((item) => (
                    <small key={item.survey_id}>
                      {sourceLabels[item.survey_type] || item.survey_type} · {item.survey_date} · {displayEvidenceValue(conflict, item.survey_id)}
                    </small>
                  ))}
                  {conflict.status === "ACCEPTED_AS_RANGE" && conflict.frequency_min !== null && conflict.frequency_max !== null && (
                    <small>월 {conflict.frequency_min}~{conflict.frequency_max}회 범위 · 계획에는 낮은 값 월 {conflict.frequency_min}회를 사용합니다.</small>
                  )}
                  {conflict.reason && <small>결정 사유: {conflict.reason}</small>}
                </div>
                {conflict.status === "REVIEW_REQUIRED" && (
                  <div className="evidence-review-actions wrap">
                    {conflict.evidence.map((item) => (
                      <button type="button" key={item.survey_id} disabled={pending === conflict.conflict_id} onClick={() => decideConflict(conflict, "SELECT_EVIDENCE", item.survey_id)}>
                        {sourceLabels[item.survey_type] || item.survey_type} 채택
                      </button>
                    ))}
                    {conflict.conflict_type === "FREQUENCY_CONFLICT" && (
                      <button type="button" disabled={pending === conflict.conflict_id} onClick={() => decideConflict(conflict, "ACCEPTED_AS_RANGE")}>범위로 유지</button>
                    )}
                    <button type="button" disabled={pending === conflict.conflict_id} onClick={() => decideConflict(conflict, "LATEST_EVIDENCE")}>최신 조사 우선</button>
                    <button type="button" disabled={pending === conflict.conflict_id} onClick={() => decideConflict(conflict, "FURTHER_SURVEY")}>추가 조사 필요</button>
                  </div>
                )}
              </article>
            ))}
          </div>

          {review.audit.length > 0 && (
            <p className="evidence-review-audit"><Check size={13} /> 검토 결정 {review.audit.length}건 · 마지막 행위자 {review.audit.at(-1)?.actor_type} · {review.audit.at(-1)?.action_at}</p>
          )}
          <p className="evidence-review-policy">신선도 기준: 신선 {review.freshness_policy.fresh_max_age_days}일 이내, 오래됨 {review.freshness_policy.stale_after_days}일 초과. forecast 입력 최대 age {review.freshness_policy.forecast_max_evidence_age_days}일. 빈도 범위 정책: {review.frequency_planning_policy}. 중복 후보는 자동 병합하지 않습니다. 원 조사·관측·evidence는 보존됩니다.</p>
        </>
      )}
    </div>
  );
}
