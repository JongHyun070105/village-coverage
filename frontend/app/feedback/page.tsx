"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { MessageSquareText, RefreshCw } from "lucide-react";
import { ApiErrorNotice } from "@/components/api-error";
import { fetchDemandAreas, readSelectedRegionId } from "@/lib/api";
import {
  FEEDBACK_STATUS_LABEL,
  FEEDBACK_TYPE_LABEL,
  FRESHNESS_LABEL,
  actOnFeedback,
  decideFeedbackDuplicate,
  fetchFeedback,
  fetchFeedbackList,
  resolveFeedbackConflict,
  submitFeedback,
  type FeedbackAction,
  type FeedbackConflict,
  type FeedbackItem,
  type FeedbackStatus,
  type FeedbackType,
} from "@/lib/feedback";
import { koreanDate } from "@/lib/format";
import type { DemandAreaOption } from "@/lib/types";

type Role = "PLANNER" | "REVIEWER";

const SERVICE_OPTIONS: [string, string][] = [
  ["", "서비스 미지정"],
  ["laundry", "세탁"],
  ["daily_necessities", "생활용품 전달·지원"],
  ["home_repair", "간단한 주거생활 지원"],
];
const CONFLICT_LABEL: Record<FeedbackConflict["conflict_type"], string> = {
  RESIDENT_CLAIM_VS_NO_OFFICIAL_DEMAND: "주민 주장 ↔ 조사상 수요 없음",
  RESIDENT_CLAIM_VS_SURVEY_FREQUENCY: "주민 주장 빈도 ↔ 조사 빈도",
};
const ACTION_LABEL: Record<FeedbackAction, string> = {
  start_review: "검토 시작",
  request_info: "추가 확인 요청",
  accept: "근거로 채택(검증 전)",
  reject: "반려",
  resolve: "처리 완료",
};
const ACTIONS_BY_STATUS: Record<FeedbackStatus, FeedbackAction[]> = {
  SUBMITTED: ["start_review", "reject"],
  UNDER_REVIEW: ["request_info", "accept", "reject"],
  NEEDS_MORE_INFO: ["start_review", "reject"],
  ACCEPTED_AS_EVIDENCE: ["resolve"],
  REJECTED: [],
  RESOLVED: [],
};
const NOTE_REQUIRED: FeedbackAction[] = ["request_info", "accept", "reject", "resolve"];

export default function FeedbackPage() {
  const [regionId] = useState(readSelectedRegionId);
  const [areas, setAreas] = useState<DemandAreaOption[]>([]);
  const [areaFilter, setAreaFilter] = useState(() => (typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("area_id") ?? ""));
  const [statusFilter, setStatusFilter] = useState("");
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [selected, setSelected] = useState<FeedbackItem | null>(null);
  const [role, setRole] = useState<Role>("PLANNER");
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [working, setWorking] = useState(false);
  const [version, setVersion] = useState(0);

  const [formArea, setFormArea] = useState("");
  const [formType, setFormType] = useState<FeedbackType>("SERVICE_REQUEST");
  const [formService, setFormService] = useState("laundry");
  const [formDescription, setFormDescription] = useState("");
  const [formFrequency, setFormFrequency] = useState("");
  const [formContact, setFormContact] = useState("");

  useEffect(() => {
    let active = true;
    fetchDemandAreas(regionId)
      .then((body) => { if (active) setAreas(body.areas); })
      .catch((reason: unknown) => { if (active) setError(reason); });
    return () => { active = false; };
  }, [regionId]);

  useEffect(() => {
    let active = true;
    fetchFeedbackList({ regionId, areaId: areaFilter || undefined, status: statusFilter || undefined })
      .then((body) => { if (active) setItems(body.items); })
      .catch((reason: unknown) => { if (active) setError(reason); });
    return () => { active = false; };
  }, [regionId, areaFilter, statusFilter, version]);

  const refresh = useCallback(() => setVersion((value) => value + 1), []);

  async function open(feedbackId: string) {
    setError(null);
    setNote("");
    try {
      setSelected(await fetchFeedback(feedbackId));
    } catch (reason) {
      setError(reason);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setWorking(true);
    setError(null);
    setNotice("");
    try {
      const frequency = formFrequency ? Number(formFrequency) : undefined;
      const created = await submitFeedback({
        area_id: formArea,
        service_type: formService || null,
        feedback_type: formType,
        description: formDescription,
        claim: frequency ? { claimed_frequency_per_month: frequency, claims_demand: true } : { claims_demand: true },
        submitter_role: "STAFF_ASSISTED",
        intake_channel: "STAFF_ASSISTED",
        contact: formContact || null,
      });
      setNotice(`의견을 접수했습니다. 검토 전까지 수요·계획에 반영되지 않습니다.${created.conflicts?.length ? " 공식 조사와 충돌하는 항목이 있어 검토가 필요합니다." : ""}`);
      setFormDescription("");
      setFormFrequency("");
      setFormContact("");
      setSelected(created);
      refresh();
    } catch (reason) {
      setError(reason);
    } finally {
      setWorking(false);
    }
  }

  async function act(action: FeedbackAction) {
    if (!selected) return;
    setWorking(true);
    setError(null);
    setNotice("");
    try {
      const next = await actOnFeedback(selected.feedback_id, action, role, note);
      setSelected(next);
      setNote("");
      setNotice(next.stale_plan_ids?.length
        ? `근거로 채택했습니다. 계획 ${next.stale_plan_ids.length}건을 재계획 필요로 표시했습니다. 계획 화면에서 재계획하세요.`
        : `${ACTION_LABEL[action]} 처리했습니다.`);
      refresh();
    } catch (reason) {
      setError(reason);
    } finally {
      setWorking(false);
    }
  }

  async function resolve(conflict: FeedbackConflict, method: "KEEP_OFFICIAL_EVIDENCE" | "FURTHER_SURVEY" | "ACCEPT_AS_RANGE") {
    if (!selected) return;
    setWorking(true);
    setError(null);
    try {
      await resolveFeedbackConflict(conflict.conflict_id, method, role, note || "담당자 판단");
      setSelected(await fetchFeedback(selected.feedback_id));
      setNote("");
      refresh();
    } catch (reason) {
      setError(reason);
    } finally {
      setWorking(false);
    }
  }

  async function decideDuplicate(otherId: string, state: "LINKED_DUPLICATE" | "CONFIRMED_DISTINCT") {
    if (!selected) return;
    setWorking(true);
    setError(null);
    try {
      const body = await decideFeedbackDuplicate(selected.feedback_id, otherId, state, role, note || "담당자 판단");
      setSelected(body.feedback);
      setNote("");
    } catch (reason) {
      setError(reason);
    } finally {
      setWorking(false);
    }
  }

  const areaName = (id: string) => areas.find((item) => item.area_id === id)?.name ?? id;

  return (
    <main className="page-shell feedback-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">근거 보정</p>
          <h1>주민 의견·정정</h1>
          <p className="page-lede">주민 의견은 검증 전 주장입니다. 담당자 검토와 채택을 거쳐도 수요·예측·계획은 자동으로 바뀌지 않으며, 계획 담당자가 재계획할 때만 반영됩니다. PLANNER·REVIEWER는 시연용 역할입니다.</p>
        </div>
      </header>

      {error ? <ApiErrorNotice error={error} onRetry={refresh} /> : null}
      {notice ? <p className="plans-notice" role="status">{notice}</p> : null}

      <section className="panel" aria-labelledby="feedback-intake-title">
        <h2 id="feedback-intake-title"><MessageSquareText size={17} aria-hidden="true" /> 의견 접수 (담당자 대리 입력)</h2>
        <p className="feedback-note">이름·전화번호 등은 설명란에 적지 마세요. 알려진 패턴은 자동 마스킹되며, 연락처는 별도 항목으로 보관되고 내보내기에서 제외됩니다.</p>
        <form className="feedback-form" onSubmit={onSubmit}>
          <label>생활권
            <select value={formArea} required onChange={(event) => setFormArea(event.target.value)}>
              <option value="" disabled>선택</option>
              {areas.map((item) => <option key={item.area_id} value={item.area_id}>{item.name}</option>)}
            </select>
          </label>
          <label>의견 유형
            <select value={formType} onChange={(event) => setFormType(event.target.value as FeedbackType)}>
              {Object.entries(FEEDBACK_TYPE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label htmlFor="feedback-service-type">관련 서비스</label>
          <select
            id="feedback-service-type"
            name="feedback_service_type"
            value={formService}
            onChange={(event) => setFormService(event.target.value)}
          >
              {SERVICE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <label>주장하는 월 희망 횟수 (선택)
            <input type="number" min="1" max="31" value={formFrequency} onChange={(event) => setFormFrequency(event.target.value)} />
          </label>
          <label className="feedback-wide">의견 내용
            <textarea value={formDescription} required maxLength={2000} onChange={(event) => setFormDescription(event.target.value)} />
          </label>
          <label className="feedback-wide">연락처 (선택, 별도 보관)
            <input value={formContact} maxLength={200} onChange={(event) => setFormContact(event.target.value)} />
          </label>
          <button type="submit" className="primary-button" disabled={working || !formArea || !formDescription.trim()}>접수</button>
        </form>
      </section>

      <section className="panel" aria-labelledby="feedback-list-title">
        <div className="plans-section-heading">
          <h2 id="feedback-list-title">접수된 의견</h2>
          <div className="feedback-filters">
            <label>생활권
              <select value={areaFilter} onChange={(event) => setAreaFilter(event.target.value)}>
                <option value="">전체</option>
                {areas.map((item) => <option key={item.area_id} value={item.area_id}>{item.name}</option>)}
              </select>
            </label>
            <label>상태
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="">전체</option>
                {Object.entries(FEEDBACK_STATUS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <button type="button" className="ghost-button" onClick={refresh}><RefreshCw size={14} aria-hidden="true" /> 새로고침</button>
          </div>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <caption className="sr-only">접수된 주민 의견 목록</caption>
            <thead><tr><th scope="col">접수일</th><th scope="col">생활권</th><th scope="col">유형</th><th scope="col">상태</th><th scope="col">신선도</th><th scope="col">내용</th><th scope="col">작업</th></tr></thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.feedback_id}>
                  <td>{koreanDate(item.submitted_at)}</td>
                  <td>{areaName(item.area_id)}</td>
                  <td>{FEEDBACK_TYPE_LABEL[item.feedback_type]}</td>
                  <td>{FEEDBACK_STATUS_LABEL[item.status]}</td>
                  <td>{FRESHNESS_LABEL[item.freshness]}</td>
                  <td className="feedback-cell-text">{item.description}</td>
                  <td><button type="button" className="ghost-button" onClick={() => void open(item.feedback_id)} aria-label={`${areaName(item.area_id)} 의견 검토 열기`}>검토</button></td>
                </tr>
              ))}
              {!items.length ? <tr><td colSpan={7}>접수된 의견이 없습니다.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>

      {selected ? (
        <section className="panel" aria-labelledby="feedback-detail-title">
          <h2 id="feedback-detail-title">검토: {areaName(selected.area_id)} · {FEEDBACK_TYPE_LABEL[selected.feedback_type]}</h2>
          <p className="feedback-note">{FEEDBACK_STATUS_LABEL[selected.status]} · {koreanDate(selected.submitted_at)} · {FRESHNESS_LABEL[selected.freshness]} 의견 · 연락처 {selected.has_contact ? "별도 보관" : "없음"}</p>
          <blockquote className="feedback-body">{selected.description}</blockquote>
          {selected.description_was_redacted ? <p className="feedback-note">개인정보 패턴이 마스킹되었습니다.</p> : null}
          {selected.claim.claimed_frequency_per_month ? <p>주장 빈도: 월 {selected.claim.claimed_frequency_per_month}회 (검증 전)</p> : null}
          {selected.resolution ? <p>처리 메모: {selected.resolution}</p> : null}

          {selected.conflicts?.length ? (
            <div className="feedback-conflicts">
              <h3>공식 근거와의 충돌</h3>
              {selected.conflicts.map((conflict) => (
                <div key={conflict.conflict_id} className="feedback-conflict">
                  <strong>{CONFLICT_LABEL[conflict.conflict_type]}</strong>
                  <span>조사 월 {conflict.official.frequency_per_month ?? "미확인"}회 · 주장 월 {conflict.claim.claimed_frequency_per_month ?? "수요 있음"}{conflict.claim.claimed_frequency_per_month ? "회" : ""} · {conflict.status === "RESOLVED" ? `해결됨(${conflict.resolution_method})` : "해결 필요"}</span>
                  {conflict.status === "REVIEW_REQUIRED" ? (
                    <div className="feedback-actions">
                      <button type="button" className="ghost-button" disabled={working || !note.trim()} onClick={() => void resolve(conflict, "KEEP_OFFICIAL_EVIDENCE")}>공식 근거 유지</button>
                      <button type="button" className="ghost-button" disabled={working || !note.trim()} onClick={() => void resolve(conflict, "FURTHER_SURVEY")}>추가 조사</button>
                      <button type="button" className="ghost-button" disabled={working || !note.trim()} onClick={() => void resolve(conflict, "ACCEPT_AS_RANGE")}>범위로 병기</button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}

          {selected.duplicate_candidates?.length ? (
            <div className="feedback-duplicates">
              <h3>유사 의견 후보 (자동 병합 없음)</h3>
              {selected.duplicate_candidates.map((candidate) => (
                <div key={candidate.feedback_id} className="feedback-conflict">
                  <span>유사도 {Math.round(candidate.similarity * 100)}% · {candidate.decision === "UNREVIEWED" ? "미판정" : candidate.decision === "LINKED_DUPLICATE" ? "중복으로 연결" : "별개로 확인"}</span>
                  {candidate.decision === "UNREVIEWED" ? (
                    <div className="feedback-actions">
                      <button type="button" className="ghost-button" disabled={working || !note.trim()} onClick={() => void decideDuplicate(candidate.feedback_id, "LINKED_DUPLICATE")}>중복으로 연결</button>
                      <button type="button" className="ghost-button" disabled={working || !note.trim()} onClick={() => void decideDuplicate(candidate.feedback_id, "CONFIRMED_DISTINCT")}>별개 의견</button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}

          <div className="plan-approval-controls">
            <label>시연 역할
              <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
                <option value="PLANNER">계획 담당자 (PLANNER)</option>
                <option value="REVIEWER">검토자 (REVIEWER)</option>
              </select>
            </label>
            <label className="feedback-wide">처리 메모 (반려·추가 확인·채택·충돌 해결 시 필수)
              <input value={note} maxLength={1000} onChange={(event) => setNote(event.target.value)} />
            </label>
            <div className="feedback-actions">
              {ACTIONS_BY_STATUS[selected.status].map((action) => (
                <button
                  type="button"
                  key={action}
                  className={action === "accept" ? "primary-button" : "ghost-button"}
                  disabled={working || (NOTE_REQUIRED.includes(action) && !note.trim())}
                  onClick={() => void act(action)}
                >{ACTION_LABEL[action]}</button>
              ))}
              {!ACTIONS_BY_STATUS[selected.status].length ? <span>더 이상 처리할 수 없는 상태입니다.</span> : null}
            </div>
          </div>
        </section>
      ) : null}
    </main>
  );
}
