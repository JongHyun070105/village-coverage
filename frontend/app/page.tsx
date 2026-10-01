"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, BadgeAlert, Check, ChevronDown, CircleHelp, Coins, MapPinned, RefreshCw, SlidersHorizontal, type LucideIcon } from "lucide-react";
import { CoverageMap } from "@/components/coverage-map";
import { apiBase, fetchOverview } from "@/lib/api";
import type { Overview, PlanningPolicy, ScenarioKey, ScenarioResult, SurveyServiceType } from "@/lib/types";

const SCENARIOS: Array<{ id: ScenarioKey; title: string; short: string; note: string }> = [
  { id: "efficiency", title: "효율 우선", short: "EFFICIENT", note: "같은 예산으로 서비스 횟수를 늘립니다." },
  { id: "balanced", title: "균형", short: "BALANCED", note: "고령인구와 조사 필요 권역을 함께 고려합니다." },
  { id: "minimum_coverage", title: "최소 서비스 보장", short: "GUARANTEE", note: "각 권역 최소 회차와 필요한 예산을 보여줍니다." },
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
const CONSTRAINT_REASON_LABELS: Record<string, string> = {
  SERVICE_NOT_ALLOWED: "정책에서 허용하지 않은 서비스",
  MAX_TRAVEL_TIME: "최대 허브 왕복 이동시간 초과",
  NO_SUPPORTED_PROVIDER: "해당 서비스를 제공할 공급자 없음",
  MINIMUM_FREQUENCY: "설정한 최소 회차 미충족",
  BUDGET_OR_CAPACITY: "예산 또는 공급 용량 부족",
};

const money = (amount: number) => `${Math.round(amount).toLocaleString("ko-KR")}원`;
const number = (amount: number) => amount.toLocaleString("ko-KR");
const signedNumber = (amount: number) => `${amount > 0 ? "+" : ""}${number(amount)}`;
const signedMoney = (amount: number) => `${amount > 0 ? "+" : amount < 0 ? "−" : ""}${money(Math.abs(amount))}`;
const duration = (seconds: number) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return hours ? `${hours}시간 ${minutes}분` : `${minutes}분`;
};

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
  const [selected, setSelected] = useState<ScenarioKey>("balanced");
  const [selectedArea, setSelectedArea] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const reload = useCallback(() => setRefreshToken((value) => value + 1), []);

  useEffect(() => {
    let current = true;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const data = await fetchOverview(budget, policy);
        if (current) setOverview(data);
      } catch (cause) {
        if (current) setError(cause instanceof Error ? cause.message : "API 연결을 확인해 주세요.");
      } finally {
        if (current) setLoading(false);
      }
    }, 120);
    return () => { current = false; window.clearTimeout(timer); };
  }, [budget, policy, refreshToken]);

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

  return (
    <main className="page-main dashboard-page">
      <header className="topbar">
        <div className="breadcrumb"><span>정책 설계</span><span className="breadcrumb-sep">/</span><strong>공급계획 시뮬레이터</strong></div>
        <div className="topbar-right"><span className="pre-rnd-pill"><i /> PRE-R&amp;D 검증</span><span className="avatar">VC</span></div>
      </header>
      <div className="dashboard-content">
        <section className="welcome-row">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> 농촌 생활서비스 공급계획 시뮬레이터</div>
            <h1>제한된 예산으로,<br className="mobile-break" /> 어디까지 함께할 수 있을까요?</h1>
            <p className="welcome-copy">기록이 적다고 필요가 없다고 판단하지 않습니다. 예산에 따른 서비스 범위를 비교합니다.</p>
          </div>
          <div className="region-selector" aria-label="데모 지역 홍성군 장곡면">
            <span className="region-icon"><MapPinned size={17} /></span>
            <span><small>DEMO REGION</small><strong>홍성군 장곡면</strong></span>
            <ChevronDown size={16} />
          </div>
        </section>

        {error && !overview ? <ApiUnavailable error={error} retry={reload} /> : <>
          {error && overview && <div className="alert-box"><BadgeAlert size={15} /> 새 예산 결과를 가져오지 못해 직전 계산을 표시합니다. {error}</div>}
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
            <summary><span><SlidersHorizontal size={17} /> 정책 조건</span><small>값을 바꾸면 세 가지 시나리오를 다시 계산합니다.</small></summary>
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
                <div><div className="eyebrow small">3 PLANNING SCENARIOS</div><h2>어떤 기준으로 나눌까요?</h2></div>
                <Link href="/methodology" className="text-link">산정 기준 보기 <ArrowRight size={15} /></Link>
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

              <div className={`guarantee-callout ${guarantee.minimum_coverage_met ? "met" : "gap"}`}>
                <div className="guarantee-icon">{guarantee.minimum_coverage_met ? <Check size={18} /> : <CircleHelp size={18} />}</div>
                <div className="guarantee-message">
                  <strong>{guarantee.minimum_coverage_met
                    ? `모든 마을에 월 ${guarantee.minimum_services_per_area ?? policy.minimum_services_per_area}회 최소 서비스를 제공할 수 있습니다.`
                    : guarantee.guarantee_feasible === false
                      ? `월 ${guarantee.minimum_services_per_area ?? policy.minimum_services_per_area}회 기준을 보장할 수 없습니다: ${GUARANTEE_FAILURE_LABELS[guarantee.guarantee_failure_reason ?? ""] ?? "정책·수요·공급 조건을 확인해 주세요"}.`
                      : `모든 마을에 월 ${guarantee.minimum_services_per_area ?? policy.minimum_services_per_area}회 최소 서비스를 제공하려면 ${money(guarantee.additional_budget_won ?? 0)}이 더 필요합니다.`}</strong>
                  <span>필요예산 {guarantee.required_budget_won === null ? "현재 정책·수요·공급 조건으로 산정 불가" : money(guarantee.required_budget_won)} · 현재 {money(budget)} · 최소 기준 충족 {guarantee.minimum_frequency_met_areas}/{overview.areas.length}개 권역 · 필요 용량 {guarantee.required_capacity ?? "—"}회 / 가용 {guarantee.available_capacity ?? "—"}회 / 부족 {guarantee.missing_capacity ?? "—"}회</span>
                </div>
                <div className="guarantee-gap"><small>{guarantee.guarantee_feasible === false ? "미충족 원인" : "추가 필요 예산"}</small><b>{guarantee.guarantee_feasible === false ? GUARANTEE_FAILURE_LABELS[guarantee.guarantee_failure_reason ?? ""] ?? "확인 필요" : guarantee.additional_budget_won === null ? "—" : money(guarantee.additional_budget_won)}</b></div>
              </div>

              {selected === "balanced" && <>
                <div className="balanced-note"><CircleHelp size={16} /><span>먼저 같은 예산에서 가능한 월간 회차를 확보하고, 서비스 권역 수 → 조사 필요 권역 → 고령 인구·고령 1인세대 → 권역별 배정 집중도 → 이동비 순으로 비교합니다. 공공 인구통계는 모의 수요를 실측 수요로 바꾸지 않습니다.</span></div>
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
                    <small className="cost-breakdown-note">추가 공공재원 {chosenResult.additional_public_subsidy_won === null ? "미산정" : money(chosenResult.additional_public_subsidy_won)}{chosenResult.additional_public_subsidy_won === null ? " — 이 시나리오의 전체 수요 충족 재원은 산정하지 않았습니다." : " — 최소서비스 기준 예산 gap"}</small>
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
                <p><b>실제 공개자료</b> 법정동·인구·고령인구·1인가구·마을회관/경로당 위치·Kakao 도로 거리/시간 <span className="provenance-badge real">REAL PUBLIC DATA</span><br /><b>사전 연구용 모의값</b> 주민 요청·서비스 필요량·제공자 일정/용량·가격·운영 조건 <span className="provenance-badge simulated">SIMULATED FOR PRE-R&amp;D</span></p>
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
