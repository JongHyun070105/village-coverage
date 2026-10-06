"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ArrowRightLeft, Coins, Play, Scale } from "lucide-react";
import { ApiErrorNotice } from "@/components/api-error";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { SolverStatus } from "@/components/solver-status";
import { createSchedulePlan, fetchRegions, readSelectedRegionId, saveSelectedRegionId } from "@/lib/api";
import { count, won } from "@/lib/format";
import UnderservedComparisonPanel from "@/components/underserved-comparison-panel";
import ProviderResiliencePanel from "@/components/provider-resilience-panel";
import type { PlanningPolicy, RegionOption, ScenarioKey, SchedulePlan } from "@/lib/types";
import {
  analyzeMinimumCoverage,
  fetchAreasV4,
  fetchPlanExplanations,
  fetchPolicyPresets,
  type AreaExplanation,
  type AreaV4,
  type MinimumCoverageComparison,
  type PolicyPreset,
} from "@/lib/v4";

const SCENARIOS: Array<{ id: ScenarioKey; title: string; focus: string }> = [
  { id: "efficiency", title: "효율 중심", focus: "같은 예산으로 서비스 회차를 최대화" },
  { id: "balanced", title: "균형", focus: "회차·권역 분산·조사필요·취약 가중을 함께 고려" },
  { id: "minimum_coverage", title: "최소보장", focus: "모든 권역 최소 회차를 우선" },
  { id: "underserved_first", title: "소외 최소화", focus: "서비스 공백이 긴 권역을 우선" },
];
const DEFAULT_POLICY: PlanningPolicy = {
  minimum_services_per_area: 1,
  elderly_priority_weight: 500,
  single_elderly_household_priority_weight: 500,
  survey_required_protection_weight: 1000,
  maximum_round_trip_travel_minutes: null,
  allowed_services: ["laundry", "daily_necessities", "home_repair"],
  minimum_provider_compensation_won: 0,
};

type CardResult = { plan: SchedulePlan; explanations: AreaExplanation[] };
type Snapshot = { presetLabel: string; plan: SchedulePlan; vulnerableCovered: number; surveyCovered: number };

const minutes = (seconds: number) => `${Math.round(seconds / 60).toLocaleString("ko-KR")}분`;
const signed = (value: number, unit = "") => `${value > 0 ? "+" : value < 0 ? "−" : "±"}${Math.abs(value).toLocaleString("ko-KR")}${unit}`;

export default function ScenarioComparePage() {
  const [regions, setRegions] = useState<RegionOption[]>([]);
  const [regionId, setRegionId] = useState<string>(() => readSelectedRegionId());
  const [budget, setBudget] = useState(4_000_000);
  const [presets, setPresets] = useState<PolicyPreset[]>([]);
  const [presetNotice, setPresetNotice] = useState("");
  const [presetId, setPresetId] = useState("balanced");
  const [areas, setAreas] = useState<AreaV4[]>([]);
  const [results, setResults] = useState<Partial<Record<ScenarioKey, CardResult>>>({});
  const [minimum, setMinimum] = useState<MinimumCoverageComparison | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [previous, setPrevious] = useState<Snapshot | null>(null);
  const [current, setCurrent] = useState<Snapshot | null>(null);
  const [focusTarget, setFocusTarget] = useState<"error" | "results" | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const resultsHeadingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    fetchRegions().then((body) => setRegions(body.regions)).catch(setError);
    fetchPolicyPresets().then((body) => { setPresets(body.presets); setPresetNotice(body.notice); }).catch(setError);
  }, []);
  useEffect(() => { fetchAreasV4(regionId).then((body) => setAreas(body.areas)).catch(setError); }, [regionId]);

  useEffect(() => {
    if (focusTarget === "error") errorRef.current?.focus();
    if (focusTarget === "results") resultsHeadingRef.current?.focus();
  }, [focusTarget, error, results, minimum]);

  const preset = presets.find((item) => item.preset_id === presetId);
  const policy: PlanningPolicy = useMemo(() => ({ ...DEFAULT_POLICY, ...(preset?.policy ?? {}) }), [preset]);
  const vulnerableIds = useMemo(() => {
    const values = areas.map((a) => a.single_households_65_plus ?? 0).sort((x, y) => x - y);
    const median = values[Math.floor(values.length / 2)] ?? 0;
    return new Set(areas.filter((a) => (a.single_households_65_plus ?? 0) > median).map((a) => a.area_id));
  }, [areas]);
  const surveyIds = useMemo(() => new Set(areas.filter((a) => a.needs_survey).map((a) => a.area_id)), [areas]);

  const run = useCallback(async (event?: FormEvent) => {
    event?.preventDefault();
    setFocusTarget(null);
    setRunning(true);
    setError(null);
    setMinimum(null);
    try {
      const next: Partial<Record<ScenarioKey, CardResult>> = {};
      for (const scenario of SCENARIOS) {
        setProgress(`${scenario.title} 계산 중…`);
        const plan = await createSchedulePlan(scenario.id, budget, policy, regionId);
        const explanations = (await fetchPlanExplanations(plan.schedule_id)).areas;
        next[scenario.id] = { plan, explanations };
        setResults({ ...next });
      }
      const balanced = next.balanced;
      if (balanced) {
        const included = new Set(balanced.explanations.filter((row) => row.included).map((row) => row.area_id));
        const snapshot: Snapshot = {
          presetLabel: preset?.label ?? presetId,
          plan: balanced.plan,
          vulnerableCovered: [...vulnerableIds].filter((id) => included.has(id)).length,
          surveyCovered: [...surveyIds].filter((id) => included.has(id)).length,
        };
        setPrevious(current);
        setCurrent(snapshot);
      }
      setProgress("최소보장 비용 분석 중…");
      setMinimum((await analyzeMinimumCoverage(regionId, budget)).comparison);
      setProgress("");
      setFocusTarget("results");
    } catch (caught) {
      setError(caught);
      setFocusTarget("error");
      setProgress("");
    } finally {
      setRunning(false);
    }
  }, [budget, current, policy, preset, presetId, regionId, surveyIds, vulnerableIds]);

  return (
    <main className="page-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">시나리오 비교</p>
          <h1>네 가지 계획안을 같은 조건으로 나란히 비교</h1>
          <p className="page-lede">정책 프리셋은 정답이 아니라 시작 설정입니다. 결과 차이는 규칙에 따라 계산한 설명이며 AI가 판단하지 않습니다.</p>
        </div>
      </header>

      <form className="panel toolbar-form" onSubmit={run} aria-describedby="preset-notice">
        <label htmlFor="scenario-region">
          <span>지역</span>
          <select id="scenario-region" aria-label="지역" value={regionId} onChange={(e) => { setRegionId(e.target.value); saveSelectedRegionId(e.target.value); setResults({}); }}>
            {regions.map((region) => <option key={region.region_id} value={region.region_id}>{region.name}</option>)}
          </select>
        </label>
        <label htmlFor="scenario-budget">
          <span>월 예산 (원)</span>
          <input id="scenario-budget" type="number" min={0} step={100000} value={budget} onChange={(e) => setBudget(Number(e.target.value))} aria-describedby="budget-help" />
          <small id="budget-help">{won(budget)}</small>
        </label>
        <label htmlFor="scenario-preset">
          <span>정책 시작 설정</span>
          <select id="scenario-preset" value={presetId} onChange={(e) => setPresetId(e.target.value)}>
            {presets.map((item) => <option key={item.preset_id} value={item.preset_id}>{item.label}</option>)}
          </select>
        </label>
        <button type="submit" className="primary-button" disabled={running}><Play size={15} aria-hidden="true" /> {running ? "계산 중" : "4안 비교 실행"}</button>
        <p id="preset-notice" className="muted full-row">{presetNotice} 적용값: 최소 {policy.minimum_services_per_area}회 · 고령 {policy.elderly_priority_weight} · 고령 1인가구 {policy.single_elderly_household_priority_weight} · 조사필요 보호 {policy.survey_required_protection_weight}</p>
        {running ? <p className="loading-line full-row" role="status" aria-live="polite">{progress}</p> : null}
      </form>

      {error ? <div ref={errorRef} tabIndex={-1}><ApiErrorNotice error={error} onRetry={() => run()} /></div> : null}

      <section className="scenario-grid" aria-labelledby="scenario-results-heading">
        <h2 id="scenario-results-heading" tabIndex={-1} ref={resultsHeadingRef} className="sr-only">시나리오 결과</h2>
        {SCENARIOS.map((scenario) => {
          const result = results[scenario.id];
          const summary = result?.plan.summary;
          const included = result ? new Set(result.explanations.filter((row) => row.included).map((row) => row.area_id)) : null;
          return (
            <article className="scenario-card" key={scenario.id} aria-labelledby={`card-${scenario.id}`}>
              <header>
                <h2 id={`card-${scenario.id}`}>{scenario.title}</h2>
                <p className="muted">{scenario.focus}</p>
              </header>
              {!summary ? (
                <p className="empty-line">{running ? "계산 대기 중" : "아직 실행하지 않았습니다."}</p>
              ) : (
                <>
                  <SolverStatus status={summary.solver_status} hasPlan={summary.served_units > 0 || summary.solver_status === "OPTIMAL"} scope={summary.optimality_scope} strategyUsed={summary.strategy_used} fallbackUsed={summary.fallback_used} fallbackReason={summary.fallback_reason} solveTimeMs={summary.solve_time_ms} />
                  <dl className="metric-list">
                    <div><dt>서비스 회차(단위)</dt><dd>{count(summary.served_units)} / {count(summary.total_demand_units)}</dd></div>
                    <div><dt>서비스 권역</dt><dd>{count(summary.covered_areas)}</dd></div>
                    <div><dt>미충족 권역</dt><dd>{count(summary.uncovered_areas)}</dd></div>
                    <div><dt>조사필요 권역 포함</dt><dd>{included ? count([...surveyIds].filter((id) => included.has(id)).length) : "-"} / {count(surveyIds.size)}</dd></div>
                    <div><dt>총 비용 <ProvenanceBadge kind="OPTIMIZATION_RESULT" compact /></dt><dd>{won(summary.total_cost_won)}</dd></div>
                    <div><dt>공공재원 필요액</dt><dd>{won(summary.total_cost_won)} 이하<small className="cell-sub">보조·이용료 미정 → 상한만 표시</small></dd></div>
                    <div><dt>이동시간</dt><dd>{minutes(summary.travel_time_s)}</dd></div>
                  </dl>
                  <Link className="text-link" href={`/plans?id=${encodeURIComponent(result.plan.schedule_id)}`}>계획 상세·승인으로 이동</Link>
                </>
              )}
            </article>
          );
        })}
      </section>

      {results.efficiency && results.balanced && results.minimum_coverage ? (
        <section className="panel" aria-labelledby="tradeoff-title">
          <h2 id="tradeoff-title"><Scale size={17} aria-hidden="true" /> 차이 설명 (규칙 기반)</h2>
          <ul className="plain-list tradeoff-list">
            {tradeoffLines(results.efficiency.plan, results.balanced.plan, results.minimum_coverage.plan).map((line) => <li key={line}>{line}</li>)}
          </ul>
        </section>
      ) : null}

      <UnderservedComparisonPanel regionId={regionId} budgetWon={budget} />
      <ProviderResiliencePanel regionId={regionId} budgetWon={budget} />

      {previous && current ? (
        <section className="panel" aria-labelledby="changed-title">
          <h2 id="changed-title"><ArrowRightLeft size={17} aria-hidden="true" /> 무엇이 바뀌었나 (균형안: {previous.presetLabel} → {current.presetLabel})</h2>
          <ul className="plain-list tradeoff-list">
            <li>고령 1인가구 많은 권역 포함 {signed(current.vulnerableCovered - previous.vulnerableCovered, "곳")}</li>
            <li>조사필요 권역 포함 {signed(current.surveyCovered - previous.surveyCovered, "곳")}</li>
            <li>서비스 권역 {signed(current.plan.summary.covered_areas - previous.plan.summary.covered_areas, "곳")}</li>
            <li>총 이동시간 {signed(Math.round((current.plan.summary.travel_time_s - previous.plan.summary.travel_time_s) / 60), "분")}</li>
            <li>총비용 {signed(current.plan.summary.total_cost_won - previous.plan.summary.total_cost_won, "원")}</li>
          </ul>
        </section>
      ) : null}

      {minimum ? (
        <section className="panel" aria-labelledby="minimum-title">
          <h2 id="minimum-title"><Coins size={17} aria-hidden="true" /> 최소보장 비용 분석</h2>
          <dl className="metric-list wide">
            <div><dt>{minimum.theoretical_minimum_cost.label}</dt><dd>{won(minimum.theoretical_minimum_cost.value_won)}</dd></div>
            <div><dt>{minimum.schedule_feasible_minimum_cost.label}</dt><dd>{won(minimum.schedule_feasible_minimum_cost.value_won)} {minimum.schedule_feasible_minimum_cost.status !== "CALCULATED" ? `(${minimum.schedule_feasible_minimum_cost.status === "NOT_PROVEN" ? "최적성 미확인으로 금액 미표시" : "실행 불가"})` : ""}</dd></div>
            <div><dt>추가로 필요한 예산</dt><dd>{won(minimum.additional_budget_needed_won)}</dd></div>
            <div><dt>{minimum.legacy_monthly_estimate.label}</dt><dd>{won(minimum.legacy_monthly_estimate.value_won)}</dd></div>
          </dl>
          <p className={`callout ${minimum.money_alone_insufficient ? "callout-bad" : minimum.money_alone_insufficient === false ? "callout-ok" : "callout-warn"}`} role="status">{minimum.money_alone_message}</p>
          {minimum.non_monetary_failures.length ? (
            <ul className="plain-list">
              {minimum.non_monetary_failures.map((item) => (
                <li key={item.code}>{item.label}{item.area_count !== null ? ` · ${item.area_count}곳` : " · 지역 전체"} {minimum.non_monetary_scope === "BINDING_AT_CURRENT_BUDGET" ? "(현재 예산에서 걸리는 제약)" : ""}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}

function tradeoffLines(efficiency: SchedulePlan, balanced: SchedulePlan, minimum: SchedulePlan): string[] {
  const e = efficiency.summary;
  const b = balanced.summary;
  const m = minimum.summary;
  return [
    `효율 중심만 따르면 ${e.uncovered_areas}개 권역이 서비스에서 빠집니다 (균형 ${b.uncovered_areas}개, 최소보장 ${m.uncovered_areas}개).`,
    `균형안은 효율안 대비 서비스 권역 ${signed(b.covered_areas - e.covered_areas, "곳")}, 서비스 단위 ${signed(b.served_units - e.served_units)}, 이동시간 ${signed(Math.round((b.travel_time_s - e.travel_time_s) / 60), "분")}입니다.`,
    `최소보장안은 효율안 대비 서비스 권역 ${signed(m.covered_areas - e.covered_areas, "곳")}, 총비용 ${signed(m.total_cost_won - e.total_cost_won, "원")}입니다.`,
    m.required_budget_won !== null
      ? `모든 권역 최소 서비스에 일정 기준 ${won(m.required_budget_won)}이 필요합니다 (현재 예산 대비 ${signed(m.required_budget_won - minimum.budget_won, "원")}).`
      : "모든 권역 최소 서비스에 필요한 금액은 최적성이 확인되지 않아 표시하지 않습니다.",
  ];
}
