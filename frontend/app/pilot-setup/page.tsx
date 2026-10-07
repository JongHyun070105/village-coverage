"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, CircleHelp, Database, FileCheck2, Store, Upload } from "lucide-react";
import {
  createPilotContext,
  createPilotPlan,
  fetchPilotPlan,
  fetchPilotPlans,
  fetchPilotContexts,
  fetchPilotSetupReadiness,
  fetchRegions,
  linkPilotResidentFeedback,
  recordPilotAssumption,
  replanPilotPlan,
  reviewPilotServiceMapping,
  transitionPilotPlan,
  type PilotContext,
  type PilotSetupReadiness,
} from "@/lib/api";
import type { RegionOption } from "@/lib/types";

const statusLabel: Record<string, string> = {
  READY: "확인됨",
  MISSING: "자료 없음",
  LIMITED: "제한적",
  REVIEW_REQUIRED: "검토 필요",
  NEEDS_SELECTION: "지역 선택 필요",
  NOT_REQUIRED_YET: "아직 필요 없음",
};

function PilotPlanProvenance({ planRecord }: { planRecord: Record<string, unknown> }) {
  const snapshot = (planRecord.data_snapshot ?? {}) as Record<string, unknown>;
  const plan = (planRecord.plan ?? {}) as Record<string, unknown>;
  const provenanceRecords = Array.isArray(snapshot.provenance_records)
    ? snapshot.provenance_records as Record<string, unknown>[]
    : [];
  const mappingReviews = Array.isArray(snapshot.provider_service_mapping_reviews)
    ? snapshot.provider_service_mapping_reviews as Record<string, unknown>[]
    : [];
  const assumptions = (snapshot.active_scenario_assumptions ?? {}) as Record<string, unknown>;
  const routeCache = (snapshot.route_cache_provenance ?? {}) as Record<string, unknown>;
  const providerInputs = Array.isArray(plan.provider_inputs)
    ? plan.provider_inputs as Record<string, unknown>[]
    : [];
  const demandInputs = Array.isArray(plan.demand_inputs)
    ? plan.demand_inputs as Record<string, unknown>[]
    : [];
  const importBatchIds = Array.isArray(snapshot.import_batch_ids)
    ? snapshot.import_batch_ids.map(String)
    : [];
  const feedback = Array.isArray(snapshot.resident_feedback)
    ? snapshot.resident_feedback as Record<string, unknown>[]
    : [];

  return <details className="pilot-plan-provenance">
    <summary>계획 입력 근거와 재현 정보</summary>
    <dl>
      <dt>데이터 모드 / context</dt><dd>{String(snapshot.data_mode ?? "UNKNOWN")} · {String(snapshot.pilot_context_id ?? planRecord.pilot_context_id ?? "UNKNOWN")}</dd>
      <dt>지역 / 수요 / 공급 snapshot</dt><dd>{String(snapshot.region_snapshot_id ?? "UNKNOWN")} · {String(snapshot.demand_snapshot_id ?? "UNKNOWN")} · {String(snapshot.provider_snapshot_id ?? "UNKNOWN")}</dd>
      <dt>가장 최근 입력 기준일</dt><dd>{String(snapshot.source_snapshot_date ?? "UNKNOWN")}</dd>
      <dt>Import batch</dt><dd>{importBatchIds.join(", ") || "없음"}</dd>
      <dt>Optimizer / route source</dt><dd>{String(snapshot.optimizer_version ?? "UNKNOWN")} · {String(snapshot.route_source ?? "UNKNOWN")}</dd>
      <dt>Route matrix fingerprint</dt><dd>{String(snapshot.route_matrix_fingerprint ?? "UNKNOWN")}</dd>
      <dt>Route cache 원자료 기준일 / cache 수집일 / 최근 성공 / 이유</dt><dd>{String(routeCache.source_snapshot_date ?? "UNKNOWN")} · {String(routeCache.cache_fetched_date ?? "없음")} · {String(routeCache.last_successful_fetch ?? "없음")} · {String(routeCache.cache_reason ?? "cache 미사용")}</dd>
      <dt>Resident feedback</dt><dd>{feedback.length ? `${feedback.length}건 연결 · 미해결 충돌 ${String(snapshot.resident_feedback_unresolved_conflict_count ?? 0)}건` : "연결된 resident feedback 없음"}</dd>
    </dl>
    <h3>공급자 운영 조건과 가격 근거</h3>
    <pre>{JSON.stringify(providerInputs, null, 2)}</pre>
    <h3>수요·조사 근거와 경고</h3>
    <pre>{JSON.stringify({ demand_inputs: demandInputs, warnings: snapshot.data_freshness_warnings ?? [] }, null, 2)}</pre>
    <h3>시나리오 가정과 서비스 매핑 검토</h3>
    <pre>{JSON.stringify({ assumptions, mapping_reviews: mappingReviews }, null, 2)}</pre>
    <h3>연결된 주민 의견 (본문·연락처 제외)</h3>
    {feedback.length ? <div className="table-wrap"><table className="data-table">
      <caption>계획 snapshot에 연결된 개인정보 최소화 주민 의견</caption>
      <thead><tr><th scope="col">의견 ID</th><th scope="col">법정동 코드</th><th scope="col">유형 / 상태</th><th scope="col">접수일</th><th scope="col">미해결 충돌</th></tr></thead>
      <tbody>{feedback.map((item) => <tr key={String(item.feedback_id)}>
        <td>{String(item.feedback_id)}</td><td>{String(item.area_code)}</td>
        <td>{String(item.feedback_type)} · {String(item.status)}</td><td>{String(item.submitted_at)}</td>
        <td>{String(item.unresolved_conflict_count ?? 0)}</td>
      </tr>)}</tbody>
    </table></div> : <p>계획 시점에 연결된 resident feedback이 없습니다.</p>}
    <h3>Import provenance records</h3>
    <div className="table-wrap"><table className="data-table">
      <caption>Pilot plan source record provenance</caption>
      <thead><tr><th scope="col">양식</th><th scope="col">출처</th><th scope="col">Source ID</th><th scope="col">Record ID</th><th scope="col">기준일</th><th scope="col">권역 / 공급자 / 서비스</th></tr></thead>
      <tbody>{provenanceRecords.map((item) => <tr key={String(item.record_id)}>
        <td>{String(item.template_type ?? "UNKNOWN")}</td><td>{String(item.provenance ?? item.source_type ?? "UNKNOWN")}</td>
        <td>{String(item.source_id ?? "-")}</td><td>{String(item.source_record_id ?? item.row_fingerprint ?? "-")}</td>
        <td>{String(item.source_date ?? "-")}</td>
        <td>{[item.area_code, item.provider_org_id, item.service_type].filter(Boolean).map(String).join(" · ") || "-"}</td>
      </tr>)}</tbody>
    </table></div>
  </details>;
}

export default function PilotSetupPage() {
  const [regions, setRegions] = useState<RegionOption[]>([]);
  const [selectedRegion, setSelectedRegion] = useState("");
  const [areaCode, setAreaCode] = useState("");
  const [serviceType, setServiceType] = useState("laundry");
  const [contexts, setContexts] = useState<PilotContext[]>([]);
  const [contextId, setContextId] = useState("");
  const [contextName, setContextName] = useState("충남 현장 파일럿");
  const [dataMode, setDataMode] = useState<"PILOT" | "SYNTHETIC_REHEARSAL">("PILOT");
  const [scenario, setScenario] = useState("balanced");
  const [budgetWon, setBudgetWon] = useState(5000000);
  const [createdPlan, setCreatedPlan] = useState<Record<string, unknown> | null>(null);
  const [planMessage, setPlanMessage] = useState("");
  const [assumptionKey, setAssumptionKey] = useState<"route_matrix" | "provider_base_locations" | "service_prices_won" | "service_duration_minutes">("provider_base_locations");
  const [assumptionJson, setAssumptionJson] = useState("{}");
  const [assumptionReason, setAssumptionReason] = useState("");
  const [mappingProviderId, setMappingProviderId] = useState("");
  const [feedbackId, setFeedbackId] = useState("");
  const [mappingService, setMappingService] = useState("laundry");
  const [readiness, setReadiness] = useState<PilotSetupReadiness | null>(null);
  const [error, setError] = useState("");
  const [focusPlanId, setFocusPlanId] = useState("");
  const [focusApprovalId, setFocusApprovalId] = useState("");
  const errorRef = useRef<HTMLDivElement>(null);
  const planHeadingRef = useRef<HTMLHeadingElement>(null);
  const approvalStatusRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    Promise.all([fetchRegions(), fetchPilotContexts()]).then(([regionResult, contextResult]) => {
      setRegions(regionResult.regions);
      setSelectedRegion(regionResult.regions[0]?.county ?? "");
      setContexts(contextResult.contexts);
      const savedId = window.localStorage.getItem("village-coverage-pilot-context");
      const saved = contextResult.contexts.find((item) => item.context_id === savedId);
      if (saved) {
        setContextId(saved.context_id);
        setContextName(saved.context_name);
        setDataMode(saved.data_mode);
        fetchPilotPlans(saved.context_id)
          .then(({ plans }) => setCreatedPlan(plans.at(-1) ?? null))
          .catch((cause: Error) => setError(cause.message));
      }
    }).catch((cause: Error) => setError(cause.message));
  }, []);

  useEffect(() => {
    fetchPilotSetupReadiness(serviceType, areaCode || undefined, selectedRegion || undefined, contextId || undefined)
      .then(setReadiness)
      .catch((cause: Error) => setError(cause.message));
  }, [serviceType, areaCode, selectedRegion, contextId]);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  useEffect(() => {
    if (createdPlan?.plan_id === focusPlanId) planHeadingRef.current?.focus();
  }, [createdPlan?.plan_id, focusPlanId]);

  useEffect(() => {
    if (createdPlan?.plan_id === focusApprovalId) approvalStatusRef.current?.focus();
  }, [createdPlan?.plan_id, createdPlan?.approval_status, focusApprovalId]);

  const currentContext = contexts.find((item) => item.context_id === contextId);
  const savedBatchIds = new Set(
    Array.isArray((createdPlan?.data_snapshot as Record<string, unknown> | undefined)?.import_batch_ids)
      ? ((createdPlan?.data_snapshot as Record<string, unknown>).import_batch_ids as string[])
      : [],
  );
  const hasNewImportsAfterPlan = Boolean(
    currentContext?.import_batch_ids.some((batchId) => !savedBatchIds.has(batchId)),
  );

  const start = async () => {
    setError("");
    try {
      setReadiness(await fetchPilotSetupReadiness(
        serviceType,
        areaCode || undefined,
        selectedRegion || undefined,
        contextId || undefined,
      ));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "준비도를 불러오지 못했습니다.");
    }
  };

  const createContext = async () => {
    setError("");
    setCreatedPlan(null);
    try {
      const context = await createPilotContext(contextName, selectedRegion, dataMode);
      window.localStorage.setItem("village-coverage-pilot-context", context.context_id);
      setContexts((items) => [context, ...items]);
      setContextId(context.context_id);
      setReadiness(await fetchPilotSetupReadiness(serviceType, areaCode || undefined, selectedRegion, context.context_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "파일럿 데이터셋을 만들지 못했습니다.");
    }
  };

  const generatePlan = async () => {
    if (!contextId) return;
    setError("");
    setCreatedPlan(null);
    try {
      const plan = await createPilotPlan(contextId, scenario, budgetWon);
      setCreatedPlan(plan);
      setFocusPlanId(String(plan.plan_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "파일럿 계획을 만들지 못했습니다.");
    }
  };

  const saveAssumption = async () => {
    if (!contextId) return;
    setError("");
    try {
      const value = JSON.parse(assumptionJson) as Record<string, unknown> | Record<string, unknown>[];
      await recordPilotAssumption(contextId, assumptionKey, value, assumptionReason);
      setPlanMessage("시나리오 가정을 provenance와 함께 저장했습니다. 실제 입력자료와 별도로 유지됩니다.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "가정 JSON을 확인해 주세요.");
    }
  };

  const verifyMapping = async () => {
    if (!contextId || !mappingProviderId.trim()) return;
    setError("");
    try {
      await reviewPilotServiceMapping(contextId, mappingProviderId.trim(), mappingService, "VERIFIED_MAPPING");
      setPlanMessage("담당자 검토 결과를 저장했습니다. CSV의 제안값만으로는 optimizer에 반영되지 않습니다.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "서비스 매핑을 검토하지 못했습니다.");
    }
  };

  const linkFeedback = async () => {
    if (!contextId || !feedbackId.trim()) return;
    setError("");
    try {
      const linked = await linkPilotResidentFeedback(contextId, feedbackId.trim());
      const { contexts: nextContexts } = await fetchPilotContexts();
      setContexts(nextContexts);
      setFeedbackId("");
      setPlanMessage(`주민 의견 ${linked.feedback_id}를 연결했습니다. 본문·연락처는 pilot snapshot에 복사하지 않습니다. 기존 계획에는 반영되지 않으므로 새 버전을 만들어 확인하세요.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "주민 의견을 데이터셋에 연결하지 못했습니다.");
    }
  };

  const updatePlan = async (action: "submit" | "approve" | "request_changes") => {
    const planId = String(createdPlan?.plan_id ?? "");
    if (!planId) return;
    setError("");
    try {
      await transitionPilotPlan(planId, action, action === "submit" ? "PLANNER" : "REVIEWER", action === "request_changes" ? "현장 제공 조건과 최신 자료 기준일을 다시 확인해 주세요." : undefined);
      setCreatedPlan(await fetchPilotPlan(planId));
      setFocusApprovalId(planId);
      setPlanMessage(action === "request_changes" ? "변경 요청을 기록했습니다. 요청 사항 반영 후 새 계획 버전을 만드세요." : "계획 상태를 업데이트했습니다.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "계획 상태를 변경하지 못했습니다.");
    }
  };

  const replan = async (changeReason = "변경 요청 또는 확인된 공급자 참여 변경 반영") => {
    const planId = String(createdPlan?.plan_id ?? "");
    if (!planId) return;
    setError("");
    try {
      const plan = await replanPilotPlan(planId, changeReason);
      setCreatedPlan(plan);
      setFocusPlanId(String(plan.plan_id));
      setPlanMessage("같은 pilot context의 새 계획 버전을 만들었습니다.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "재계획을 만들지 못했습니다.");
    }
  };

  return (
    <main className="page-main">
      <header className="topbar"><div className="breadcrumb"><span>업무 시작</span><span className="breadcrumb-sep">/</span><strong>파일럿 초기 설정</strong></div><span className="pre-rnd-pill"><i /> 현장 검증 전</span></header>
      <div className="content-page">
        <div className="content-hero">
          <div className="eyebrow"><span className="eyebrow-line" /> 파일럿 초기 설정</div>
          <h1>지역 파일럿 준비 현황</h1>
          <p>기초자료, 주민 근거, 공급조건에서 빠진 항목을 확인합니다. 자료가 부족하면 임의 숫자 대신 부족 상태를 그대로 표시합니다.</p>
        </div>
        <div className="balanced-note"><CircleHelp size={16} /><span>파일럿 계획은 선택한 데이터셋의 확정 자료만 사용합니다. 데모 공급자·합성 수요는 자동으로 섞이지 않습니다. 실도로 구간·서비스 시간·공급자 기준 위치가 없으면 계획을 만들지 않고 필요한 입력을 표시합니다.</span></div>

        {error && <div className="alert-box" role="alert" tabIndex={-1} ref={errorRef}>{error}</div>}
        <section className="content-card pilot-setup-form" aria-labelledby="pilot-region-heading">
          <h2 id="pilot-region-heading"><Database size={16} /> 1. 지역·서비스 선택</h2>
          <label htmlFor="pilot-region">지역</label>
          <select id="pilot-region" value={selectedRegion} onChange={(event) => setSelectedRegion(event.target.value)}>
            {regions.map((region) => <option key={region.region_id} value={region.county}>{region.province} {region.county} {region.town}</option>)}
          </select>
          <label htmlFor="pilot-area-code">법정동 코드 (자료 조회 시 선택)</label>
          <input id="pilot-area-code" inputMode="numeric" pattern="[0-9]{10}" maxLength={10} value={areaCode} onChange={(event) => setAreaCode(event.target.value.replace(/\D/g, "").slice(0, 10))} placeholder="10자리 법정동 코드" />
          <label htmlFor="pilot-service">서비스 유형</label>
          <select id="pilot-service" value={serviceType} onChange={(event) => setServiceType(event.target.value)}>
            <option value="laundry">세탁</option><option value="daily_necessities">생활필수품</option><option value="home_repair">간단 집수리</option>
          </select>
          <button type="button" className="secondary-button" onClick={start}>현재 준비도 다시 확인</button>
        </section>

        <section className="content-card pilot-setup-form" aria-labelledby="pilot-context-heading">
          <h2 id="pilot-context-heading"><Database size={16} /> 2. 데이터셋 선택</h2>
          <label htmlFor="pilot-context">기존 데이터셋</label>
          <select id="pilot-context" value={contextId} onChange={(event) => {
            setContextId(event.target.value);
            const selected = contexts.find((item) => item.context_id === event.target.value);
            if (selected) {
              setContextName(selected.context_name);
              setDataMode(selected.data_mode);
              window.localStorage.setItem("village-coverage-pilot-context", selected.context_id);
            }
          }}>
            <option value="">데이터셋 선택</option>
            {contexts.map((context) => <option key={context.context_id} value={context.context_id}>{context.context_name} · {context.data_mode === "PILOT" ? "실제 입력자료" : "합성 리허설"}</option>)}
          </select>
          <label htmlFor="pilot-context-name">새 데이터셋 이름</label>
          <input id="pilot-context-name" value={contextName} onChange={(event) => setContextName(event.target.value)} maxLength={120} />
          <label htmlFor="pilot-data-mode">데이터 모드</label>
          <select id="pilot-data-mode" value={dataMode} onChange={(event) => setDataMode(event.target.value as "PILOT" | "SYNTHETIC_REHEARSAL")}>
            <option value="PILOT">실제 입력자료</option>
            <option value="SYNTHETIC_REHEARSAL">합성 리허설</option>
          </select>
          <button type="button" className="secondary-button" disabled={!selectedRegion || !contextName.trim()} onClick={createContext}>새 파일럿 데이터셋 만들기</button>
          {contextId && <p role="status">선택됨: {contextName} · {dataMode === "PILOT" ? "실제 입력자료" : "합성 리허설"} · 데이터셋 ID {contextId} · 가져온 자료 묶음 {contexts.find((item) => item.context_id === contextId)?.import_batch_ids.length ?? 0}개</p>}
        </section>

        {readiness && <>
          <section className="content-card" aria-labelledby="pilot-steps-heading">
            <h2 id="pilot-steps-heading">초기 설정 업무 흐름</h2>
            <ol className="pilot-steps">{readiness.steps.map((step) => <li key={step.step}><span className="pilot-step-number">{step.step}</span><div><strong>{step.label}</strong><span>{statusLabel[step.status] ?? step.status}</span></div></li>)}</ol>
          </section>

          <section className="content-card" aria-labelledby="pilot-readiness-heading">
            <h2 id="pilot-readiness-heading">자료 준비 상태</h2>
            <p>{contextId ? "선택한 pilot context의 확정·승격 자료만 표시합니다." : "context를 선택하면 해당 데이터셋의 확정·승격 자료만 표시합니다."} 공공 디렉터리의 조직 존재와 실제 운영조건은 별도로 확인합니다.</p>
            <div className="pilot-dimension-list">{readiness.dimensions.map((item) => <div className="pilot-dimension" key={item.id}><strong>{item.label}</strong><span>{statusLabel[item.status] ?? item.status}</span><small>{item.records.toLocaleString("ko-KR")}행{item.detail ? ` · ${item.detail}` : ""}</small></div>)}</div>
          </section>

          <section className="content-card" aria-labelledby="calibration-heading">
            <h2 id="calibration-heading">지역 보정 준비도 · {readiness.calibration.status}</h2>
            <p>이 상태는 준비도 판정입니다. 모델 입력을 자동 보정하지 않습니다. 행 수만으로 승격하지 않으며 unique observation, 기간, 분모, 표본 완결성, 출처 다양성, 신선도와 충돌을 함께 확인합니다.</p>
            <ul>{readiness.calibration.missing_requirements.map((item) => <li key={item}>수요 보정 조건 미충족: {item}</li>)}{readiness.calibration.operational_missing_requirements.map((item) => <li key={item}>운영 검증 조건 미충족: {item}</li>)}</ul>
            <Link className="text-link" href="/methodology">보정 기준 자세히 보기 <ArrowRight size={14} /></Link>
          </section>
        </>}

        {contextId && <section className="content-card pilot-setup-form" aria-labelledby="pilot-plan-heading">
          <h2 id="pilot-assumptions-heading">운영 입력·시나리오 가정</h2>
          <label htmlFor="pilot-feedback-id">연결할 주민 의견 ID</label>
          <input id="pilot-feedback-id" value={feedbackId} onChange={(event) => setFeedbackId(event.target.value)} maxLength={120} />
          <button type="button" className="secondary-button" disabled={!feedbackId.trim()} onClick={linkFeedback}>법정동 코드로 주민 의견 연결</button>
          <p>같은 데이터셋에 확정된 지역 자료의 법정동 코드와 일치해야 합니다. 의견 본문과 연락처는 저장·계획 export에 복사하지 않습니다.</p>
          <label htmlFor="pilot-mapping-provider">검토할 provider_org_id</label>
          <input id="pilot-mapping-provider" value={mappingProviderId} onChange={(event) => setMappingProviderId(event.target.value)} />
          <label htmlFor="pilot-mapping-service">서비스 mapping</label>
          <select id="pilot-mapping-service" value={mappingService} onChange={(event) => setMappingService(event.target.value)}><option value="laundry">세탁</option><option value="daily_necessities">생활필수품</option><option value="home_repair">간단 집수리</option></select>
          <button type="button" className="secondary-button" disabled={!mappingProviderId.trim()} onClick={verifyMapping}>서비스 mapping 검토·확정</button>
          <label htmlFor="pilot-assumption-key">명시적 시나리오 가정</label>
          <select id="pilot-assumption-key" value={assumptionKey} onChange={(event) => setAssumptionKey(event.target.value as typeof assumptionKey)}><option value="provider_base_locations">공급자 기준 위치</option><option value="route_matrix">도로 route matrix</option><option value="service_duration_minutes">서비스 소요시간</option><option value="service_prices_won">공급 단가</option></select>
          <label htmlFor="pilot-assumption-json">가정 값 JSON</label>
          <textarea id="pilot-assumption-json" rows={4} value={assumptionJson} onChange={(event) => setAssumptionJson(event.target.value)} />
          <label htmlFor="pilot-assumption-reason">가정 사유</label>
          <input id="pilot-assumption-reason" value={assumptionReason} onChange={(event) => setAssumptionReason(event.target.value)} maxLength={500} />
          <button type="button" className="secondary-button" disabled={!assumptionReason.trim()} onClick={saveAssumption}>가정 저장</button>
        </section>}

        {contextId && <section className="content-card pilot-setup-form" aria-labelledby="pilot-plan-heading">
          <h2 id="pilot-plan-heading">3. 선택한 데이터셋으로 계획 계산</h2>
          <label htmlFor="pilot-scenario">시나리오</label>
          <select id="pilot-scenario" value={scenario} onChange={(event) => setScenario(event.target.value)}>
            <option value="efficiency">효율 우선</option><option value="balanced">균형</option><option value="underserved_first">소외 최소화</option><option value="minimum_coverage">최소 서비스 보장</option>
          </select>
          <label htmlFor="pilot-budget">예산 (원)</label>
          <input id="pilot-budget" type="number" min={0} step={10000} value={budgetWon} onChange={(event) => setBudgetWon(Number(event.target.value))} />
          <button type="button" className="primary-button" onClick={generatePlan}>파일럿 계획 만들기</button>
          {planMessage && <p className="import-message" role="status">{planMessage}</p>}
          {createdPlan && <section className="import-message pilot-plan-summary" aria-label="현재 파일럿 계획">
            <h3 tabIndex={-1} ref={planHeadingRef}>파일럿 계획 {String(createdPlan.plan_id)} · v{String(createdPlan.plan_version)}</h3><p role="status" tabIndex={-1} ref={approvalStatusRef}>승인 상태 {String(createdPlan.approval_status)} · context {String(createdPlan.pilot_context_id)} · {String((createdPlan.data_snapshot as Record<string, unknown> | undefined)?.optimizer_version ?? "")}</p><span>계획된 zero-service 마을 {String(((createdPlan.plan as Record<string, unknown> | undefined)?.planned_coverage as Record<string, unknown> | undefined)?.zero_service_area_count ?? "UNKNOWN")} · 도로 source {String((createdPlan.plan as Record<string, unknown> | undefined)?.route_source ?? "UNKNOWN")}</span>
            <PilotPlanProvenance planRecord={createdPlan} />
            <div className="pilot-setup-actions">
              {createdPlan.approval_status === "DRAFT" && <button type="button" className="secondary-button" onClick={() => void updatePlan("submit")}>검토 요청</button>}
              {createdPlan.approval_status === "UNDER_REVIEW" && <><button type="button" className="secondary-button" onClick={() => void updatePlan("request_changes")}>변경 요청</button><button type="button" className="secondary-button" onClick={() => void updatePlan("approve")}>승인</button></>}
              {createdPlan.approval_status === "CHANGES_REQUESTED" && <button type="button" className="secondary-button" onClick={() => void replan()}>새 버전 재계획</button>}
              {createdPlan.approval_status === "APPROVED" && hasNewImportsAfterPlan && <button type="button" className="secondary-button" onClick={() => void replan("승인 후 새로 확정한 import 자료 반영")}>새 import 반영해 버전 생성</button>}
            </div>
          </section>}
          {dataMode === "SYNTHETIC_REHEARSAL" && <p className="provenance-footer">합성 field-pilot rehearsal입니다. 현장 실증이나 실제 수행 결과로 해석하지 않습니다.</p>}
        </section>}

        <section className="content-card pilot-setup-actions" aria-label="다음 작업">
          <Link className="primary-button" href="/pilot-imports"><Upload size={16} /> 파일럿 CSV 검토하기</Link>
          <Link className="secondary-button" href="/providers"><Store size={16} /> 공급자 디렉터리 확인</Link>
          <Link className="secondary-button" href="/plans"><FileCheck2 size={16} /> 기존 계획 검토</Link>
        </section>
        <p className="provenance-footer">파일럿 import 기록은 출처·batch·row fingerprint와 계획 snapshot을 보존합니다. 합성 리허설은 현장 수행성과·운영가능성·지자체 승인 또는 실증 결과로 해석할 수 없습니다.</p>
      </div>
    </main>
  );
}
