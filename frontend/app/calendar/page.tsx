"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowDownToLine, ArrowRight, CalendarDays, Clock3, History, MapPinned, Route, Store } from "lucide-react";
import { createSchedulePlan, fetchScheduleHistory, fetchSchedulePlan, readSelectedRegionId, scheduleExportUrl } from "@/lib/api";
import type { PlanningPolicy, ScenarioKey, ScheduleHistoryEntry, SchedulePlan, ScheduleRound, SurveyServiceType } from "@/lib/types";

const SCENARIOS: Array<{ id: ScenarioKey; title: string; note: string }> = [
  { id: "efficiency", title: "효율 우선", note: "제공 회차를 최대화한 뒤 실제 provider road cost를 줄입니다." },
  { id: "balanced", title: "균형", note: "회차 수를 유지하면서 조사 필요·취약 권역 분산을 반영합니다." },
  { id: "minimum_coverage", title: "최소 서비스 보장", note: "권역 수를 먼저 확보하고 예산·공급 부족을 공개합니다." },
];
const SERVICE_LABELS: Record<string, string> = {
  laundry: "세탁", daily_necessities: "생활용품 전달·지원", home_repair: "간단한 주거생활 지원",
};
const SERVICE_OPTIONS = Object.keys(SERVICE_LABELS) as SurveyServiceType[];
const REASON_LABELS: Record<string, string> = {
  NO_SUPPORTED_PROVIDER: "서비스 공급자 없음",
  PROVIDER_DECLINED: "공급자의 해당 기간 불참 선택",
  MAX_TRAVEL_TIME: "최대 이동시간 초과",
  MAX_DAILY_HOURS: "하루 근무시간 초과",
  TIME_WINDOW: "가용시간창에 맞지 않음",
  REQUESTED_TIME_WINDOW: "요청한 날짜·시각에 공급자 가용시간이 맞지 않음",
  REQUESTED_DATE_WINDOW: "요청 날짜와 계획 기간이 맞지 않음",
  EXCLUDED_DAY_CONFLICT: "주민이 제외한 요일",
  PROVIDER_UNAVAILABLE: "가용 공급자 없음",
  PREFERRED_DAY_CONFLICT: "희망 요일과 공급 요일 불일치",
  PROVIDER_CAPACITY: "공급 회차 용량 부족",
  SHARED_PROVIDER_CAPACITY: "다른 권역 배정으로 공급자 월 회차 부족",
  SHARED_PROVIDER_TIME: "같은 날 다른 일정과 공급자 시간이 겹침",
  SCENARIO_PRIORITY: "선택한 시나리오의 우선순위",
  SCHEDULER_OPTIMALITY_NOT_PROVEN: "제한시간 내 미배정 원인 최적성 미확정",
  PROVIDER_CAPACITY_OR_TIME: "공급자 용량 또는 시간 제약으로 기준 충족 불가",
  OPTIMALITY_NOT_PROVEN: "제한시간 내 최소 필요 예산 최적성 미확정",
  BUDGET: "예산 부족",
  SERVICE_NOT_ALLOWED: "정책에서 허용하지 않은 서비스",
  MINIMUM_FREQUENCY: "설정한 최소 회차 미충족",
  DEMAND_BELOW_MINIMUM: "관측 수요가 설정한 최소 회차보다 적음",
};
const STATUS_LABELS: Record<string, string> = {
  AVAILABLE: "참여 미정", OPTED_IN: "참여 의사 표시", DECLINED: "이번 회차 불참",
  UNAVAILABLE: "참여 불가", COMPLETED: "완료", CANCELLED: "취소",
};
const money = (value: number) => `${Math.round(value).toLocaleString("ko-KR")}원`;
const compact = (value: number) => value.toLocaleString("ko-KR");
const formatDate = (value: string) => new Intl.DateTimeFormat("ko-KR", { month: "long", day: "numeric", weekday: "long" }).format(new Date(`${value}T00:00:00`));
const minutes = (seconds: number) => `${Math.ceil(seconds / 60)}분`;

function mondayFor(value: string) {
  const date = new Date(`${value}T00:00:00`);
  const shift = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - shift);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export default function CalendarPage() {
  const [scenario, setScenario] = useState<ScenarioKey>("balanced");
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
  const [plan, setPlan] = useState<SchedulePlan | null>(null);
  const [regionId, setRegionId] = useState(readSelectedRegionId);
  const [historySnapshot, setHistorySnapshot] = useState<{ regionId: string; plans: ScheduleHistoryEntry[] } | null>(null);
  const [compareScheduleId, setCompareScheduleId] = useState("");
  const [comparisonPlan, setComparisonPlan] = useState<SchedulePlan | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [view, setView] = useState<"month" | "week">("month");
  const [providerFilter, setProviderFilter] = useState("all");
  const [serviceFilter, setServiceFilter] = useState("all");
  const [areaFilter, setAreaFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState("all");
  const [weekFilter, setWeekFilter] = useState("");
  const historyLoading = historySnapshot?.regionId !== regionId;
  const history = historySnapshot?.regionId === regionId ? historySnapshot.plans : [];
  const fallbackCompareId = history.find((entry) => entry.schedule_id !== plan?.schedule_id)?.schedule_id || "";
  const effectiveCompareId = history.some((entry) => entry.schedule_id === compareScheduleId && entry.schedule_id !== plan?.schedule_id)
    ? compareScheduleId
    : fallbackCompareId;

  useEffect(() => {
    let active = true;
    fetchScheduleHistory(regionId).then((result) => {
      if (active) setHistorySnapshot({ regionId, plans: result.plans });
    }).catch(() => {
      if (active) setHistorySnapshot({ regionId, plans: [] });
    });
    return () => { active = false; };
  }, [regionId, plan?.schedule_id]);

  useEffect(() => {
    let active = true;
    if (!effectiveCompareId || effectiveCompareId === plan?.schedule_id) return () => { active = false; };
    fetchSchedulePlan(effectiveCompareId).then((result) => {
      if (active) setComparisonPlan(result);
    }).catch(() => {
      if (active) setComparisonPlan(null);
    });
    return () => { active = false; };
  }, [effectiveCompareId, plan?.schedule_id]);

  async function generate() {
    setGenerating(true);
    setError("");
    try {
      setPlan(await createSchedulePlan(scenario, budget, policy, regionId));
      setProviderFilter("all"); setServiceFilter("all"); setAreaFilter("all"); setDateFilter("all"); setWeekFilter("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "일정을 계산하지 못했습니다.");
    } finally {
      setGenerating(false);
    }
  }

  async function openSavedPlan(scheduleId: string) {
    try {
      const saved = await fetchSchedulePlan(scheduleId);
      setPlan(saved);
      setScenario(saved.scenario_key);
      setBudget(saved.budget_won);
      setPolicy(saved.planning_policy);
      setRegionId(saved.region_id);
      setProviderFilter("all"); setServiceFilter("all"); setAreaFilter("all"); setDateFilter("all"); setWeekFilter("");
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "저장된 계획을 불러오지 못했습니다.");
    }
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

  const options = useMemo(() => {
    if (!plan) return { providers: [], services: [], areas: [], dates: [], weeks: [] };
    const unique = (key: keyof ScheduleRound) => [...new Set(plan.rounds.map((round) => String(round[key])))].sort();
    return {
      providers: [...new Map(plan.rounds.map((round) => [round.provider_id, round.provider_name])).entries()],
      services: unique("service_type"),
      areas: [...new Map(plan.rounds.map((round) => [round.area_id, round.area_name])).entries()],
      dates: unique("scheduled_date"),
      weeks: [...new Set(plan.rounds.map((round) => mondayFor(round.scheduled_date)))].sort(),
    };
  }, [plan]);

  const visibleRounds = useMemo(() => {
    if (!plan) return [];
    return plan.rounds.filter((round) =>
      (providerFilter === "all" || round.provider_id === providerFilter)
      && (serviceFilter === "all" || round.service_type === serviceFilter)
      && (areaFilter === "all" || round.area_id === areaFilter)
      && (dateFilter === "all" || round.scheduled_date === dateFilter)
      && (view !== "week" || !weekFilter || mondayFor(round.scheduled_date) === weekFilter),
    );
  }, [areaFilter, dateFilter, plan, providerFilter, serviceFilter, view, weekFilter]);

  const groupedRounds = useMemo(() => {
    const grouped = new Map<string, ScheduleRound[]>();
    for (const round of visibleRounds) grouped.set(round.scheduled_date, [...(grouped.get(round.scheduled_date) || []), round]);
    return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [visibleRounds]);

  const visibleRoutes = useMemo(() => {
    if (!plan) return [];
    const routeIds = new Set(
      visibleRounds.flatMap((round) => (round.route_id ? [round.route_id] : [])),
    );
    return (plan.routes ?? []).filter((route) => routeIds.has(route.route_id));
  }, [plan, visibleRounds]);

  return (
    <main className="main-content calendar-content">
      <header className="topbar"><div className="breadcrumb">공급 운영 <span>/</span> 서비스 일정</div><span className="demo-chip">정책 선택 · 시뮬레이션</span></header>
      <div className="dashboard-content">
        <section className="welcome-row"><div><div className="eyebrow"><span className="eyebrow-line" /> SERVICE PLAN CALENDAR</div><h1>예산과 기준을 정해<br className="mobile-break" /> 실제 회차 일정으로 확인합니다</h1><p className="welcome-copy">공급자별 가용시간과 Kakao 도로 왕복·다중 경유 경로를 반영해 향후 4주 일정을 만듭니다.{plan ? ` · ${plan.region_name} 일정` : " · 대시보드에서 선택한 지역"}</p></div><Link href="/providers" className="text-link">공급자 참여 현황 <ArrowRight size={15} /></Link></section>

        <section className="calendar-builder" aria-label="공급 일정 생성 조건">
          <div className="calendar-builder-heading"><div><CalendarDays size={19} /><div><h2>계획 조건</h2><p>이 설정은 정책 선택이며 AI가 자동 결정한 가치판단이 아닙니다.</p></div></div><span className="provenance-badge simulated">OPTIMIZATION RESULT</span></div>
          <div className="calendar-builder-controls">
            <label>월 예산 (원)<input type="number" min={0} max={100_000_000} step={100_000} value={budget} onChange={(event) => setBudget(Math.max(0, Number(event.target.value) || 0))} /></label>
            <label>정책 시나리오<select value={scenario} onChange={(event) => setScenario(event.target.value as ScenarioKey)}>{SCENARIOS.map((option) => <option key={option.id} value={option.id}>{option.title}</option>)}</select></label>
            <div className="calendar-policy-note">{SCENARIOS.find((option) => option.id === scenario)?.note}</div>
            <button className="calendar-generate-button" onClick={() => void generate()} disabled={generating}>{generating ? "공급자 일정 계산 중…" : "일정 생성"}</button>
          </div>
          <details className="calendar-policy-controls">
            <summary>추가 정책 조건 <small>공급자 회차 생성과 최소보장안에 반영합니다.</small></summary>
            <p>정책 값은 담당자가 선택합니다. 최소 회차는 최소 서비스 보장 시나리오의 4주 일정 창에 적용되며, 이동 제한은 각 공급자 거점의 개별 왕복 도로시간을 기준으로 후보 회차를 거릅니다.</p>
            <div className="calendar-policy-grid">
              <label>권역별 최소 4주 회차<select value={policy.minimum_services_per_area} onChange={(event) => setPolicyValue("minimum_services_per_area", Number(event.target.value))}>{[1, 2, 3, 4, 6, 8].map((count) => <option key={count} value={count}>{count}회</option>)}</select></label>
              <label>최대 공급자 왕복 이동시간<select value={policy.maximum_round_trip_travel_minutes ?? ""} onChange={(event) => setPolicyValue("maximum_round_trip_travel_minutes", event.target.value ? Number(event.target.value) : null)}><option value="">별도 제한 없음</option>{[30, 60, 90, 120, 180, 240].map((minutesValue) => <option key={minutesValue} value={minutesValue}>{minutesValue}분</option>)}</select></label>
              <label>공급자 월 최소 보상 기준<input type="number" min={0} max={10_000_000} step={10_000} value={policy.minimum_provider_compensation_won} onChange={(event) => setPolicyValue("minimum_provider_compensation_won", Math.min(10_000_000, Math.max(0, Number(event.target.value) || 0)))} /></label>
              <fieldset><legend>허용 서비스</legend>{SERVICE_OPTIONS.map((service) => <label key={service}><input type="checkbox" checked={policy.allowed_services.includes(service)} onChange={(event) => setServiceAllowed(service, event.target.checked)} />{SERVICE_LABELS[service]}</label>)}</fieldset>
              <label className="calendar-policy-range">고령인구 우선 가중치 <output>{policy.elderly_priority_weight / 100}/10</output><input type="range" min={0} max={1000} step={100} value={policy.elderly_priority_weight} onChange={(event) => setPolicyValue("elderly_priority_weight", Number(event.target.value))} /></label>
              <label className="calendar-policy-range">고령 1인가구 우선 가중치 <output>{policy.single_elderly_household_priority_weight / 100}/10</output><input type="range" min={0} max={1000} step={100} value={policy.single_elderly_household_priority_weight} onChange={(event) => setPolicyValue("single_elderly_household_priority_weight", Number(event.target.value))} /></label>
              <label className="calendar-policy-range">조사 필요 권역 보호 가중치 <output>{policy.survey_required_protection_weight / 100}/10</output><input type="range" min={0} max={1000} step={100} value={policy.survey_required_protection_weight} onChange={(event) => setPolicyValue("survey_required_protection_weight", Number(event.target.value))} /></label>
            </div>
          </details>
          {error && <div className="calendar-error" role="alert">{error}<small>도로 캐시 누락·공급자 제약·solver 상태를 확인해 주세요. 누락 경로를 직선거리로 대체하지 않습니다.</small></div>}
        </section>

        <section className="saved-plans-panel" aria-label="저장된 계획 이력">
          <div className="calendar-routing-heading">
            <div><div className="eyebrow small"><History size={13} /> PLAN HISTORY</div><h2>저장된 계획과 정책 버전</h2><p>각 항목은 생성 시점의 지역·예산·정책·산정 결과를 보존합니다. 저장 기록은 계약이나 공급자 확정이 아닙니다.</p></div>
            <span>{historyLoading ? "이력 불러오는 중" : `${history.length}개 저장`}</span>
          </div>
          {history.length === 0 && !historyLoading ? <p className="calendar-routing-empty">이 지역의 저장된 계획이 없습니다. 일정 생성 후 계획 버전이 이곳에 남습니다.</p> : <div className="saved-plan-list">{history.map((entry) => {
            const entryScenario = SCENARIOS.find((option) => option.id === entry.scenario_key);
            return <article className={`saved-plan-card ${entry.schedule_id === plan?.schedule_id ? "active" : ""}`} key={entry.schedule_id}>
              <header><div><strong>{entryScenario?.title || entry.scenario_key} · {entry.region_name}</strong><small>{new Date(entry.created_at).toLocaleString("ko-KR")} · 계획 {entry.schedule_id.slice(0, 8)}</small></div><b>{money(entry.summary.total_cost_won)}</b></header>
              <p>예산 {money(entry.budget_won)} · {entry.round_count}회 · 서비스 {entry.summary.covered_areas}/{entry.summary.covered_areas + entry.summary.uncovered_areas}권역 · 이동 {(entry.summary.travel_distance_m / 1000).toFixed(1)}km</p>
              <div className="saved-plan-actions"><button onClick={() => void openSavedPlan(entry.schedule_id)}>일정 열기</button><button onClick={() => setCompareScheduleId(entry.schedule_id)} disabled={!plan || entry.schedule_id === plan.schedule_id}>비교 기준</button><a href={scheduleExportUrl(entry.schedule_id)}><ArrowDownToLine size={13} /> CSV 내려받기</a></div>
            </article>;
          })}</div>}
          {plan && <div className="saved-plan-compare">
            <label>비교할 저장 계획<select aria-label="비교할 저장 계획" value={effectiveCompareId} onChange={(event) => setCompareScheduleId(event.target.value)}><option value="">비교할 계획 선택</option>{history.filter((entry) => entry.schedule_id !== plan.schedule_id).map((entry) => <option key={entry.schedule_id} value={entry.schedule_id}>{SCENARIOS.find((option) => option.id === entry.scenario_key)?.title || entry.scenario_key} · {new Date(entry.created_at).toLocaleString("ko-KR")} · {money(entry.budget_won)}</option>)}</select></label>
            {comparisonPlan?.schedule_id === effectiveCompareId && <div className="saved-plan-compare-grid" aria-label="저장 계획 비교 결과">
              {[{ label: "현재 열린 계획", value: plan }, { label: "비교 기준", value: comparisonPlan }].map(({ label, value }) => <article key={label}><small>{label} · {SCENARIOS.find((option) => option.id === value.scenario_key)?.title || value.scenario_key}</small><strong>{value.region_name}</strong><span>{value.rounds.length}회 · 총비용 {money(value.summary.total_cost_won)}</span><span>최소 회차 {value.summary.minimum_frequency_met_areas}/{value.summary.minimum_frequency_met_areas + value.summary.unmet_minimum_frequency_areas}권역 · 이동 {(value.summary.travel_distance_m / 1000).toFixed(1)}km</span><span>예산 {money(value.budget_won)} · {value.summary.optimality_proven ? "모델 목적 최적성 검증" : "실행 가능 · 모델 목적 최적성 미확정"}</span>{value.summary.global_route_optimality_proven === false && <small>다중 경유 전역 최적성은 증명되지 않았습니다.</small>}<small>정책 보관: 최소 {value.planning_policy.minimum_services_per_area}회 · 허용 {value.planning_policy.allowed_services.length}개 서비스</small></article>)}
            </div>}
          </div>}
        </section>

        {!plan ? <div className="calendar-empty"><CalendarDays size={25} /><strong>일정이 아직 없습니다</strong><span>시나리오와 예산을 선택하고 일정 생성을 눌러 주세요.</span></div> : <>
          <section className="calendar-metrics" aria-label="계획 일정 비용 요약">
            <div><small>배정 회차</small><strong>{compact(plan.rounds.length)}회</strong><span>{compact(plan.summary.served_units)} 서비스 단위 제공</span></div>
            <div><small>서비스 원가</small><strong>{money(plan.summary.service_cost_won)}</strong><span>회차 서비스 기준 단가 합</span></div>
            <div><small>도로 이동비</small><strong>{money(plan.summary.travel_cost_won)}</strong><span>{(plan.summary.travel_distance_m / 1000).toFixed(1)}km · {minutes(plan.summary.travel_time_s)}</span></div>
            <div><small>최소보상 보전</small><strong>{money(plan.summary.minimum_compensation_topup_won)}</strong><span>최소 보상 기준 부족분</span></div>
            <div><small>최소 회차 충족 / 공급 용량 상한</small><strong>{plan.summary.minimum_frequency_met_areas}/{plan.summary.minimum_frequency_met_areas + plan.summary.unmet_minimum_frequency_areas}권역</strong><span>필요 {plan.summary.required_capacity}회 · 적격 공급자 월 한도 상한 {plan.summary.available_capacity}회 · 상한 대비 부족 {plan.summary.missing_capacity}회 (예산·시간 제약 전)</span></div>
            <div><small>총 비용 / 예산 잔액</small><strong>{money(plan.summary.total_cost_won)}</strong><span>현재 계획 예산 잔액 {money(plan.summary.budget_remaining_won)}</span></div>
            <div><small>최소 기준 필요 예산 · {plan.summary.required_budget_model === "PROVIDER_CP_SAT_INTEGRATED_KAKAO_VRPTW" ? "provider별 통합 Kakao 경로" : plan.summary.required_budget_model === "PROVIDER_CP_SAT_KAKAO_VRPTW_WITH_HUB_FALLBACK" ? "Kakao 경로·허브 왕복 대체" : "중앙 거점 왕복 모델"}</small><strong>{plan.summary.required_budget_status === "CALCULATED" ? money(plan.summary.required_budget_won || 0) : "산정 불가"}</strong><span>{plan.summary.required_budget_status === "CALCULATED" ? `현재 예산 ${money(plan.budget_won)} · 추가 필요 ${money(plan.summary.budget_gap_won || 0)}` : REASON_LABELS[plan.summary.required_budget_reason || ""] || "최적성 또는 공급·시간 조건을 확인할 수 없습니다."}</span></div>
          </section>

          <section className="calendar-routing-panel" aria-label="왕복 경로와 다중 경유 경로 비교">
            <div className="calendar-routing-heading"><div><div className="eyebrow small">ROAD ROUTING COMPARISON</div><h2>개별 왕복과 다중 경유 비교</h2><p>모든 이동은 Kakao 도로 캐시를 사용하며, 다중 경유 경로는 OR-Tools가 같은 공급자·날짜 안에서 순서를 계산합니다.</p></div><span>{plan.summary.routing_comparison.multi_stop_route_count}개 다중 경유 경로</span></div>
            <div className="calendar-routing-metrics">
              <div><small>개별 왕복 기준</small><strong>{(plan.summary.routing_comparison.old_distance_m / 1000).toFixed(1)}km · {minutes(plan.summary.routing_comparison.old_duration_s)}</strong><span>이동비 {money(plan.summary.routing_comparison.old_cost_won)}</span></div>
              <div><small>계산 경로</small><strong>{(plan.summary.routing_comparison.actual_distance_m / 1000).toFixed(1)}km · {minutes(plan.summary.routing_comparison.actual_duration_s)}</strong><span>이동비 {money(plan.summary.routing_comparison.actual_cost_won)}</span></div>
              <div><small>절감</small><strong>{(plan.summary.routing_comparison.distance_savings_m / 1000).toFixed(1)}km · {minutes(plan.summary.routing_comparison.duration_savings_s)}</strong><span>{money(plan.summary.routing_comparison.cost_savings_won)}</span></div>
            </div>
            {visibleRoutes.some((route) => route.route_type === "MULTI_STOP") ? <div className="calendar-route-list">{visibleRoutes.filter((route) => route.route_type === "MULTI_STOP").map((route) => <article className="calendar-route-card" key={route.route_id}>
              <header><strong>{route.provider_name} · {formatDate(route.scheduled_date)}</strong><span>{(route.distance_m / 1000).toFixed(1)}km · {minutes(route.duration_s)} · {money(route.cost_won)}</span></header>
              <ol>{route.stops.map((stop) => <li key={stop.route_stop_id}><b>{stop.sequence}</b><div><strong>{stop.sequence === 1 ? "공급자 거점" : stop.incoming_from_area_name} → {stop.area_name}</strong><small>{stop.service_start_time}–{stop.service_end_time} · 진입 {minutes(stop.incoming_time_s)} · {(stop.incoming_distance_m / 1000).toFixed(1)}km</small></div><span>다음: {stop.outgoing_to_area_id === route.base_area_id ? "공급자 거점" : stop.outgoing_to_area_name}<small>{minutes(stop.outgoing_time_s)} · {(stop.outgoing_distance_m / 1000).toFixed(1)}km</small></span></li>)}</ol>
            </article>)}</div> : <p className="calendar-routing-empty">선택한 일정에는 개별 거점 왕복이 적용되었습니다. 필요한 Kakao 경로가 없거나 같은 날 여러 권역을 묶어도 이동 이점이 확인되지 않으면 다중 경유로 바꾸지 않습니다.</p>}
          </section>

          <section className="calendar-plan-panel">
            <div className="section-heading"><div><div className="eyebrow small">{plan.scenario_key.toUpperCase()} · {plan.summary.travel_source}</div><h2>향후 4주 공급 일정</h2><p className="calendar-plan-policy">적용 정책 · 최소 {plan.planning_policy.minimum_services_per_area}회 · 허용 서비스 {plan.planning_policy.allowed_services.map((service) => SERVICE_LABELS[service]).join("·")} · 왕복 제한 {plan.planning_policy.maximum_round_trip_travel_minutes === null ? "없음" : `${plan.planning_policy.maximum_round_trip_travel_minutes}분`} · 보상 하한 {money(plan.planning_policy.minimum_provider_compensation_won)} · 주·월 불참 기간은 후보에서 제외, 참여 의사는 동률 기준</p><p className={`calendar-solver-status ${plan.summary.optimality_proven ? "proven" : "unproven"}`}>{plan.summary.optimality_proven ? "모델 목적 최적성 검증 완료" : "실행 가능 일정 · 제한시간 내 모델 목적 최적성 미확정"} ({plan.summary.solver_status})</p>{plan.summary.route_assignment_model && <p className="calendar-plan-policy">경로 배정 모델 {plan.summary.route_assignment_model} · 완전한 Kakao 행렬의 후보 창 {plan.summary.exact_route_group_count ?? 0}개 · 허브 왕복 대체 창 {plan.summary.hub_fallback_group_count ?? 0}개 · {plan.summary.global_route_optimality_proven ? "현재 경로 모델 범위의 최적성 증명 완료" : "제한시간 또는 누락된 도로 구간으로 전역 경로 최적성 미확정"}</p>}</div><div className="calendar-plan-actions"><a className="calendar-export-link" href={scheduleExportUrl(plan.schedule_id)}><ArrowDownToLine size={14} /> CSV 내려받기</a><div className="calendar-view-switch" role="group" aria-label="달력 기간 보기"><button className={view === "month" ? "active" : ""} onClick={() => setView("month")}>월간</button><button className={view === "week" ? "active" : ""} onClick={() => setView("week")}>주간</button></div></div></div>
            <div className="calendar-filters" aria-label="일정 필터">
              <label>공급자<select aria-label="공급자 필터" value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}><option value="all">전체 공급자</option>{options.providers.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
              <label>서비스<select aria-label="서비스 필터" value={serviceFilter} onChange={(event) => setServiceFilter(event.target.value)}><option value="all">전체 서비스</option>{options.services.map((service) => <option key={service} value={service}>{SERVICE_LABELS[service] || service}</option>)}</select></label>
              <label>권역<select aria-label="권역 필터" value={areaFilter} onChange={(event) => setAreaFilter(event.target.value)}><option value="all">전체 권역</option>{options.areas.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
              <label>날짜<select aria-label="날짜 필터" value={dateFilter} onChange={(event) => setDateFilter(event.target.value)}><option value="all">전체 날짜</option>{options.dates.map((date) => <option key={date} value={date}>{formatDate(date)}</option>)}</select></label>
              {view === "week" && <label>주 선택<select aria-label="주간 범위 필터" value={weekFilter || options.weeks[0] || ""} onChange={(event) => setWeekFilter(event.target.value)}>{options.weeks.map((week) => <option key={week} value={week}>{formatDate(week)} 시작</option>)}</select></label>}
            </div>
            {visibleRounds.length === 0 ? <div className="calendar-no-results">선택한 조건에 해당하는 일정이 없습니다.</div> : <div className="calendar-day-list">{groupedRounds.map(([day, rounds]) => <section className="calendar-day" key={day}><header><strong>{formatDate(day)}</strong><span>{rounds.length}회 배정</span></header><div className="calendar-day-rounds">{rounds.map((round) => <article className="calendar-round" key={round.scheduled_round_id}>
              <div className="calendar-round-time"><span>{round.departure_time}</span><small><Clock3 size={12} /> {round.route_type === "MULTI_STOP" && round.route_sequence > 1 ? "이전 권역 출발" : "공급자 출발"}</small></div>
              <div className="calendar-round-main"><strong>{round.provider_name} <span>→</span> {round.area_name}</strong><p>{round.service_start_time}–{round.service_end_time} · {SERVICE_LABELS[round.service_type] || round.service_type} · {round.service_units}단위</p><small>{round.route_type === "MULTI_STOP" ? `이전 구간 ${minutes(round.travel_before_s)} · 다음 구간 ${minutes(round.travel_after_s)}` : `이동 ${minutes(round.travel_before_s)} + 귀환 ${minutes(round.travel_after_s)}`} · {(round.travel_distance_m / 1000).toFixed(1)}km · {round.route_type === "MULTI_STOP" ? `${round.route_sequence}번째 경유` : "개별 왕복"}</small></div>
              <div className="calendar-round-cost"><b>{money(round.total_cost_won)}</b><span>서비스 {money(round.service_cost_won)} · 이동 {money(round.travel_cost_won)}</span>{round.minimum_compensation_topup_won > 0 && <span>최소보상 보전 {money(round.minimum_compensation_topup_won)}</span>}</div>
              <Link href={`/providers/${round.provider_id}`} className={`calendar-round-status ${round.participation_status.toLowerCase()}`}><Store size={13} />{round.participation_source === "WEEK" ? "주 설정 참여 의사" : round.participation_source === "MONTH" ? "월 설정 참여 의사" : STATUS_LABELS[round.participation_status] || round.participation_status}<ArrowRight size={12} /></Link>
            </article>)}</div></section>)}</div>}
            <div className="calendar-route-disclaimer"><Route size={15} /> 다중 경유 일정은 공급자 거점에서 출발해 표시된 순서로 권역을 방문한 뒤 복귀합니다. 다중 경유가 성립하지 않으면 개별 왕복을 사용하며 지도 직선거리로 대체하지 않습니다.</div>
          </section>
          {(plan.summary.planning_demand_inputs?.length ?? 0) > 0 && <details className="calendar-unmet-panel calendar-demand-basis">
            <summary>권역별 수요 산정 근거 · {plan.summary.planning_demand_inputs?.length ?? 0}개 권역</summary>
            <p>인구는 공개자료 실측값입니다. 인구 prior는 선택 지역·서비스별 합성 기준회차를 공개 인구로 나눈 설명용 시뮬레이션이며 실제 관측 수요나 예측값이 아닙니다. seed 기준과 조사 빈도 하한을 낮추지 않고, 조사 표본은 합산·마을 전체로 확대하지 않습니다. 기존 제공 회차는 최근 CSV 자료가 있을 때만 차감합니다.</p>
            <ul>{plan.summary.planning_demand_inputs?.map((item) => <li key={item.area_id}>
              <b>{item.area_name} · {SERVICE_LABELS[item.service_type] || item.service_type}</b>
              <span>합성 seed {item.source_baseline_units}회 · 공개 인구 {item.population_total === null ? "확인 불가" : `${item.population_total.toLocaleString()}명 (${item.population_reference_date ?? "기준일 없음"})`} · 서비스별 합성 기준률 {item.population_rate_per_1000_simulated_rounds === null ? "계산 불가" : `${item.population_rate_per_1000_simulated_rounds.toFixed(2)}회/1,000명`} · 합성 인구 prior {item.population_prior_floor_units === null ? "계산 불가" : `${item.population_prior_floor_units}회`} · 조정 기준 {item.population_adjusted_baseline_units}회</span>
              <span>조사 빈도 하한 {item.survey_frequency_floor_monthly === null ? "없음" : `${item.survey_frequency_floor_monthly}회 (${item.survey_frequency_observation_count}건)`} · 기존 제공 차감 {item.existing_service_status === "CURRENT_REPORTED_SNAPSHOT" ? `${item.existing_service_rounds_deducted}회` : "미확인·오래됨, 차감 안 함"}</span>
              <small>{item.population_prior_model} · {item.population_prior_provenance}</small>
              <strong>계획 수요 {item.planning_demand_units}회</strong>
            </li>)}</ul>
          </details>}
          {(plan.summary.unmet_criteria.length > 0 || plan.summary.minimum_frequency_gaps.length > 0) && <section className="calendar-unmet-panel"><div className="section-heading"><div><div className="eyebrow small">UNMET CONSTRAINTS</div><h2>미충족 기준과 사유</h2></div><span>{plan.summary.uncovered_areas}개 권역 미배정 · 최소 회차 {plan.summary.minimum_frequency_met_areas}/{plan.summary.minimum_frequency_met_areas + plan.summary.unmet_minimum_frequency_areas}개 충족</span></div><ul>{plan.summary.unmet_criteria.map((item) => <li key={`demand-${item.area_id}`}><b>{item.area_name}</b><span>{item.units}단위 미충족</span><strong>{(item.reasons?.length ? item.reasons : [item.reason]).map((reason) => REASON_LABELS[reason] || reason).join(" · ")}</strong></li>)}{plan.summary.minimum_frequency_gaps.map((item) => <li key={`frequency-${item.area_id}`}><b>{item.area_name}</b><span>{item.missing_rounds}회차 부족</span><strong>{(item.reasons?.length ? item.reasons : [item.reason]).map((reason) => REASON_LABELS[reason] || reason).join(" · ")}</strong></li>)}</ul></section>}
          <p className="calendar-provenance-note"><MapPinned size={14} /> 도로시간·거리는 Kakao 도로 캐시, 기준 수요·공급자·가용성·단가는 시연용 합성자료입니다. 최근 조사 빈도와 기존 제공 실적은 출처를 분리해 표시하고 조사 표본을 마을 전체로 확대하지 않습니다. 배정은 OR-Tools 결과이며 참여 확정이나 계약이 아닙니다.</p>
        </>}
        <footer className="page-footer"><span>일정 및 비용은 정책 비교용 계산결과입니다.</span><span>공급자 opt-in 후에도 행정 검토가 필요합니다.</span></footer>
      </div>
    </main>
  );
}
