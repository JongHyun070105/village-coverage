"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, BadgeAlert, Check, ChevronDown, CircleHelp, Clock3, Coins, MapPinned, RefreshCw, SlidersHorizontal, UsersRound, type LucideIcon } from "lucide-react";
import { CoverageMap } from "@/components/coverage-map";
import { apiBase, fetchOverview } from "@/lib/api";
import type { Overview, ScenarioKey, ScenarioResult } from "@/lib/types";

const SCENARIOS: Array<{ id: ScenarioKey; title: string; short: string; note: string }> = [
  { id: "efficiency", title: "효율 우선", short: "EFFICIENT", note: "같은 예산으로 서비스 횟수를 늘립니다." },
  { id: "balanced", title: "균형", short: "BALANCED", note: "고령인구와 저데이터 조사 필요를 함께 고려합니다." },
  { id: "minimum_coverage", title: "최소보장", short: "GUARANTEE", note: "모든 권역에 월 1회 제공 비용과 부족분을 계산합니다." },
];

const money = (amount: number) => `${Math.round(amount).toLocaleString("ko-KR")}원`;
const number = (amount: number) => amount.toLocaleString("ko-KR");
const signedNumber = (amount: number) => `${amount > 0 ? "+" : ""}${number(amount)}`;
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

function ScenarioMetrics({ result }: { result: ScenarioResult }) {
  return (
    <div className="scenario-stats">
      <div><span>월간 서비스 충족</span><strong>{Math.round(result.service_fulfillment_rate * 100)}<small>%</small></strong></div>
      <div><span>서비스 권역</span><strong>{result.covered_villages}<small> / 16곳</small></strong></div>
      <div><span>예상 수혜</span><strong>{number(result.beneficiaries)}<small>명</small></strong></div>
      <div><span>예상 이동</span><strong>{duration(result.travel_time_s)}</strong></div>
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
        const data = await fetchOverview(budget);
        if (current) setOverview(data);
      } catch (cause) {
        if (current) setError(cause instanceof Error ? cause.message : "API 연결을 확인해 주세요.");
      } finally {
        if (current) setLoading(false);
      }
    }, 120);
    return () => { current = false; window.clearTimeout(timer); };
  }, [budget, refreshToken]);

  const chosenResult = overview?.scenario_results[selected];
  const guarantee = overview?.scenario_results.minimum_coverage;
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
            <p className="welcome-copy">기록이 적은 마을을 수요 0으로 보지 않고, 형평성을 달성하는 비용을 투명하게 비교합니다.</p>
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

          {overview && guarantee && chosenResult ? <>
            <section className="metrics-grid" aria-label="현재 시나리오 요약">
              <MetricCard icon={Check} label="서비스 충족률" value={`${Math.round(chosenResult.service_fulfillment_rate * 100)}%`} detail={`${number(chosenResult.served_units)} / ${number(chosenResult.total_demand_units)}회 제공`} />
              <MetricCard icon={MapPinned} label="미충족 마을" value={`${chosenResult.uncovered_villages}곳`} detail={`총 ${overview.areas.length}개 법정리 권역`} tone="amber" />
              <MetricCard icon={Clock3} label="예상 도로 이동" value={duration(chosenResult.travel_time_s)} detail={`이동비 ${money(chosenResult.travel_cost_won)}`} tone="blue" />
              <MetricCard icon={UsersRound} label="예상 수혜 인원" value={`${number(chosenResult.beneficiaries)}명`} detail="서비스 횟수 × 모의 수혜 인원" tone="violet" />
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

              {selected === "minimum_coverage" && <div className={`guarantee-callout ${guarantee.minimum_coverage_met ? "met" : "gap"}`}>
                <div className="guarantee-icon">{guarantee.minimum_coverage_met ? <Check size={18} /> : <CircleHelp size={18} />}</div>
                <div className="guarantee-message">
                  <strong>{guarantee.minimum_coverage_met
                    ? "모든 마을에 월 1회 최소 서비스를 제공할 수 있습니다."
                    : guarantee.guarantee_capacity_feasible === false
                      ? "현재 모의 공급자 용량으로는 모든 마을을 보장할 수 없습니다. 예산 증액만으로 해결되지 않습니다."
                      : `모든 마을에 월 1회 최소 서비스를 제공하려면 ${money(guarantee.additional_budget_won ?? 0)}이 더 필요합니다.`}</strong>
                  <span>최소보장 필요 예산 {guarantee.required_budget_won === null ? "용량 부족으로 산정 불가" : money(guarantee.required_budget_won)} · 현재 예산 {money(budget)} · {guarantee.covered_villages}/{overview.areas.length}개 권역 제공 · 모의 수혜 추정은 효율 우선 대비 {signedNumber(guarantee.beneficiaries_added_vs_efficiency ?? 0)}명</span>
                </div>
                <div className="guarantee-gap"><small>{guarantee.guarantee_capacity_feasible === false ? "모의 공급 용량" : "추가 필요 예산"}</small><b>{guarantee.additional_budget_won === null ? "—" : money(guarantee.additional_budget_won)}</b></div>
              </div>}

              {selected === "balanced" && <div className="balanced-note"><CircleHelp size={16} /><span>관측이 적은 지역도 공공 인구자료의 고령 비율을 참고해 보호합니다. <b>기록이 적다는 이유만으로 수요를 낮추지 않습니다.</b></span></div>}

              <ScenarioMetrics result={chosenResult} />
              <div className="planner-layout">
                <section className="map-card" aria-labelledby="coverage-map-heading">
                  <div className="card-heading">
                    <div><h3 id="coverage-map-heading">마을별 서비스 계획</h3><p>마을을 선택하면 근거와 필요한 조사를 확인합니다.</p></div>
                    <span className="area-count">{overview.areas.length}개 권역</span>
                  </div>
                  <CoverageMap areas={overview.areas} result={chosenResult} activeArea={selectedArea} onSelect={setSelectedArea} />
                  {selectedAreaInfo && selectedAssignment && <div className="area-popover" role="region" aria-label={`${selectedAreaInfo.name} 상세`}>
                    <button className="popover-close" onClick={() => setSelectedArea(null)} aria-label="상세 닫기">×</button>
                    <div className="popover-title"><strong>{selectedAreaInfo.name}</strong><span className={selectedAreaInfo.needs_survey ? "text-amber" : "text-green"}>{selectedAreaInfo.needs_survey ? "데이터 부족 · 조사 필요" : selectedAssignment.status}</span></div>
                    <div className="popover-metrics"><span>관측 <b>{selectedAreaInfo.demand_observation_count}건</b></span><span>월 제공 <b>{selectedAssignment.served_units}/{selectedAssignment.demand_units}회</b></span><span>65세 이상 <b>{((selectedAreaInfo.elderly_ratio_65 || 0) * 100).toFixed(1)}%</b></span></div>
                    <Link href={`/villages/${selectedAreaInfo.id}`} className="text-link">권역 근거와 조사 항목 보기 <ArrowRight size={14} /></Link>
                  </div>}
                  <div className="map-source-note">좌표: 경로당·마을회관 · 도로 이동: Kakao Mobility 캐시 · 운영 수요: 시뮬레이션</div>
                </section>
                <aside className="coverage-side">
                  <div className="side-card comparison-card">
                    <div className="card-heading"><div><h3>예산 사용</h3><p>운영비와 이동비를 함께 반영</p></div><Coins size={17} /></div>
                    <div className="budget-total"><strong>{money(chosenResult.budget_spent_won)}</strong><span>사용</span></div>
                    <div className="budget-meter"><i style={{ width: `${Math.min(100, chosenResult.budget_spent_won / Math.max(budget, 1) * 100)}%` }} /></div>
                    <div className="meter-labels"><span>잔액</span><strong>{money(chosenResult.budget_remaining_won)}</strong></div>
                    <div className="cost-breakdown"><span>서비스 공급가</span><b>{money(chosenResult.budget_spent_won - chosenResult.travel_cost_won)}</b></div>
                    <div className="cost-breakdown"><span>도로 이동비</span><b>{money(chosenResult.travel_cost_won)}</b></div>
                  </div>
                  <div className="side-card lowdata-card">
                    <div className="lowdata-header"><span className="lowdata-icon">?</span><div><strong>관측 부족 마을</strong><small>수요 없음으로 단정하지 않습니다</small></div><span className="lowdata-count">{overview.areas.filter((area) => area.needs_survey).length}<small>곳</small></span></div>
                    <div className="lowdata-list">
                      {overview.areas.filter((area) => area.needs_survey).slice(0, 3).map((area) => (
                        <Link href={`/villages/${area.id}`} key={area.id} className="lowdata-row">
                          <span>{area.name}</span><small>기록 {area.demand_observation_count}건</small><ArrowRight size={13} />
                        </Link>
                      ))}
                    </div>
                    <Link href="/data-quality" className="lowdata-foot">데이터 품질 전체 보기 <ArrowRight size={13} /></Link>
                  </div>
                </aside>
              </div>

              <div className="simulation-banner">
                <span className="simulation-banner-icon"><CircleHelp size={17} /></span>
                <p><b>데이터를 구분해 해석해 주세요.</b> 인구·1인가구·시설 위치는 REAL PUBLIC DATA입니다. 서비스 수요·운영 용량·서비스 단가는 <strong>SIMULATED FOR PRE-R&amp;D</strong>입니다.</p>
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
