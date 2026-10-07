"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, BadgeAlert, CalendarDays, Check, CircleHelp, Coins, MapPinned, RefreshCw, SlidersHorizontal, type LucideIcon } from "lucide-react";
import { CoverageMap } from "@/components/coverage-map";
import { apiBase, createSchedulePlan, DEFAULT_REGION_ID, fetchOverview, fetchRegions, readSelectedRegionId, saveSelectedRegionId } from "@/lib/api";
import type { Overview, PlanningPolicy, ScenarioKey, ScenarioResult, SchedulePlan, SurveyServiceType } from "@/lib/types";

const SCENARIOS: Array<{ id: ScenarioKey; title: string; short: string; note: string }> = [
  { id: "efficiency", title: "효율 우선", short: "EFFICIENT", note: "같은 예산으로 서비스 횟수를 늘립니다." },
  { id: "balanced", title: "균형", short: "BALANCED", note: "서비스량과 권역 분산을 함께 고려하고, 조사·취약도 정책 가중치를 반영합니다." },
  { id: "minimum_coverage", title: "최소 서비스 보장", short: "GUARANTEE", note: "정한 최소 회차를 채우는 권역 수를 먼저 높이고 부족을 표시합니다." },
  { id: "underserved_first", title: "소외 최소화", short: "UNDERSERVED", note: "서비스 공백이 긴 권역을 먼저 반영합니다. 이력은 입력·가정 기준의 시뮬레이션입니다." },
];

const SERVICE_LABELS: Record<SurveyServiceType, string> = {
  laundry: "세탁",
  daily_necessities: "생활용품 전달·지원",
  home_repair: "간단한 주거생활 지원",
};
const SERVICE_OPTIONS = Object.keys(SERVICE_LABELS) as SurveyServiceType[];
const GUARANTEE_FAILURE_LABELS: Record<string, string> = {
  SERVICE_NOT_ALLOWED: "허용 서비스에서 제외된 권역이 있습니다",
  DEMAND_BELOW_MINIMUM: "관측 수요가 설정한 최소 회차보다 적은 권역이 있습니다",
  MAX_TRAVEL_TIME: "최대 허브 왕복 이동시간을 넘는 권역이 있습니다",
  NO_SUPPORTED_PROVIDER: "해당 서비스를 제공할 공급자가 없습니다",
  PROVIDER_CAPACITY: "공급자 용량이 부족합니다",
  PROVIDER_CAPACITY_OR_SERVICE_MIX: "공급자 용량 또는 서비스별 공급 구성이 부족합니다",
  GUARANTEE_FEASIBILITY_NOT_PROVEN: "공급 용량 가능성을 계산으로 확인하지 못했습니다",
  GUARANTEE_COST_NOT_PROVEN: "필요 예산을 최적으로 산정하지 못했습니다",
};
const FULL_DEMAND_FUNDING_LABELS: Record<string, string> = {
  NO_SUPPORTED_PROVIDER: "해당 서비스를 제공할 공급자가 없습니다",
  PROVIDER_CAPACITY_OR_SERVICE_MIX: "공급자 용량 또는 서비스 구성이 모의수요에 부족합니다",
  SERVICE_NOT_ALLOWED: "허용 서비스 정책에서 제외된 수요가 있습니다",
  MAX_TRAVEL_TIME: "최대 허브 왕복 이동시간을 넘는 권역이 있습니다",
  OPTIMALITY_NOT_PROVEN: "최적성을 확인하지 못해 금액을 표시하지 않습니다",
};
const CONSTRAINT_REASON_LABELS: Record<string, string> = {
  SERVICE_NOT_ALLOWED: "정책에서 허용하지 않은 서비스",
  MAX_TRAVEL_TIME: "최대 허브 왕복 이동시간 초과",
  NO_SUPPORTED_PROVIDER: "해당 서비스를 제공할 공급자 없음",
  DEMAND_BELOW_MINIMUM: "모의 수요가 설정한 최소 회차보다 적음",
  PROVIDER_CAPACITY: "지원 공급자의 월간 회차 용량 부족",
  BUDGET: "예산 제약으로 배정 미충족",
  SHARED_BUDGET_OR_CAPACITY: "전체 배정에서 예산 또는 공급 용량 경쟁",
  SCENARIO_PRIORITY: "선택한 시나리오가 최소 회차를 우선하지 않음",
  MINIMUM_FREQUENCY: "설정한 최소 회차 미충족",
  BUDGET_OR_CAPACITY: "예산 또는 공급 용량 부족",
};

const money = (amount: number) => `${Math.round(amount).toLocaleString("ko-KR")}원`;
const number = (amount: number) => amount.toLocaleString("ko-KR");
const percentFromBasisPoints = (amount: number) => `${(amount / 100).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`;
const distanceKm = (meters: number) => `${(meters / 1000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}km`;
const signedNumber = (amount: number) => `${amount > 0 ? "+" : ""}${number(amount)}`;
const signedMoney = (amount: number) => `${amount > 0 ? "+" : amount < 0 ? "−" : ""}${money(Math.abs(amount))}`;
const duration = (seconds: number) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return hours ? `${hours}시간 ${minutes}분` : `${minutes}분`;
};
const fullDemandBudgetSummary = (result: ScenarioResult) => {
  if (
    result.full_demand_budget_status === "CALCULATED" &&
    result.full_demand_required_budget_won !== null &&
    result.full_demand_budget_gap_won !== null
  ) {
    return `${money(result.full_demand_required_budget_won)} 필요 · 추가 ${money(result.full_demand_budget_gap_won)}`;
  }
  return FULL_DEMAND_FUNDING_LABELS[result.full_demand_failure_reason ?? ""] ?? "조건 확인 필요";
};

function scheduleConstraintSummary(plan: SchedulePlan) {
  const reasons = [
    ...plan.summary.unmet_criteria.flatMap((item) => item.reasons?.length ? item.reasons : [item.reason]),
    ...plan.summary.minimum_frequency_gaps.flatMap((item) => item.reasons?.length ? item.reasons : [item.reason]),
  ];
  return [...new Set(reasons)].slice(0, 3).map((reason) => CONSTRAINT_REASON_LABELS[reason] || reason);
}

function MetricCard({ icon: Icon, label, value, detail, tone = "green" }: {
  icon: LucideIcon; label: string; value: string; detail: string; tone?: string;
}) {
  return (
    <div className="metric-card">
      <div className={`metric-icon ${tone}`}><Icon size={18} strokeWidth={1.9} /></div>
      <div className="metric-label">{label}</div>
      <strong className="metric-value">{value}</strong>
      <div className="metric-detail">{detail}</div>
    </div>
  );
}

function ScenarioMetrics({ result, surveyCovered, surveyCount, areaCount }: { result: ScenarioResult; surveyCovered: number; surveyCount: number; areaCount: number }) {
  return (
    <div className="scenario-stats">
      <div><span>월간 서비스 회차 충족</span><strong>{Math.round(result.service_fulfillment_rate * 100)}<small>%</small></strong></div>
      <div><span>서비스 권역</span><strong>{result.covered_villages}<small> / {areaCount}곳</small></strong></div>
      <div><span>조사 필요 포함</span><strong>{surveyCovered}<small> / {surveyCount}곳</small></strong></div>
      <div><span>도로 이동시간</span><strong>{duration(result.travel_time_s)}</strong></div>
    </div>
  );
}

function ApiUnavailable({ error, retry }: { error: string; retry: () => void }) {
  return (
    <div className="api-unavailable">
      <div className="api-unavailable-icon"><BadgeAlert size={21} /></div>
      <h2>계획 데이터를 불러오지 못했습니다</h2>
      <p>{error}</p>
      <p className="api-command"><code>uv run uvicorn backend.main:app --reload</code></p>
      <button className="button button-dark" onClick={retry}><RefreshCw size={15} /> 다시 불러오기</button>
      <span className="api-base">API: {apiBase()}</span>
    </div>
  );
}

export default function DashboardPage() {
  const [budget, setBudget] = useState(5_000_000);
  const [policy, setPolicy] = useState<PlanningPolicy>({
    minimum_services_per_area: 1,
    elderly_priority_weight: 500,
    single_elderly_household_priority_weight: 500,
    survey_required_protection_weight: 1000,
    maximum_round_trip_travel_minutes: null,
    allowed_services: SERVICE_OPTIONS,
    minimum_provider_compensation_won: 0,
  });
  const [overview, setOverview] = useState<Overview | null>(null);
  const [regionId, setRegionId] = useState(DEFAULT_REGION_ID);
  const [regionReady, setRegionReady] = useState(false);
  const [selected, setSelected] = useState<ScenarioKey>("balanced");
  const [compareAllScenarios, setCompareAllScenarios] = useState(false);
  const [providerScenarioPlans, setProviderScenarioPlans] = useState<Partial<Record<ScenarioKey, SchedulePlan>>>({});
  const [providerScenarioErrors, setProviderScenarioErrors] = useState<Partial<Record<ScenarioKey, string>>>({});
  const [providerScenarioRun, setProviderScenarioRun] = useState<{ budget: number; regionId: string; regionName: string; policy: PlanningPolicy } | null>(null);
  const [providerScenarioStep, setProviderScenarioStep] = useState<{ scenario: ScenarioKey; index: number } | null>(null);
  const [generatingProviderScenarios, setGeneratingProviderScenarios] = useState(false);
  const [selectedArea, setSelectedArea] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const reload = useCallback(() => setRefreshToken((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    fetchRegions().then(({ regions, default_region_id }) => {
      if (!active) return;
      const saved = readSelectedRegionId();
      const available = regions.some((region) => region.region_id === saved);
      const next = available ? saved : default_region_id;
      setRegionId(next);
      saveSelectedRegionId(next);
      setRegionReady(true);
    }).catch(() => {
      if (!active) return;
      setRegionId(DEFAULT_REGION_ID);
      setRegionReady(true);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!regionReady) return;
    let current = true;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const data = await fetchOverview(budget, policy, regionId);
        if (current) setOverview(data);
      } catch (cause) {
        if (current) setError(cause instanceof Error ? cause.message : "API 연결을 확인해 주세요.");
      } finally {
        if (current) setLoading(false);
      }
    }, 120);
    return () => { current = false; window.clearTimeout(timer); };
  }, [budget, policy, refreshToken, regionId, regionReady]);

  function selectRegion(value: string) {
    setRegionId(value);
    saveSelectedRegionId(value);
    setSelectedArea(null);
  }

  function setPolicyValue<K extends keyof PlanningPolicy>(key: K, value: PlanningPolicy[K]) {
    setPolicy((current) => ({ ...current, [key]: value }));
  }

  function setServiceAllowed(service: SurveyServiceType, enabled: boolean) {
    const allowed = new Set(policy.allowed_services);
    if (!enabled && allowed.size <= 1) return;
    if (enabled) allowed.add(service);
    else allowed.delete(service);
    setPolicyValue("allowed_services", SERVICE_OPTIONS.filter((option) => allowed.has(option)));
  }

  async function generateProviderScenarioComparison() {
    if (generatingProviderScenarios) return;
    const runBudget = budget;
    const runRegionId = regionId;
    const runPolicy = { ...policy, allowed_services: [...policy.allowed_services] };
    setProviderScenarioRun({
      budget: runBudget,
      regionId: runRegionId,
      regionName: overview?.region ?? runRegionId,
      policy: runPolicy,
    });
    setProviderScenarioPlans({});
    setProviderScenarioErrors({});
    setGeneratingProviderScenarios(true);
    try {
      for (const [index, scenario] of SCENARIOS.entries()) {
        setProviderScenarioStep({ scenario: scenario.id, index });
        try {
          const plan = await createSchedulePlan(scenario.id, runBudget, runPolicy, runRegionId);
          setProviderScenarioPlans((current) => ({ ...current, [scenario.id]: plan }));
        } catch (cause) {
          setProviderScenarioErrors((current) => ({
            ...current,
            [scenario.id]: cause instanceof Error ? cause.message : "일정 계산을 완료하지 못했습니다.",
          }));
        }
      }
    } finally {
      setProviderScenarioStep(null);
      setGeneratingProviderScenarios(false);
    }
  }

  const chosenResult = overview?.scenario_results[selected];
  const guarantee = overview?.scenario_results.minimum_coverage;
  const selectedSurvey = overview && chosenResult ? {
    total: overview.areas.filter((area) => area.needs_survey).length,
    covered: chosenResult.assignments.filter((item) => item.needs_survey && item.covered).length,
  } : { total: 0, covered: 0 };
  const selectedAssignment = useMemo(() => {
    if (!selectedArea || !chosenResult) return null;
    return chosenResult.assignments.find((item) => item.area_id === selectedArea) || null;
  }, [chosenResult, selectedArea]);
  const selectedAreaInfo = overview?.areas.find((area) => area.id === selectedArea);
  const selectedRegion = overview?.regions.find((region) => region.region_id === regionId);
  const counties = [...new Set((overview?.regions ?? []).map((region) => region.county))];
  const towns = (overview?.regions ?? []).filter((region) => region.county === selectedRegion?.county);

  return (
    <main className="page-main dashboard-page">
      <header className="topbar">
        <div className="breadcrumb"><span>정책 설계</span><span className="breadcrumb-sep">/</span><strong>공급계획 시뮬레이터</strong></div>
        <div className="topbar-right"><span className="pre-rnd-pill"><i /> 시뮬레이션 데모</span><span className="avatar">VC</span></div>
      </header>
      <div className="dashboard-content">
        <section className="welcome-row">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> 농촌 생활서비스 공급계획 시뮬레이터</div>
            <h1>제한된 예산으로,<br className="mobile-break" /> 어디까지 함께할 수 있을까요?</h1>
            <p className="welcome-copy">기록이 적다고 필요가 없다고 판단하지 않습니다. 예산에 따른 서비스 범위를 비교합니다.</p>
          </div>
          <div className="region-selector region-selector-controls" aria-label="서비스 지역 선택">
            <span className="region-icon"><MapPinned size={17} /></span>
            <span className="region-selector-fields">
              <small>충청남도 · 검증 시범 지역</small>
              <label>시군구<select aria-label="시군구 선택" value={selectedRegion?.county ?? ""} disabled={!overview} onChange={(event) => {
                const next = overview?.regions.find((region) => region.county === event.target.value);
                if (next) selectRegion(next.region_id);
              }}>{counties.map((county) => <option key={county} value={county}>{county}</option>)}</select></label>
              <label>읍면<select aria-label="읍면 선택" value={regionId} disabled={!overview} onChange={(event) => selectRegion(event.target.value)}>{towns.map((region) => <option key={region.region_id} value={region.region_id}>{region.town}</option>)}</select></label>
              <label>서비스 권역<select aria-label="서비스 권역 선택" value={selectedArea ?? "all"} disabled={!overview} onChange={(event) => setSelectedArea(event.target.value === "all" ? null : event.target.value)}><option value="all">전체 권역 보기</option>{(overview?.areas ?? []).map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}</select></label>
            </span>
          </div>
        </section>

        {error && !overview ? <ApiUnavailable error={error} retry={reload} /> : <>
          {error && overview && <div className="alert-box"><BadgeAlert size={15} /> 새 예산 결과를 가져오지 못해 직전 계산을 표시합니다. {error}</div>}
          {overview?.operations_attention && overview.operations_attention.length > 0 && (
            <section className="operations-attention-panel" aria-label="운영 주의 필요 항목">
              <div className="operations-attention-header">
                <div className="operations-attention-title">
                  <BadgeAlert size={18} />
                  <strong>운영 주의 필요 {overview.operations_attention.length}건</strong>
                  <span>지금 즉시 확인 또는 조치가 필요한 운영 항목입니다.</span>
                </div>
              </div>
              <ul className="operations-attention-list">
                {overview.operations_attention.map((item) => (
                  <li key={item.id} className="attention-item">
                    <div className="attention-item-info">
                      <strong className="attention-item-title">{item.title}</strong>
                      <p className="attention-item-desc">{item.description}</p>
                    </div>
                    <Link href={item.action_url} className="attention-action-btn">
                      {item.action_label} <ArrowRight size={13} />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section className="budget-panel" aria-labelledby="budget-heading">
            <div className="budget-head">
              <div className="budget-title-wrap">
                <span className="budget-symbol"><Coins size={19} /></span>
                <div><h2 id="budget-heading">가용 월 예산</h2><p>예산을 움직여 공급 범위와 미충족 지역을 확인하세요.</p></div>
              </div>
              <div className="budget-amount" aria-live="polite">{money(budget)}</div>
            </div>
            <div className="budget-control">
              <input
                aria-label="월간 가용 예산"
                type="range"
                min={3_000_000}
                max={7_000_000}
                step={100_000}
                value={budget}
                style={{ "--slider-progress": `${((budget - 3_000_000) / 4_000_000) * 100}%` } as React.CSSProperties}
                onChange={(event) => setBudget(Number(event.target.value))}
              />
              <div className="slider-limits"><span>3,000,000원</span><span>7,000,000원</span></div>
            </div>
            <div className="budget-foot"><span><SlidersHorizontal size={14} /> 100,000원 단위 조정</span><span>모든 금액은 월 기준입니다.</span></div>
          </section>

          <details className="policy-simulator-panel">
            <summary><span><SlidersHorizontal size={17} /> 정책 조건</span><small>값을 바꾸면 네 가지 시나리오를 다시 계산합니다.</small></summary>
            <p className="policy-choice-note">이 설정은 정책 선택이며 AI가 자동 결정한 가치판단이 아닙니다. 고령·조사 보호 가중치는 균형안 우선순위에, 최소 회차는 최소 서비스 보장안에 적용됩니다.</p>
            <div className="policy-control-grid">
              <label>권역별 최소 월 회차<select value={policy.minimum_services_per_area} onChange={(event) => setPolicyValue("minimum_services_per_area", Number(event.target.value))}>{[1, 2, 3, 4].map((count) => <option key={count} value={count}>{count}회</option>)}</select><small>최소 서비스 보장안 기준입니다.</small></label>
              <label>최대 허브 왕복 이동시간<select value={policy.maximum_round_trip_travel_minutes ?? ""} onChange={(event) => setPolicyValue("maximum_round_trip_travel_minutes", event.target.value ? Number(event.target.value) : null)}><option value="">제한 없음</option>{[30, 60, 90, 120, 180, 240].map((minutes) => <option key={minutes} value={minutes}>{minutes}분</option>)}</select><small>중앙 허브 왕복 도로시간을 기준으로 합니다.</small></label>
              <label>공급자 월 최소 보상 기준<input type="number" min={0} max={10_000_000} step={10_000} value={policy.minimum_provider_compensation_won} onChange={(event) => setPolicyValue("minimum_provider_compensation_won", Math.min(10_000_000, Math.max(0, Number(event.target.value) || 0)))} /><small>기존 공급자 기준보다 높을 때 적용하는 월 보상 하한입니다.</small></label>
              <fieldset className="policy-service-options"><legend>계획에 허용할 서비스</legend>{SERVICE_OPTIONS.map((service) => <label key={service}><input type="checkbox" checked={policy.allowed_services.includes(service)} onChange={(event) => setServiceAllowed(service, event.target.checked)} />{SERVICE_LABELS[service]}</label>)}</fieldset>
              <label className="policy-range-control">고령인구 우선 가중치 <output>{policy.elderly_priority_weight / 100}/10</output><input type="range" min={0} max={1000} step={100} value={policy.elderly_priority_weight} onChange={(event) => setPolicyValue("elderly_priority_weight", Number(event.target.value))} /></label>
              <label className="policy-range-control">고령 1인가구 우선 가중치 <output>{policy.single_elderly_household_priority_weight / 100}/10</output><input type="range" min={0} max={1000} step={100} value={policy.single_elderly_household_priority_weight} onChange={(event) => setPolicyValue("single_elderly_household_priority_weight", Number(event.target.value))} /></label>
              <label className="policy-range-control">조사 필요 권역 보호 가중치 <output>{policy.survey_required_protection_weight / 100}/10</output><input type="range" min={0} max={1000} step={100} value={policy.survey_required_protection_weight} onChange={(event) => setPolicyValue("survey_required_protection_weight", Number(event.target.value))} /></label>
            </div>
          </details>

          {overview && guarantee && chosenResult ? <>
            <section className="metrics-grid" aria-label="현재 시나리오 요약">
              <MetricCard icon={Check} label="서비스 충족률" value={`${Math.round(chosenResult.service_fulfillment_rate * 100)}%`} detail={`${number(chosenResult.served_units)} / ${number(chosenResult.total_demand_units)}회 제공`} />
              <MetricCard icon={MapPinned} label="서비스 권역" value={`${chosenResult.covered_villages}곳`} detail={`총 ${overview.areas.length}개 법정리 권역`} tone="blue" />
              <MetricCard icon={BadgeAlert} label="미충족 권역" value={`${chosenResult.uncovered_villages}곳`} detail="이번 달 서비스 배정 없음" tone="amber" />
              <MetricCard icon={CircleHelp} label="조사 필요 포함" value={`${selectedSurvey.covered}/${selectedSurvey.total}곳`} detail="관측이 적은 권역의 배정" tone="violet" />
            </section>

            <section className="scenario-panel">
              <div className="section-heading">
                <div><div className="eyebrow small">{SCENARIOS.length} PLANNING SCENARIOS</div><h2>어떤 기준으로 나눌까요?</h2></div>
                <div className="scenario-heading-actions"><button className="scenario-compare-toggle" aria-expanded={compareAllScenarios} onClick={() => setCompareAllScenarios((value) => !value)}>{compareAllScenarios ? "비교표 접기" : "4안 나란히 비교"}</button><Link href="/methodology" className="text-link">산정 기준 보기 <ArrowRight size={15} /></Link></div>
              </div>
              <div className="scenario-tabs" role="tablist" aria-label="계획 시나리오">
                {SCENARIOS.map((scenario) => (
                  <button
                    role="tab"
                    aria-selected={selected === scenario.id}
                    className={`scenario-tab ${selected === scenario.id ? "active" : ""} ${scenario.id === "minimum_coverage" ? "guarantee-tab" : ""}`}
                    key={scenario.id}
                    onClick={() => { setSelected(scenario.id); setSelectedArea(null); }}
                  >
                    <span className="scenario-tab-top"><small>{scenario.short}</small>{selected === scenario.id && <i><Check size={12} /></i>}</span>
                    <strong>{scenario.title}</strong>
                    <span>{scenario.note}</span>
                  </button>
                ))}
              </div>

              {compareAllScenarios && <section className="scenario-compare-grid" aria-label="네 가지 정책 시나리오 비교">
                {SCENARIOS.map((option) => {
                  const result = overview.scenario_results[option.id];
                  const surveyAreas = overview.areas.filter((area) => area.needs_survey).length;
                  const surveyCovered = result.assignments.filter((assignment) => assignment.needs_survey && assignment.covered).length;
                  return <article className={option.id === "minimum_coverage" ? "guarantee" : ""} key={option.id}>
                    <header><small>{option.short}</small><strong>{option.title}</strong><span>{option.note}</span></header>
                    <dl>
                      <div><dt>서비스 회차</dt><dd>{number(result.served_units)} / {number(result.total_demand_units)}</dd></div>
                      <div><dt>충족 권역</dt><dd>{result.covered_villages} / {overview.areas.length}</dd></div>
                      <div><dt>조사 필요 권역 포함</dt><dd>{surveyCovered} / {surveyAreas}</dd></div>
                      <div><dt>중앙 거점 왕복 환산 거리 · 시간</dt><dd>{distanceKm(result.travel_distance_m)} · {duration(result.travel_time_s)}</dd></div>
                      <div><dt>이동 비용</dt><dd>{money(result.travel_cost_won)}</dd></div>
                      <div><dt>최대 권역 배정/수요 비율</dt><dd>{percentFromBasisPoints(result.max_area_demand_saturation_basis_points)}</dd></div>
                      <div><dt>서비스 · 최소보상</dt><dd>{money(result.service_cost_won)} · {money(result.minimum_compensation_topup_won)}</dd></div>
                      <div><dt>총 사용액 · 잔액</dt><dd>{money(result.budget_spent_won)} · {money(result.budget_remaining_won)}</dd></div>
                      <div><dt>최소 기준 충족</dt><dd>{result.minimum_frequency_met_areas} / {overview.areas.length}권역</dd></div>
                      <div><dt>필요 추가 재원</dt><dd>{result.additional_budget_won === null ? "미산정" : money(result.additional_budget_won)}</dd></div>
                      <div><dt>전체 모의수요 필요예산 · 추가 재원</dt><dd>{fullDemandBudgetSummary(result)}</dd></div>
                    </dl>
                    <details className="scenario-provider-cost-details">
                      <summary>공급자별 비용 배분 ({result.provider_cost_breakdown.length}곳)</summary>
                      {result.provider_cost_breakdown.length > 0 ? <div className="scenario-provider-cost-scroll">
                        <table>
                          <thead><tr><th>공급자</th><th>회차</th><th>서비스비</th><th>이동 환산 거리·시간·비용</th><th>최소보상·지급·보전</th><th>총비용</th></tr></thead>
                          <tbody>{result.provider_cost_breakdown.map((provider) => <tr key={provider.provider_id}>
                            <th scope="row">{provider.provider_name}</th>
                            <td>{number(provider.service_rounds)}</td>
                            <td>{money(provider.service_cost_won)}</td>
                            <td>{distanceKm(provider.travel_distance_m)} · {duration(provider.travel_time_s)} · {money(provider.travel_cost_won)}</td>
                            <td>{money(provider.minimum_compensation_floor_won)} · {money(provider.compensation_paid_won)} · {money(provider.compensation_topup_won)}</td>
                            <td>{money(provider.total_cost_won)}</td>
                          </tr>)}</tbody>
                        </table>
                      </div> : <p>배정된 공급자가 없습니다.</p>}
                      <small>공급자명·운영 단가는 SIMULATED입니다. 이동 항목은 Kakao 도로 캐시의 중앙 거점 왕복 환산 배분이며, 다중 경유 일정은 서비스 일정에서 확인합니다. 모델: {result.provider_travel_model}</small>
                    </details>
                    <footer>같은 예산 {money(budget)} · {result.optimality_proven ? "최적성 증명 완료" : `실행 가능 · 최적성 미확정 (${result.solver_status})`}</footer>
                  </article>;
                })}
                <p className="scenario-compare-note">전체 모의수요 금액은 모의 공급자 월 용량·서비스 비용과 중앙 거점 왕복 이동비로 계산합니다. 날짜별 가용시간 및 공급자별 다중정차 경로는 반영하지 않습니다.</p>
              </section>}

              {compareAllScenarios && <section className="provider-scenario-compare" aria-label="공급자 일정 기준 시나리오 비교">
                <div className="provider-scenario-compare-heading">
                  <div><div className="eyebrow small">PROVIDER SCHEDULE CROSS-CHECK</div><h3>공급자·도로 일정으로 4안 검토</h3><p>위 월간 집계 비교와 별도로 각 시나리오의 향후 4주 공급자 배정, Kakao 도로경로, 시간·용량·비용 제약을 계산합니다.</p></div>
                  <button className="button button-dark" onClick={() => void generateProviderScenarioComparison()} disabled={generatingProviderScenarios}>
                    <CalendarDays size={15} /> {generatingProviderScenarios ? "공급 일정을 계산하고 있습니다" : "공급 일정 4안 생성"}
                  </button>
                </div>
                <p className="scenario-compare-note">공급자·가용성·가격은 SIMULATED 입력이며, 성공한 해도 실제 참여 확정이나 계약이 아닙니다. 세 일정은 순차 계산되고 각각 저장됩니다. 한 안의 계산이 실패해도 나머지 안은 계속 계산합니다.</p>
                {providerScenarioRun && <p className="provider-scenario-run-context">계산 조건: {providerScenarioRun.regionName} · 예산 {money(providerScenarioRun.budget)} · 최소 {providerScenarioRun.policy.minimum_services_per_area}회 · 허용 서비스 {providerScenarioRun.policy.allowed_services.length}종</p>}
                <p className="provider-scenario-progress" aria-live="polite">{providerScenarioStep ? `${SCENARIOS[providerScenarioStep.index].title} 공급 일정 계산 중 (${providerScenarioStep.index + 1}/${SCENARIOS.length})` : providerScenarioRun ? `${Object.keys(providerScenarioPlans).length}개 일정 저장 · ${Object.keys(providerScenarioErrors).length}개 계산 실패` : "생성 버튼을 눌러 공급자 제약을 적용한 시나리오별 일정을 계산합니다."}</p>
                <div className="provider-scenario-grid">
                  {SCENARIOS.map((option) => {
                    const plan = providerScenarioPlans[option.id];
                    const errorMessage = providerScenarioErrors[option.id];
                    const constraintReasons = plan ? scheduleConstraintSummary(plan) : [];
                    return <article className={option.id === "minimum_coverage" ? "guarantee" : ""} key={option.id}>
                      <header><small>{option.short}</small><strong>{option.title}</strong></header>
                      {plan ? <>
                        <dl>
                          <div><dt>배정 회차 · 서비스 단위</dt><dd>{number(plan.rounds.length)}회 · {number(plan.summary.served_units)}/{number(plan.summary.total_demand_units)}</dd></div>
                          <div><dt>충족 권역</dt><dd>{plan.summary.covered_areas}/{plan.summary.covered_areas + plan.summary.uncovered_areas}</dd></div>
                          <div><dt>Kakao 이동 거리 · 시간</dt><dd>{distanceKm(plan.summary.travel_distance_m)} · {duration(plan.summary.travel_time_s)}</dd></div>
                          <div><dt>서비스비 · 이동비 · 최소보상 보전</dt><dd>{money(plan.summary.service_cost_won)} · {money(plan.summary.travel_cost_won)} · {money(plan.summary.minimum_compensation_topup_won)}</dd></div>
                          <div><dt>총 비용 · 예산 잔액</dt><dd>{money(plan.summary.total_cost_won)} · {money(plan.summary.budget_remaining_won)}</dd></div>
                          <div><dt>최소 회차 충족</dt><dd>{plan.summary.minimum_frequency_met_areas}/{plan.summary.minimum_frequency_met_areas + plan.summary.unmet_minimum_frequency_areas} · 용량 부족 {plan.summary.missing_capacity}회</dd></div>
                          <div><dt>최소 기준 추가 예산</dt><dd>{plan.summary.required_budget_won === null ? `미산정 · ${plan.summary.required_budget_status}` : `${money(plan.summary.required_budget_won)} · 추가 ${money(plan.summary.budget_gap_won ?? 0)}`}</dd></div>
                        </dl>
                        {option.id === "balanced" && plan.summary.balanced_objective_weights && plan.summary.balanced_objective_policy_weights && <p className="provider-scenario-proof">균형 점수 기본 비중: 회차 {plan.summary.balanced_objective_weights.service_volume} · 권역 {plan.summary.balanced_objective_weights.area_coverage} · 조사 {plan.summary.balanced_objective_weights.survey_protection} · 취약 {plan.summary.balanced_objective_weights.vulnerability} · 집중도 {plan.summary.balanced_objective_weights.concentration} · 이동비 {plan.summary.balanced_objective_weights.travel_cost}. 저장된 정책 입력: 조사 {plan.summary.balanced_objective_policy_weights.survey_required_protection_weight}/1000 · 고령 {plan.summary.balanced_objective_policy_weights.elderly_priority_weight}/1000 · 고령 1인가구 {plan.summary.balanced_objective_policy_weights.single_elderly_household_priority_weight}/1000.</p>}
                        {constraintReasons.length > 0 && <p className="provider-scenario-reasons">미충족 진단: {constraintReasons.join(" · ")}</p>}
                        <p className="provider-scenario-proof">{plan.summary.optimality_proven ? "해당 일정 모델의 목적 최적성 증명" : `실행 가능 일정 · 목적 최적성 미확정 (${plan.summary.solver_status})`} · {plan.summary.global_route_optimality_proven ? "경로 모델 최적성 증명" : "경로 전역 최적성 미확정"}</p>
                        <Link className="provider-scenario-open" href={`/calendar?schedule_id=${encodeURIComponent(plan.schedule_id)}`}>저장된 일정 상세 보기 <ArrowRight size={14} /></Link>
                      </> : errorMessage ? <p className="provider-scenario-error" role="status">계산하지 못함: {errorMessage}</p> : <p className="provider-scenario-pending">{providerScenarioStep?.scenario === option.id ? "계산 중…" : "아직 계산되지 않음"}</p>}
                    </article>;
                  })}
                </div>
              </section>}

              <div className={`guarantee-callout ${guarantee.minimum_coverage_met ? "met" : "gap"}`}>
                <div className="guarantee-icon">{guarantee.minimum_coverage_met ? <Check size={18} /> : <CircleHelp size={18} />}</div>
                <div className="guarantee-message">
                  <strong>{guarantee.minimum_coverage_met
                    ? `월간 집계 모델에서 월 ${guarantee.minimum_services_per_area ?? policy.minimum_services_per_area}회 최소 기준을 충족하는 배정입니다.`
                    : guarantee.guarantee_feasible === false
                      ? `월간 집계 모델에서도 월 ${guarantee.minimum_services_per_area ?? policy.minimum_services_per_area}회 기준을 보장할 수 없습니다: ${GUARANTEE_FAILURE_LABELS[guarantee.guarantee_failure_reason ?? ""] ?? "정책·수요·공급 조건을 확인해 주세요"}.`
                      : `월간 집계 모델에서 월 ${guarantee.minimum_services_per_area ?? policy.minimum_services_per_area}회 기준을 달성하려면 ${money(guarantee.additional_budget_won ?? 0)}이 더 필요합니다.`}</strong>
                  <span>필요예산 {guarantee.required_budget_won === null ? "현재 정책·수요·공급 조건으로 산정 불가" : money(guarantee.required_budget_won)} · 현재 {money(budget)} · 최소 기준 충족 {guarantee.minimum_frequency_met_areas}/{overview.areas.length}개 권역 · 필요 용량 {guarantee.required_capacity ?? "—"}회 / 공급자 월 용량 상한 {guarantee.available_capacity ?? "—"}회 / 서비스 조합 적격 {guarantee.minimum_compatible_capacity ?? "—"}회 / 부족 {guarantee.missing_capacity ?? "—"}회</span>
                  <span className="guarantee-scope-note">월 용량과 중앙 거점 왕복 이동비를 쓰는 집계 추정입니다. 날짜별 공급자 가용시간·하루 근무시간·다중정차 경로까지 충족하는 일정임을 증명하지 않습니다. <Link href="/calendar">공급 일정에서 날짜별 가능 여부 확인</Link></span>
                </div>
                <div className="guarantee-gap"><small>{guarantee.guarantee_feasible === false ? "미충족 원인" : "추가 필요 예산"}</small><b>{guarantee.guarantee_feasible === false ? GUARANTEE_FAILURE_LABELS[guarantee.guarantee_failure_reason ?? ""] ?? "확인 필요" : guarantee.additional_budget_won === null ? "—" : money(guarantee.additional_budget_won)}</b></div>
              </div>

              {selected === "balanced" && <>
                <div className="balanced-note"><CircleHelp size={16} /><span>먼저 같은 예산에서 가능한 월간 회차를 확보하고, 서비스 권역 수 → 조사 필요 권역 → 고령 인구·고령 1인세대 → 권역별 배정 집중도 → 이동비 순으로 비교합니다. 공공 인구통계는 모의 수요를 실측 수요로 바꾸지 않습니다.</span></div>
                <div className="balanced-tradeoff">가장 많이 배정된 권역의 모의 수요 대비 비율 {percentFromBasisPoints(chosenResult.max_area_demand_saturation_basis_points)} · 낮을수록 권역별 배정 비율이 고르게 분산된 결과입니다.</div>
                <div className="scenario-evidence" aria-label="요청 기록 우선과 균형안 비교">
                  <strong>요청 기록만 우선하면</strong>
                  <span>{overview.request_count_baseline.survey_required_covered}/{overview.request_count_baseline.survey_required_areas} 조사 필요 권역 포함</span>
                  <i aria-hidden="true">→</i>
                  <strong>균형안</strong>
                  <span>{selectedSurvey.covered}/{selectedSurvey.total} 포함</span>
                  <small>{money(budget)} 기준 · 모의 관측 자료</small>
                </div>
                <div className="balanced-tradeoff">같은 예산에서 효율 우선 대비 월간 회차 {signedNumber(chosenResult.served_units - overview.scenario_results.efficiency.served_units)}회 · 서비스 권역 {signedNumber(chosenResult.covered_villages - overview.scenario_results.efficiency.covered_villages)}곳 · 도로 이동비 {signedMoney(chosenResult.travel_cost_won - overview.scenario_results.efficiency.travel_cost_won)}</div>
              </>}

              <ScenarioMetrics result={chosenResult} surveyCovered={selectedSurvey.covered} surveyCount={selectedSurvey.total} areaCount={overview.areas.length} />
              <div className="planner-layout">
                <section className="map-card" aria-labelledby="coverage-map-heading">
                  <div className="card-heading">
                    <div><h3 id="coverage-map-heading">마을별 서비스 계획</h3><p>마을을 선택하면 근거와 필요한 조사를 확인합니다.</p></div>
                    <span className="area-count">{overview.areas.length}개 권역</span>
                  </div>
                  <details className="map-area-alternative">
                    <summary>마을별 배정 표로 보기</summary>
                    <div className="table-wrap">
                      <table className="data-table" aria-label="지도 대체 마을별 서비스 배정">
                        <caption className="sr-only">현재 시나리오의 권역별 서비스 배정과 조사 상태</caption>
                        <thead>
                          <tr>
                            <th scope="col">마을</th>
                            <th scope="col">서비스 배정</th>
                            <th scope="col">모의 월 회차</th>
                            <th scope="col">조사 상태</th>
                            <th scope="col">미배정 이유</th>
                            <th scope="col">상세</th>
                          </tr>
                        </thead>
                        <tbody>
                          {overview.areas.map((area) => {
                            const assignment = chosenResult.assignments.find((row) => row.area_id === area.id);
                            return (
                              <tr key={area.id}>
                                <th scope="row">{area.name}</th>
                                <td>{assignment?.covered ? "서비스 배정" : "현재 계획에서 서비스 미배정"}</td>
                                <td>{assignment ? `${assignment.served_units} / ${assignment.demand_units}` : "계산 중"}</td>
                                <td>{area.needs_survey ? "조사 필요" : "추가 조사 기준 미충족"}</td>
                                <td>{!assignment?.covered && assignment?.constraint_reason ? CONSTRAINT_REASON_LABELS[assignment.constraint_reason] ?? "조건 확인 필요" : "-"}</td>
                                <td><Link className="text-link" href={`/villages/${area.id}`}>권역 상세</Link></td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </details>
                  <CoverageMap areas={overview.areas} result={chosenResult} activeArea={selectedArea} onSelect={setSelectedArea} />
                  {selectedAreaInfo && selectedAssignment && <div className="area-popover" role="region" aria-label={`${selectedAreaInfo.name} 상세`}>
                    <button className="popover-close" onClick={() => setSelectedArea(null)} aria-label="상세 닫기">×</button>
                    <div className="popover-title"><strong>{selectedAreaInfo.name}</strong><span className={selectedAreaInfo.needs_survey ? "text-amber" : "text-green"}>{selectedAreaInfo.needs_survey ? "조사 필요 · 모의 기록 부족" : selectedAssignment.status}</span></div>
                    <div className="popover-metrics"><span>모의 요청 기록 <b>{selectedAreaInfo.demand_observation_count}건</b></span><span>월간 서비스 회차 <b>{selectedAssignment.served_units}/{selectedAssignment.demand_units}회</b></span><span>65세 이상 <b>{((selectedAreaInfo.elderly_ratio_65 || 0) * 100).toFixed(1)}%</b></span></div>
                    {!selectedAssignment.covered && selectedAssignment.constraint_reason && <p className="area-constraint-reason">미충족 원인: {CONSTRAINT_REASON_LABELS[selectedAssignment.constraint_reason] ?? "조건 확인 필요"}</p>}
                    <Link href={`/villages/${selectedAreaInfo.id}`} className="text-link">권역 근거와 조사 항목 보기 <ArrowRight size={14} /></Link>
                  </div>}
                  <div className="map-source-note"><span className="provenance-badge real">REAL PUBLIC DATA</span> 법정동·인구·고령인구·1인가구·시설 위치·Kakao 도로 거리/시간<br /><span className="provenance-badge simulated">SIMULATED</span> 주민 요청·서비스 필요량·제공자 일정/용량·가격·운영 조건</div>
                </section>
                <aside className="coverage-side">
                  <div className="side-card comparison-card">
                    <div className="card-heading"><div><h3>예산 사용</h3><p>운영비와 이동비를 함께 반영</p></div><Coins size={17} /></div>
                    <div className="budget-total"><strong>{money(chosenResult.budget_spent_won)}</strong><span>사용</span></div>
                    <div className="budget-meter"><i style={{ width: `${Math.min(100, chosenResult.budget_spent_won / Math.max(budget, 1) * 100)}%` }} /></div>
                    <div className="meter-labels"><span>잔액</span><strong>{money(chosenResult.budget_remaining_won)}</strong></div>
                    <div className="cost-breakdown"><span>서비스 비용</span><b>{money(chosenResult.service_cost_won)}</b></div>
                    <div className="cost-breakdown"><span>최소 보상 보전 (총비용 포함)</span><b>{money(chosenResult.minimum_compensation_topup_won)}</b></div>
                    <div className="cost-breakdown"><span>도로 이동비</span><b>{money(chosenResult.travel_cost_won)}</b></div>
                    <div className="cost-breakdown" title="최소 보상 기준은 서비스 원가보다 부족할 때 보전액으로 총비용에 반영됩니다."><span>참여 공급자 최소 보상 하한</span><b>{money(chosenResult.provider_minimum_compensation_won)}</b></div>
                    {chosenResult.scenario === "minimum_coverage" && <div className="cost-breakdown"><span>최소서비스 보장 추가 재원</span><b>{chosenResult.additional_public_subsidy_won === null ? "산정 불가" : money(chosenResult.additional_public_subsidy_won)}</b></div>}
                    <div className="cost-breakdown"><span>전체 모의수요 충족 필요예산</span><b>{chosenResult.full_demand_budget_status === "CALCULATED" && chosenResult.full_demand_required_budget_won !== null ? money(chosenResult.full_demand_required_budget_won) : "산정 불가"}</b></div>
                    <div className="cost-breakdown"><span>전체수요 추가 공공재원</span><b>{chosenResult.full_demand_budget_status === "CALCULATED" && chosenResult.full_demand_budget_gap_won !== null ? money(chosenResult.full_demand_budget_gap_won) : FULL_DEMAND_FUNDING_LABELS[chosenResult.full_demand_failure_reason ?? ""] ?? "조건 확인 필요"}</b></div>
                    <small className="cost-breakdown-note">전체수요 기준은 모의 공급자 용량·서비스 비용과 중앙 거점 왕복 이동비의 aggregate estimate입니다. 날짜별 가용시간·하루 근무시간·공급자별 다중정차 경로는 일정 생성에서 따로 계산합니다.</small>
                  </div>
                  <div className="side-card lowdata-card">
                    <div className="lowdata-header"><span className="lowdata-icon">?</span><div><strong>조사 필요 권역</strong><small>낮은 관측 수는 수요 0의 근거가 아닙니다</small></div><span className="lowdata-count">{overview.areas.filter((area) => area.needs_survey).length}<small>곳</small></span></div>
                    <div className="lowdata-list">
                      {overview.areas.filter((area) => area.needs_survey).slice(0, 3).map((area) => (
                        <Link href={`/villages/${area.id}`} key={area.id} className="lowdata-row">
                          <span>{area.name}</span><small>모의 기록 {area.demand_observation_count}건</small><ArrowRight size={13} />
                        </Link>
                      ))}
                    </div>
                    <Link href="/data-quality" className="lowdata-foot">데이터 품질 전체 보기 <ArrowRight size={13} /></Link>
                  </div>
                </aside>
              </div>

              <div className="simulation-banner">
                <span className="simulation-banner-icon"><CircleHelp size={17} /></span>
                <p><b>실제 공개자료</b> 법정동·인구·고령인구·1인가구·마을회관/경로당 위치·Kakao 도로 거리/시간 <span className="provenance-badge real">REAL PUBLIC DATA</span><br /><b>시연용 모의값</b> 주민 요청·서비스 필요량·제공자 일정/용량·가격·운영 조건 <span className="provenance-badge simulated">시연용 시뮬레이션</span></p>
                <Link href="/data-quality">출처 확인 <ArrowRight size={14} /></Link>
              </div>
            </section>
          </> : <div className="loading-card"><span className="spinner" />{error || (loading ? "최적화 시나리오 계산 중…" : "데이터를 확인하고 있습니다.")}</div>}
        </>}
        <footer className="page-footer"><span>VillageCoverage · 의사결정을 돕는 Pre-R&amp;D 시제품</span><span>이 결과는 행정 결정을 대신하지 않습니다.</span></footer>
      </div>
      {loading && overview && <div className="refresh-pill"><span className="spinner small" /> 예산 시나리오 갱신 중</div>}
    </main>
  );
}
