"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Check, CircleHelp, LockKeyhole, Save, WandSparkles } from "lucide-react";
import {
  approveDemandDraft,
  createDemandDraft,
  fetchDemandDrafts,
  fetchDemandAreas,
  fetchRegions,
  readSelectedRegionId,
  saveSelectedRegionId,
} from "@/lib/api";
import type {
  DemandApprovalResult,
  DemandDraft,
  DemandStructureResult,
  RegionOption,
  ReviewedDemandRequest,
  StructuredDemandRequest,
  SurveyType,
} from "@/lib/types";
import { koreaDateValue } from "@/lib/date";
import EvidenceReviewPanel from "@/components/evidence-review-panel";

const sample = "겨울철 세탁 서비스를 월 2회 요청하고, 병원 방문일은 피하고 싶다고 함.";
const serviceLabels: Record<string, string> = {
  laundry: "세탁",
  daily_necessities: "생활용품 전달·지원",
  home_repair: "간단한 주거생활 지원",
  licensed_repair: "자격·인허가 필요 수리",
  mobility_support: "이동 지원",
  medical_service: "의료 서비스",
  legal_service: "법률 서비스",
  unknown: "서비스 확인 필요",
};
const policyLabels: Record<string, string> = {
  ALLOWED: "초기 지원 허용",
  REGULATED: "인허가 검토 필요",
  EXCLUDED: "초기 범위 제외",
  UNCLASSIFIED: "서비스 확인 필요",
};
const sourceLabels: Record<SurveyType, string> = {
  phone: "전화 상담",
  village_meeting: "마을 회의",
  proxy: "이장·대리 조사",
  field: "현장 조사",
};
const weekdayOptions = [
  ["monday", "월"],
  ["tuesday", "화"],
  ["wednesday", "수"],
  ["thursday", "목"],
  ["friday", "금"],
  ["saturday", "토"],
  ["sunday", "일"],
] as const;
const allowedServices = ["laundry", "daily_necessities", "home_repair"] as const;

function toApprovalRequest(request: StructuredDemandRequest): ReviewedDemandRequest {
  return {
    service_type: request.service_type as ReviewedDemandRequest["service_type"],
    requested_period: request.requested_period,
    frequency_per_month: request.frequency_per_month,
    desired_date: request.desired_date,
    desired_time: request.desired_time,
    recurring_pattern: request.recurring_pattern,
    urgency: request.urgency,
    urgency_evidence: request.urgency_evidence,
    preferred_days: request.preferred_days,
    excluded_days: request.excluded_days,
    constraints: request.constraints,
  };
}

export default function DemandPage() {
  const [regions, setRegions] = useState<RegionOption[]>([]);
  const [regionId, setRegionId] = useState("");
  const [areas, setAreas] = useState<Array<{ area_id: string; name: string; legal_code: string }>>([]);
  const [areaId, setAreaId] = useState("");
  const [sourceType, setSourceType] = useState<SurveyType>("phone");
  const [surveyDate, setSurveyDate] = useState("");
  const [text, setText] = useState(sample);
  const [draft, setDraft] = useState<DemandDraft | null>(null);
  const [savedDrafts, setSavedDrafts] = useState<DemandDraft[]>([]);
  const [approval, setApproval] = useState<DemandApprovalResult | null>(null);
  const [evidenceReviewRevision, setEvidenceReviewRevision] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchRegions()
      .then(({ regions: options, default_region_id }) => {
        setRegions(options);
        const remembered = readSelectedRegionId();
        const preferred = options.some((region) => region.region_id === remembered)
          ? remembered
          : default_region_id;
        setRegionId(preferred);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "지역 목록을 읽지 못했습니다."));
  }, []);

  useEffect(() => {
    if (!regionId) return;
    let active = true;
    saveSelectedRegionId(regionId);
    fetchDemandAreas(regionId)
      .then(({ areas: options }) => {
        if (!active) return;
        setAreas(options);
        const requestedAreaId = new URLSearchParams(window.location.search).get("area_id");
        setAreaId((current) => options.some((area) => area.area_id === requestedAreaId)
          ? requestedAreaId ?? ""
          : options.some((area) => area.area_id === current) ? current : options[0]?.area_id || "");
        setDraft(null);
        setApproval(null);
      })
      .catch((cause) => {
        if (active) setError(cause instanceof Error ? cause.message : "서비스 권역을 읽지 못했습니다.");
      });
    return () => { active = false; };
  }, [regionId]);

  useEffect(() => {
    if (!areaId) return;
    let active = true;
    fetchDemandDrafts(areaId)
      .then(({ drafts }) => { if (active) setSavedDrafts(drafts); })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "미검토 초안을 읽지 못했습니다."); });
    return () => { active = false; };
  }, [areaId, draft?.status]);

  function updateRequest(index: number, changes: Partial<ReviewedDemandRequest>) {
    setDraft((current) => {
      if (!current) return current;
      const requests = current.structured.requests.map((request, itemIndex) =>
        itemIndex === index ? { ...request, ...changes } : request,
      );
      return { ...current, structured: { ...current.structured, requests } };
    });
    setApproval(null);
  }

  function updateDraftStructure(changes: Partial<DemandStructureResult>) {
    setDraft((current) => current
      ? { ...current, structured: { ...current.structured, ...changes } }
      : current);
    setApproval(null);
  }

  async function createDraft(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setDraft(null);
    setApproval(null);
    try {
      const created = await createDemandDraft({
        area_id: areaId,
        survey_type: sourceType,
        survey_date: surveyDate,
        text,
      });
      setDraft(created);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "구조화 초안을 저장하지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function approveDraft() {
    if (!draft) return;
    setLoading(true);
    setError("");
    try {
      const approved = await approveDemandDraft(draft.draft_id, {
        requests: draft.structured.requests.map(toApprovalRequest),
        needs_followup_survey: draft.structured.needs_followup_survey,
        followup_reason: draft.structured.followup_reason,
      });
      setApproval(approved);
      setDraft({ ...draft, status: "APPROVED" });
      setEvidenceReviewRevision((revision) => revision + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "검토 결과를 승인하지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  function openSavedDraft(saved: DemandDraft) {
    setDraft(saved);
    setApproval(null);
    setError("");
  }

  const selectedRegion = regions.find((region) => region.region_id === regionId);
  const selectedArea = areas.find((area) => area.area_id === areaId);
  const outOfScopeRequests = draft?.structured.requests.filter(
    (request) => request.service_policy.policy_status !== "ALLOWED",
  ) ?? [];
  const approvalDisabled = !draft
    || draft.status !== "DRAFT"
    || draft.structured.requests.length === 0
    || outOfScopeRequests.length > 0
    || loading;

  return (
    <main className="page-main">
      <header className="topbar">
        <div className="breadcrumb"><span>정책 설계</span><span className="breadcrumb-sep">/</span><strong>주민 요청 구조화</strong></div>
        <div className="topbar-right"><span className="pre-rnd-pill"><i /> PRE-R&amp;D 검증</span><span className="avatar">VC</span></div>
      </header>
      <div className="content-page">
        <div className="content-hero">
          <div className="eyebrow"><span className="eyebrow-line" /> 수요 구조화 검토</div>
          <h1>조사 기록을 검토하고 근거로 승인</h1>
          <p>구조화는 명시된 문장만 추출합니다. 담당자가 수정·승인하기 전에는 조사 기록이 수요 근거나 계획 입력에 반영되지 않습니다.</p>
        </div>

        <div className="demand-layout">
          <section className="content-card">
            <h2>전화·회의·대리·현장 기록</h2>
            {savedDrafts.length > 0 && (
              <div className="saved-draft-row" aria-label="저장된 미검토 초안">
                <label htmlFor="saved-draft">미검토 초안 이어서 검토</label>
                <select id="saved-draft" value="" onChange={(event) => {
                  const selected = savedDrafts.find((item) => item.draft_id === event.target.value);
                  if (selected) openSavedDraft(selected);
                }}>
                  <option value="">초안 선택</option>
                  {savedDrafts.map((item) => <option key={item.draft_id} value={item.draft_id}>
                    {sourceLabels[item.survey_type]} · {item.survey_date} · {item.draft_id.slice(0, 8)}
                  </option>)}
                </select>
              </div>
            )}
            <form onSubmit={createDraft}>
              <div className="demand-form-grid">
                <label>충청남도 시군구·읍면
                  <select value={regionId} onChange={(event) => setRegionId(event.target.value)} required>
                    {regions.map((region) => <option key={region.region_id} value={region.region_id}>{region.name}</option>)}
                  </select>
                </label>
                <label>서비스 권역
                  <select value={areaId} onChange={(event) => setAreaId(event.target.value)} required>
                    {areas.map((area) => <option key={area.area_id} value={area.area_id}>{area.name} · {area.legal_code}</option>)}
                  </select>
                </label>
                <label>기록 출처
                  <select value={sourceType} onChange={(event) => setSourceType(event.target.value as SurveyType)}>
                    {Object.entries(sourceLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label>조사일
                  <input type="date" value={surveyDate} onFocus={() => {
                    if (!surveyDate) setSurveyDate(koreaDateValue());
                  }} onChange={(event) => setSurveyDate(event.target.value)} required />
                </label>
              </div>
              <label className="demand-note-label" htmlFor="demand-note">원문 기록</label>
              <textarea id="demand-note" className="demand-textarea" value={text} onChange={(event) => setText(event.target.value)} maxLength={10000} required placeholder="예: 겨울철 세탁 서비스를 월 2회 원하고, 병원 방문일은 피하고 싶다고 함." />
              <div className="demand-actions">
                <span>시연용 합성 조사 입력입니다. 알려진 개인정보는 마스킹한 기록만 초안에 저장합니다.</span>
                <button type="submit" className="button button-dark" disabled={loading || !text.trim() || !areaId || !surveyDate}>
                  <WandSparkles size={15} /> {loading ? "초안 저장 중…" : "구조화 초안 저장"}
                </button>
              </div>
            </form>
            {error && <div className="request-warning" role="alert">{error}</div>}

            {draft && (
              <section className="demand-review" aria-live="polite" aria-label="구조화 검토와 승인">
                <div className="demand-review-heading">
                  <div>
                    <strong>담당자 검토</strong>
                    <span className="pill">{draft.status === "APPROVED" ? "승인 완료" : "저장된 초안"}</span>
                  </div>
                  <small>{selectedRegion?.name} · {selectedArea?.name} · {sourceLabels[draft.survey_type]} · 조사일 {draft.survey_date}</small>
                </div>
                <div className="demand-source-note">
                  <strong>마스킹된 원문</strong>
                  <p>{draft.source_text_redacted}</p>
                  {draft.source_text_was_redacted && <span><LockKeyhole size={12} /> 식별정보를 마스킹했습니다.</span>}
                </div>
                <div className="request-warning">
                  <CircleHelp size={15} />
                  <span>상태: {draft.status === "APPROVED" ? "승인 완료" : "검토 대기"} · 승인 전 초안은 수요 근거와 충분도 계산에 들어가지 않습니다.</span>
                </div>
                {draft.structured.requests.length === 0 && <p>명확한 서비스 요청을 찾지 못했습니다. 원문을 확인하고 별도 기초조사를 남겨 주세요.</p>}
                {draft.structured.requests.map((request, index) => {
                  const policyStatus = request.service_policy.policy_status;
                  const allowed = policyStatus === "ALLOWED";
                  return (
                    <article className="demand-request-editor" key={`${request.service_type}-${index}`}>
                      <div className="demand-request-title">
                        <strong>요청 {index + 1}</strong>
                        <span className={`service-policy-chip ${allowed ? "allowed" : "review"}`}>
                          {request.service_policy.label_ko} · {policyLabels[policyStatus] || policyStatus}
                        </span>
                        <button type="button" className="text-button" onClick={() => updateDraftStructure({
                          requests: draft.structured.requests.filter((_item, itemIndex) => itemIndex !== index),
                        })}>요청 제거</button>
                      </div>
                      {!allowed && <p className="service-policy-reason">{request.service_policy.policy_reason} 이 요청은 초기 계획에 승인할 수 없습니다.</p>}
                      <div className="demand-review-grid">
                        <label>서비스
                          <select value={request.service_type} disabled={!allowed} onChange={(event) => updateRequest(index, { service_type: event.target.value as ReviewedDemandRequest["service_type"] })}>
                            {allowedServices.map((service) => <option key={service} value={service}>{serviceLabels[service]}</option>)}
                          </select>
                        </label>
                        <label>희망 시기
                          <input value={request.requested_period ?? ""} onChange={(event) => updateRequest(index, { requested_period: event.target.value || null })} placeholder="예: 겨울, 10월, 다음 달" />
                        </label>
                        <label>월 빈도
                          <input type="number" min="1" max="31" value={request.frequency_per_month ?? ""} onChange={(event) => updateRequest(index, { frequency_per_month: event.target.value ? Number(event.target.value) : null })} />
                        </label>
                        <label>희망 날짜
                          <input value={request.desired_date ?? ""} onChange={(event) => updateRequest(index, { desired_date: event.target.value || null })} placeholder="YYYY-MM-DD 또는 MM-DD" />
                        </label>
                        <label>희망 시각
                          <input type="time" value={request.desired_time ?? ""} onChange={(event) => updateRequest(index, { desired_time: event.target.value || null })} />
                        </label>
                        <label>반복 방식
                          <select value={request.recurring_pattern ?? ""} onChange={(event) => updateRequest(index, { recurring_pattern: (event.target.value || null) as ReviewedDemandRequest["recurring_pattern"] })}>
                            <option value="">확인 안 됨</option>
                            <option value="weekly">매주</option>
                            <option value="monthly">매월</option>
                            <option value="seasonal">계절 반복</option>
                            <option value="one_time">한 번</option>
                          </select>
                        </label>
                        <label>긴급도
                          <select value={request.urgency ?? ""} onChange={(event) => updateRequest(index, { urgency: (event.target.value || null) as ReviewedDemandRequest["urgency"], urgency_evidence: event.target.value ? request.urgency_evidence : null })}>
                            <option value="">표시 안 함</option>
                            <option value="urgent">긴급</option>
                          </select>
                        </label>
                        <label>긴급 근거 문구
                          <input value={request.urgency_evidence ?? ""} onChange={(event) => updateRequest(index, { urgency_evidence: event.target.value || null })} placeholder="원문에 있는 표현 그대로" />
                        </label>
                      </div>
                      <div className="demand-weekday-grid">
                        <fieldset>
                          <legend>선호 요일</legend>
                          {weekdayOptions.map(([day, label]) => <label key={`prefer-${day}`}>
                            <input type="checkbox" checked={request.preferred_days.includes(day)} onChange={(event) => updateRequest(index, { preferred_days: event.target.checked ? [...request.preferred_days, day] : request.preferred_days.filter((item) => item !== day) })} /> {label}
                          </label>)}
                        </fieldset>
                        <fieldset>
                          <legend>제외 요일</legend>
                          {weekdayOptions.map(([day, label]) => <label key={`exclude-${day}`}>
                            <input type="checkbox" checked={request.excluded_days.includes(day)} onChange={(event) => updateRequest(index, { excluded_days: event.target.checked ? [...request.excluded_days, day] : request.excluded_days.filter((item) => item !== day) })} /> {label}
                          </label>)}
                        </fieldset>
                      </div>
                      <label>추가 제약 (쉼표로 구분)
                        <input value={request.constraints.join(", ")} onChange={(event) => updateRequest(index, { constraints: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) })} placeholder="명시된 제약만 입력" />
                      </label>
                    </article>
                  );
                })}
                <label className="demand-followup-control">
                  <input type="checkbox" checked={draft.structured.needs_followup_survey} onChange={(event) => updateDraftStructure({ needs_followup_survey: event.target.checked })} />
                  추가 조사 필요
                </label>
                <label>추가 조사 사유
                  <input value={draft.structured.followup_reason ?? ""} onChange={(event) => updateDraftStructure({ followup_reason: event.target.value || null })} placeholder="검토 후 남길 이유" />
                </label>
                {draft.structured.confidence !== null && <p className="privacy-confirm">구조화 확신도 {Math.round(draft.structured.confidence * 100)}% · AI 보조 신호이며 수요 증거 점수는 아닙니다.</p>}
                <p className="demand-provenance">출처: {sourceLabels[draft.survey_type]} · 구조화: {draft.structured.method === "gemini_structured_output" ? "Gemini 초안" : "규칙 기반 초안"} · 시연용 검토 기록</p>
                {outOfScopeRequests.length > 0 && <div className="request-warning">규제·제외 서비스가 남아 있습니다. 해당 요청을 제거하거나 별도 범위 검토로 넘겨야 승인할 수 있습니다.</div>}
                {approval && <div className="balanced-note" role="status"><Check size={15} /><span>{approval.survey_ids.length}개 요청을 승인해 설문·DemandEvidence와 충분도를 갱신했습니다. 시연용 합성 자료입니다.</span></div>}
                <div className="demand-review-actions">
                  <span>승인하면 수정본, 원래 초안, 마스킹된 원문과 출처를 함께 보존합니다.</span>
                  <button type="button" className="button button-dark" onClick={approveDraft} disabled={approvalDisabled}>
                    <Save size={15} /> {loading ? "저장 중…" : draft.status === "APPROVED" ? "승인 완료" : "검토 결과 승인"}
                  </button>
                </div>
              </section>
            )}
            {areaId && <EvidenceReviewPanel areaId={areaId} refreshKey={evidenceReviewRevision} />}
          </section>

          <aside>
            <section className="content-card">
              <h2>기록 출처와 증거 수준</h2>
              <div className="service-steps">
                <div className="service-step"><span className="step-no">01</span><strong>출처를 지정</strong><p>전화·마을 회의·대리·현장 조사 유형이 근거 출처로 저장됩니다.</p></div>
                <div className="service-step"><span className="step-no">02</span><strong>원문에 있는 사실만</strong><p>날짜·시각·반복·긴급 표현은 직접 적혀 있을 때만 추출합니다.</p></div>
                <div className="service-step"><span className="step-no">03</span><strong>사람이 수정·승인</strong><p>승인 전 초안은 수요 evidence와 예측 이력에 반영되지 않습니다.</p></div>
              </div>
            </section>
            <section className="content-card privacy-card">
              <h2><LockKeyhole size={16} /> 데이터 보호</h2>
              <p>알려진 휴대전화·이메일·식별번호·일부 호칭 패턴을 마스킹합니다. 원문 초안과 승인된 조사 기록에는 마스킹된 문장만 저장합니다.</p>
              <p>인허가 검토·제외 서비스는 승인할 수 없습니다. AI 확신도는 주민 수요의 확실성을 뜻하지 않습니다.</p>
              <p>경로와 예산 배분은 AI가 아니라 별도 최적화 엔진이 계산합니다.</p>
            </section>
            <section className="content-card">
              <h2>입력 예시</h2>
              <button className="sample-prompt" onClick={() => setText(sample)}>겨울철 세탁 월 2회 요청, 병원 방문일 제외 <ArrowRight size={14} /></button>
              <button className="sample-prompt" onClick={() => setText("10월 8일 오후 2시 세탁 서비스를 원하며 목요일을 선호함. 긴급 지원 요청.")}>날짜·시각·긴급 문구 포함 <ArrowRight size={14} /></button>
              <button className="sample-prompt" onClick={() => setText("세탁 월 2회 요청. 다른 주민은 월 4회를 요청함.")}>서로 다른 빈도 요청 <ArrowRight size={14} /></button>
            </section>
          </aside>
        </div>
      </div>
    </main>
  );
}
