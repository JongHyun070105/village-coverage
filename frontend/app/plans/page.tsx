"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowDownToLine, ArrowRight, ClipboardCheck, FileCheck2, RefreshCw } from "lucide-react";
import { ApiErrorNotice } from "@/components/api-error";
import { SolverStatus } from "@/components/solver-status";
import {
  fetchScheduleHistory,
  fetchSchedulePlan,
  replanSchedule,
  reviseSchedule,
  scheduleExportUrl,
  readSelectedRegionId,
} from "@/lib/api";
import { count, koreanDate, won } from "@/lib/format";
import type { ScheduleHistoryEntry, SchedulePlan } from "@/lib/types";
import {
  exportUrl,
  decisionMemoUrl,
  fetchAuditEvents,
  fetchPlanExplanations,
  transitionPlan,
  type AreaExplanation,
  type AuditEvent,
} from "@/lib/v4";

const PUBLIC_DEMO_MODE = process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true";

const STATUS_LABEL: Record<string, string> = {
  DRAFT: "초안",
  UNDER_REVIEW: "검토 중",
  CHANGES_REQUESTED: "수정 요청",
  APPROVED: process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true" ? "데모 승인됨" : "승인됨",
  SUPERSEDED: "대체됨",
};
const SCENARIO_LABEL: Record<string, string> = {
  efficiency: "효율 중심",
  balanced: "균형",
  minimum_coverage: "최소보장",
  underserved_first: "소외 최소화",
};
const EVENT_LABEL: Record<string, string> = {
  PLAN_GENERATED: "계획 생성",
  REPLAN: "재계획",
  PLAN_SUBMITTED_FOR_REVIEW: "검토 요청",
  PLAN_APPROVED: "계획 승인",
  PLAN_RETURNED_TO_DRAFT: "초안으로 반려",
  PLAN_CHANGES_REQUESTED: "수정 요청",
  PLAN_SUPERSEDED: "이전 승인안 대체",
  PROVIDER_PARTICIPATION_CHANGED: "공급자 참여 변경",
};

export default function PlansPage() {
  const router = useRouter();
  const [regionId, setRegionId] = useState(readSelectedRegionId);
  const [plans, setPlans] = useState<ScheduleHistoryEntry[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [plan, setPlan] = useState<SchedulePlan | null>(null);
  const [explanations, setExplanations] = useState<AreaExplanation[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [role, setRole] = useState<"PLANNER" | "REVIEWER">("PLANNER");
  const [error, setError] = useState<unknown>(null);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState("");
  const [changeComment, setChangeComment] = useState("");
  const [revisionBudget, setRevisionBudget] = useState("");
  const [historyVersion, setHistoryVersion] = useState(0);
  const [selectedVersion, setSelectedVersion] = useState(0);

  const refreshSelectedState = () => {
    setError(null);
    setHistoryVersion((value) => value + 1);
    if (selectedId) setSelectedVersion((value) => value + 1);
  };

  useEffect(() => {
    let active = true;
    fetchScheduleHistory(regionId)
      .then(({ plans: nextPlans }) => { if (active) setPlans(nextPlans); })
      .catch((reason: unknown) => { if (active) setError(reason); });
    return () => { active = false; };
  }, [regionId, historyVersion]);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("id");
    if (id) Promise.resolve().then(() => setSelectedId(id));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    Promise.all([
      fetchSchedulePlan(selectedId),
      fetchPlanExplanations(selectedId),
      PUBLIC_DEMO_MODE ? Promise.resolve({ events: [] as AuditEvent[] }) : fetchAuditEvents(selectedId),
    ])
      .then(([nextPlan, explanationBody, eventBody]) => {
        if (!active) return;
        setPlan(nextPlan);
        setRevisionBudget(String(nextPlan.budget_won));
        setExplanations(explanationBody.areas);
        setEvents(eventBody.events);
        setRegionId((current) => current === nextPlan.region_id ? current : nextPlan.region_id);
      })
      .catch((reason: unknown) => { if (active) setError(reason); })
      .finally(() => undefined);
    return () => { active = false; };
  }, [selectedId, selectedVersion]);

  const choosePlan = (id: string) => {
    setPlan(null);
    setExplanations([]);
    setEvents([]);
    setError(null);
    setSelectedId(id);
    setSelectedVersion((value) => value + 1);
    router.replace(`/plans?id=${encodeURIComponent(id)}`, { scroll: false });
  };

  const loading = Boolean(selectedId && !plan && !error);

  const lineage = useMemo(
    () => plan ? plans.filter((item) => item.lineage_root_id === plan.lineage_root_id).sort((a, b) => a.plan_version - b.plan_version) : [],
    [plan, plans],
  );

  async function changeApproval(action: "submit" | "approve" | "return" | "request_changes") {
    if (!plan) return;
    setWorking(true);
    setError(null);
    setNotice("");
    try {
      const result = await transitionPlan(
        plan.schedule_id, action, role, changeComment, plan.plan_version,
      );
      setNotice(`${result.label} 상태로 변경했습니다.`);
      setChangeComment("");
      const [nextPlan, explanationBody, eventBody, historyBody] = await Promise.all([
        fetchSchedulePlan(plan.schedule_id),
        fetchPlanExplanations(plan.schedule_id),
        PUBLIC_DEMO_MODE
          ? Promise.resolve({ events: [] as AuditEvent[] })
          : fetchAuditEvents(plan.schedule_id),
        fetchScheduleHistory(plan.region_id),
      ]);
      setPlan(nextPlan);
      setRevisionBudget(String(nextPlan.budget_won));
      setExplanations(explanationBody.areas);
      setEvents(eventBody.events);
      setPlans(historyBody.plans);
    } catch (reason) {
      setError(reason);
    } finally {
      setWorking(false);
    }
  }

  async function replan() {
    if (!plan) return;
    setWorking(true);
    setError(null);
    try {
      const next = await replanSchedule(plan.schedule_id, plan.plan_version);
      const historyBody = await fetchScheduleHistory(next.region_id);
      setPlans(historyBody.plans);
      setRegionId(next.region_id);
      choosePlan(next.schedule_id);
      setPlan(next);
      setNotice(`v${next.plan_version} 초안을 만들었습니다. 이전 계획은 보존됩니다.`);
    } catch (reason) {
      setError(reason);
    } finally {
      setWorking(false);
    }
  }

  async function createRequestedRevision() {
    if (!plan) return;
    setWorking(true);
    setError(null);
    try {
      const revised = await reviseSchedule(plan.schedule_id, {
        scenario_key: plan.scenario_key,
        budget_won: Number(revisionBudget || plan.budget_won),
        planning_policy: plan.planning_policy,
        region_id: plan.region_id,
      });
      const historyBody = await fetchScheduleHistory(revised.region_id);
      setPlans(historyBody.plans);
      setRegionId(revised.region_id);
      choosePlan(revised.schedule_id);
      setNotice(`검토 요청을 반영한 계획 v${revised.plan_version}을 새로 만들었습니다.`);
    } catch (reason) {
      setError(reason);
    } finally {
      setWorking(false);
    }
  }

  const effectiveStatus = plan?.approval_effective_status ?? plan?.approval_status ?? "DRAFT";

  return (
    <main className="page-shell plans-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">서비스 계획</p>
          <h1>계획 검토와 승인 이력</h1>
          <p className="page-lede">계획 버전, 산정 상태, 변경 근거와 검토 이력을 확인합니다. PLANNER·REVIEWER는 시연용 역할이며 실제 인증이 아닙니다.</p>
        </div>
        <Link href="/scenarios" className="text-link">시나리오 비교 <ArrowRight size={14} aria-hidden="true" /></Link>
      </header>

      {error ? <ApiErrorNotice error={error} onRetry={refreshSelectedState} retryLabel="최신 상태 다시 불러오기" /> : null}
      {notice ? <p className="plans-notice" role="status">{notice}</p> : null}

      <section className="panel plans-list-panel" aria-labelledby="plans-list-title">
        <div className="plans-section-heading">
          <div><h2 id="plans-list-title">저장된 계획</h2><p>기준 지역: {plans[0]?.region_name ?? regionId}</p></div>
          <button type="button" className="ghost-button" onClick={() => setHistoryVersion((value) => value + 1)}><RefreshCw size={14} aria-hidden="true" /> 새로고침</button>
        </div>
        {plans.length === 0 ? (
          <p className="plans-empty">{error ? "계획 이력을 불러오지 못했습니다." : "저장된 계획이 없습니다. 시나리오 비교에서 계획을 생성하면 이곳에 표시됩니다."}</p>
        ) : (
          <div className="plans-list" role="list" aria-label="저장된 계획 목록">
            {plans.map((item) => (
              <button type="button" key={item.schedule_id} className={`plans-list-item ${item.schedule_id === selectedId ? "selected" : ""}`} onClick={() => choosePlan(item.schedule_id)} aria-pressed={item.schedule_id === selectedId}>
                <span className="plans-item-title">{SCENARIO_LABEL[item.scenario_key] ?? item.scenario_key} · {item.region_name} · v{item.plan_version}</span>
                <span className="plans-item-meta">{koreanDate(item.created_at)} · {item.round_count}회 · {won(item.summary.total_cost_won)}</span>
                <span className={`approval-badge approval-${item.approval_effective_status ?? item.approval_status ?? "DRAFT"}`}>{STATUS_LABEL[item.approval_effective_status ?? item.approval_status ?? "DRAFT"] ?? "초안"}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      {!selectedId && !loading ? <section className="panel plans-empty-detail"><ClipboardCheck size={22} aria-hidden="true" /><h2>검토할 계획을 선택해 주세요</h2><p>계획 상태와 권역별 포함·제외 이유, 승인 이력을 확인할 수 있습니다.</p></section> : null}
      {loading ? <p className="loading-line" role="status" aria-live="polite">계획과 검토 근거를 불러오는 중입니다…</p> : null}

      {plan ? <>
        <section className="panel plan-detail-panel" aria-labelledby="selected-plan-title">
          <div className="plans-section-heading">
            <div>
              <p className="eyebrow">{SCENARIO_LABEL[plan.scenario_key] ?? plan.scenario_key} · {plan.region_name}</p>
              <h2 id="selected-plan-title">계획 v{plan.plan_version}</h2>
              <p>생성 {koreanDate(plan.created_at)} · ID {plan.schedule_id}</p>
            </div>
            <span className={`approval-badge approval-${effectiveStatus}`}>{STATUS_LABEL[effectiveStatus]}</span>
          </div>
          <SolverStatus status={plan.summary.solver_status} hasPlan={plan.rounds.length > 0} scope={plan.summary.optimality_scope} strategyUsed={plan.summary.strategy_used} fallbackUsed={plan.summary.fallback_used} fallbackReason={plan.summary.fallback_reason} solveTimeMs={plan.summary.solve_time_ms} />
          <dl className="plan-summary-grid">
            <div><dt>계획 비용</dt><dd>{won(plan.summary.total_cost_won)}</dd></div>
            <div><dt>공공재원 상한</dt><dd>{won(plan.summary.total_cost_won)}</dd><small>지원·이용료 미확정</small></div>
            <div><dt>서비스 회차</dt><dd>{count(plan.rounds.length)}</dd></div>
            <div><dt>서비스 권역</dt><dd>{count(plan.summary.covered_areas)} / {count(plan.summary.covered_areas + plan.summary.uncovered_areas)}</dd></div>
            <div><dt>미충족 권역</dt><dd>{count(plan.summary.uncovered_areas)}</dd></div>
            <div><dt>이동시간</dt><dd>{Math.round(plan.summary.travel_time_s / 60).toLocaleString("ko-KR")}분</dd></div>
          </dl>

          <div className="plan-detail-actions" aria-label="계획 작업">
            <Link className="ghost-button" href={`/calendar?schedule_id=${encodeURIComponent(plan.schedule_id)}`}>일정 상세</Link>
            <a className="ghost-button" href={scheduleExportUrl(plan.schedule_id)}><ArrowDownToLine size={14} aria-hidden="true" /> 회차 CSV</a>
            <a className="ghost-button" href={exportUrl(plan.schedule_id, "budget.csv")}><ArrowDownToLine size={14} aria-hidden="true" /> 예산 CSV</a>
            <a className="ghost-button" href={exportUrl(plan.schedule_id, "unmet.csv")}><ArrowDownToLine size={14} aria-hidden="true" /> 미충족 CSV</a>
            <a className="ghost-button" href={exportUrl(plan.schedule_id, "summary.pdf")}><ArrowDownToLine size={14} aria-hidden="true" /> 계획 요약 PDF</a>
            <a className="ghost-button" href={decisionMemoUrl(plan.schedule_id, "pdf")}><ArrowDownToLine size={14} aria-hidden="true" /> 검토보고서 PDF</a>
            <a className="ghost-button" href={decisionMemoUrl(plan.schedule_id, "html")} target="_blank" rel="noreferrer">인쇄용 검토보고서</a>
            {plan.replan_available ? <button type="button" className="ghost-button" onClick={() => void replan()} disabled={working}><RefreshCw size={14} aria-hidden="true" /> {working ? "재계획 중" : `불참 ${plan.replan_trigger_count}건 반영해 새 버전`}</button> : null}
          </div>

          <div className="plan-approval-controls">
            <label>시연 역할<select value={role} onChange={(event) => setRole(event.target.value as "PLANNER" | "REVIEWER")}><option value="PLANNER">계획 담당자 (PLANNER)</option><option value="REVIEWER">검토자 (REVIEWER)</option></select></label>
            <span>승인된 계획은 직접 수정하지 않으며, 변경 시 새 버전을 생성합니다.</span>
            {(effectiveStatus === "DRAFT" || effectiveStatus === "CHANGES_REQUESTED") ? <>
              {effectiveStatus === "CHANGES_REQUESTED" && <p className="feedback-note">검토자가 수정을 요청했습니다. 원본은 보존됩니다. 예산을 조정해 새 버전을 만들거나, 수정 사항을 확인한 뒤 다시 검토를 요청할 수 있습니다.</p>}
              {effectiveStatus === "CHANGES_REQUESTED" && <label>수정 후 예산 (원)
                <input type="number" min={0} max={100000000} step={100000} value={revisionBudget || plan.budget_won} onChange={(event) => setRevisionBudget(event.target.value)} />
              </label>}
              {effectiveStatus === "CHANGES_REQUESTED" && <button type="button" className="ghost-button" disabled={working || role !== "PLANNER"} onClick={() => void createRequestedRevision()}>
                {working ? "새 버전 계산 중" : "수정 반영해 새 버전 생성"}
              </button>}
              <button type="button" className="primary-button" disabled={working || role !== "PLANNER"} onClick={() => void changeApproval("submit")}>{effectiveStatus === "CHANGES_REQUESTED" ? "재검토 요청" : "검토 요청"}</button>
            </> : null}
            {effectiveStatus === "UNDER_REVIEW" ? <>
              <button type="button" className="primary-button" disabled={working || role !== "REVIEWER"} onClick={() => void changeApproval("approve")}>{PUBLIC_DEMO_MODE ? "데모 승인" : "검토 승인"}</button>
              {PUBLIC_DEMO_MODE ? null : <>
                <label className="plan-change-comment">수정 요청 사유
                  <textarea value={changeComment} maxLength={500} onChange={(event) => setChangeComment(event.target.value)} />
                </label>
                <button type="button" className="ghost-button" disabled={working || role !== "REVIEWER" || !changeComment.trim()} onClick={() => void changeApproval("request_changes")}>수정 요청</button>
                <button type="button" className="ghost-button" disabled={working || role !== "REVIEWER"} onClick={() => void changeApproval("return")}>초안으로 반려</button>
              </>}
            </> : null}
          </div>
        </section>

        <section className="panel" aria-labelledby="plan-versions-title">
          <h2 id="plan-versions-title">같은 계획 계보의 버전</h2>
          {lineage.length ? <ol className="plan-version-list">{lineage.map((version) => <li key={version.schedule_id} className={version.schedule_id === plan.schedule_id ? "current" : ""}><button type="button" onClick={() => choosePlan(version.schedule_id)}>v{version.plan_version} · {STATUS_LABEL[version.approval_effective_status ?? version.approval_status ?? "DRAFT"]} · {koreanDate(version.created_at)} · {won(version.summary.total_cost_won)}</button></li>)}</ol> : <p>현재 조회된 계획 이력에서 같은 계보의 다른 버전을 찾지 못했습니다.</p>}
          {plan.data_snapshot ? <details className="plan-snapshot"><summary>생성 시점 데이터 스냅샷</summary><dl><div><dt>결합 시각</dt><dd>{koreanDate(plan.data_snapshot.bound_at)}</dd></div><div><dt>공개자료 fixture 해시</dt><dd>{plan.data_snapshot.public_data_fixture_sha256 ?? "기록 없음"}</dd></div><div><dt>도로 행렬 fingerprint</dt><dd>{plan.data_snapshot.route_matrix_fingerprint ?? "기록 없음"}</dd></div><div><dt>근거 스냅샷 해시 수</dt><dd>{Object.keys(plan.data_snapshot.evidence_snapshots_sha256 ?? {}).length}</dd></div></dl></details> : null}
        </section>

        <section className="panel" aria-labelledby="plan-explanation-title">
          <h2 id="plan-explanation-title">권역별 포함·제외 이유</h2>
          <p>설명은 solver 결과와 규칙에서 생성하며 LLM 판단을 사용하지 않습니다.</p>
          <div className="table-wrap"><table className="data-table plans-table"><caption className="sr-only">계획 권역 포함 여부와 이유</caption><thead><tr><th scope="col">권역 ID</th><th scope="col">결과</th><th scope="col">회차</th><th scope="col">설명</th><th scope="col">다음 조치</th></tr></thead><tbody>
            {explanations.map((item) => <tr key={item.area_id}><th scope="row">{item.area_id}</th><td>{item.included ? "포함" : "미포함"}</td><td>{item.rounds}</td><td>{item.reasons_ko.join(" · ") || item.reasons.join(" · ") || "규칙상 별도 사유 없음"}</td><td>{item.suggested_action ?? "-"}</td></tr>)}
            {!explanations.length ? <tr><td colSpan={5}>권역 설명을 불러오지 못했거나 표시할 권역이 없습니다.</td></tr> : null}
          </tbody></table></div>
        </section>

        <section className="panel" aria-labelledby="plan-audit-title">
          <h2 id="plan-audit-title"><FileCheck2 size={17} aria-hidden="true" /> 검토·감사 이력</h2>
          {events.length ? <ol className="plan-audit-list">{events.map((event) => <li key={event.event_id}><strong>{EVENT_LABEL[event.event_type] ?? event.event_type}</strong><span>{koreanDate(event.occurred_at)} · {event.actor_role}</span></li>)}</ol> : <p>이 계획의 감사 이벤트가 아직 없습니다.</p>}
          <p className="plans-demo-note">감사 이력 화면에는 원문 메모나 개인 식별 정보를 표시하지 않습니다. 데모 역할은 로그인 인증을 대신하지 않습니다.</p>
        </section>
      </> : null}
    </main>
  );
}
