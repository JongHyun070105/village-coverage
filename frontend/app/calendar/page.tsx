"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowRight, CalendarDays, Clock3, MapPinned, Route, Store } from "lucide-react";
import { createSchedulePlan } from "@/lib/api";
import type { ScenarioKey, SchedulePlan, ScheduleRound } from "@/lib/types";

const SCENARIOS: Array<{ id: ScenarioKey; title: string; note: string }> = [
  { id: "efficiency", title: "효율 우선", note: "제공 회차를 최대화한 뒤 실제 provider road cost를 줄입니다." },
  { id: "balanced", title: "균형", note: "회차 수를 유지하면서 조사 필요·취약 권역 분산을 반영합니다." },
  { id: "minimum_coverage", title: "최소 서비스 보장", note: "권역 수를 먼저 확보하고 예산·공급 부족을 공개합니다." },
];
const SERVICE_LABELS: Record<string, string> = {
  laundry: "세탁", daily_necessities: "생활용품 전달·지원", home_repair: "간단한 주거생활 지원",
};
const REASON_LABELS: Record<string, string> = {
  NO_SUPPORTED_PROVIDER: "서비스 공급자 없음",
  MAX_TRAVEL_TIME: "최대 이동시간 초과",
  MAX_DAILY_HOURS: "하루 근무시간 초과",
  TIME_WINDOW: "가용시간창에 맞지 않음",
  PROVIDER_UNAVAILABLE: "가용 공급자 없음",
  PREFERRED_DAY_CONFLICT: "희망 요일과 공급 요일 불일치",
  PROVIDER_CAPACITY: "공급 회차 용량 부족",
  BUDGET: "예산 부족",
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
  const [plan, setPlan] = useState<SchedulePlan | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [view, setView] = useState<"month" | "week">("month");
  const [providerFilter, setProviderFilter] = useState("all");
  const [serviceFilter, setServiceFilter] = useState("all");
  const [areaFilter, setAreaFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState("all");
  const [weekFilter, setWeekFilter] = useState("");

  async function generate() {
    setGenerating(true);
    setError("");
    try {
      setPlan(await createSchedulePlan(scenario, budget));
      setProviderFilter("all"); setServiceFilter("all"); setAreaFilter("all"); setDateFilter("all"); setWeekFilter("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "일정을 계산하지 못했습니다.");
    } finally {
      setGenerating(false);
    }
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

  return (
    <main className="main-content calendar-content">
      <header className="topbar"><div className="breadcrumb">공급 운영 <span>/</span> 서비스 일정</div><span className="demo-chip">정책 선택 · 시뮬레이션</span></header>
      <div className="dashboard-content">
        <section className="welcome-row"><div><div className="eyebrow"><span className="eyebrow-line" /> SERVICE PLAN CALENDAR</div><h1>예산과 기준을 정해<br className="mobile-break" /> 실제 회차 일정으로 확인합니다</h1><p className="welcome-copy">공급자별 가용시간과 Kakao 도로 왕복경로를 반영해 향후 4주 일정을 만듭니다.</p></div><Link href="/providers" className="text-link">공급자 참여 현황 <ArrowRight size={15} /></Link></section>

        <section className="calendar-builder" aria-label="공급 일정 생성 조건">
          <div className="calendar-builder-heading"><div><CalendarDays size={19} /><div><h2>계획 조건</h2><p>이 설정은 정책 선택이며 AI가 자동 결정한 가치판단이 아닙니다.</p></div></div><span className="provenance-badge simulated">OPTIMIZATION RESULT</span></div>
          <div className="calendar-builder-controls">
            <label>월 예산 (원)<input type="number" min={0} max={100_000_000} step={100_000} value={budget} onChange={(event) => setBudget(Math.max(0, Number(event.target.value) || 0))} /></label>
            <label>정책 시나리오<select value={scenario} onChange={(event) => setScenario(event.target.value as ScenarioKey)}>{SCENARIOS.map((option) => <option key={option.id} value={option.id}>{option.title}</option>)}</select></label>
            <div className="calendar-policy-note">{SCENARIOS.find((option) => option.id === scenario)?.note}</div>
            <button className="calendar-generate-button" onClick={() => void generate()} disabled={generating}>{generating ? "공급자 일정 계산 중…" : "일정 생성"}</button>
          </div>
          {error && <div className="calendar-error" role="alert">{error}<small>도로 캐시 누락·공급자 제약·solver 상태를 확인해 주세요. 누락 경로를 직선거리로 대체하지 않습니다.</small></div>}
        </section>

        {!plan ? <div className="calendar-empty"><CalendarDays size={25} /><strong>일정이 아직 없습니다</strong><span>시나리오와 예산을 선택하고 일정 생성을 눌러 주세요.</span></div> : <>
          <section className="calendar-metrics" aria-label="계획 일정 비용 요약">
            <div><small>배정 회차</small><strong>{compact(plan.rounds.length)}회</strong><span>{compact(plan.summary.served_units)} 서비스 단위 제공</span></div>
            <div><small>서비스 원가</small><strong>{money(plan.summary.service_cost_won)}</strong><span>회차 서비스 기준 단가 합</span></div>
            <div><small>도로 이동비</small><strong>{money(plan.summary.travel_cost_won)}</strong><span>{(plan.summary.travel_distance_m / 1000).toFixed(1)}km · {minutes(plan.summary.travel_time_s)}</span></div>
            <div><small>최소보상 보전</small><strong>{money(plan.summary.minimum_compensation_topup_won)}</strong><span>최소 보상 기준 부족분</span></div>
            <div><small>총 비용 / 잔액</small><strong>{money(plan.summary.total_cost_won)}</strong><span>잔액 {money(plan.summary.budget_remaining_won)} · 추가 필요예산 {plan.summary.budget_gap_won === null ? "산정 전" : money(plan.summary.budget_gap_won)}</span></div>
          </section>

          <section className="calendar-plan-panel">
            <div className="section-heading"><div><div className="eyebrow small">{plan.scenario_key.toUpperCase()} · {plan.summary.travel_source}</div><h2>향후 4주 공급 일정</h2><p className={`calendar-solver-status ${plan.summary.optimality_proven ? "proven" : "unproven"}`}>{plan.summary.optimality_proven ? "최적성 검증 완료" : "실행 가능 일정 · 제한시간 내 최적성 미확정"} ({plan.summary.solver_status})</p></div><div className="calendar-view-switch" role="group" aria-label="달력 기간 보기"><button className={view === "month" ? "active" : ""} onClick={() => setView("month")}>월간</button><button className={view === "week" ? "active" : ""} onClick={() => setView("week")}>주간</button></div></div>
            <div className="calendar-filters" aria-label="일정 필터">
              <label>공급자<select aria-label="공급자 필터" value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}><option value="all">전체 공급자</option>{options.providers.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
              <label>서비스<select aria-label="서비스 필터" value={serviceFilter} onChange={(event) => setServiceFilter(event.target.value)}><option value="all">전체 서비스</option>{options.services.map((service) => <option key={service} value={service}>{SERVICE_LABELS[service] || service}</option>)}</select></label>
              <label>권역<select aria-label="권역 필터" value={areaFilter} onChange={(event) => setAreaFilter(event.target.value)}><option value="all">전체 권역</option>{options.areas.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
              <label>날짜<select aria-label="날짜 필터" value={dateFilter} onChange={(event) => setDateFilter(event.target.value)}><option value="all">전체 날짜</option>{options.dates.map((date) => <option key={date} value={date}>{formatDate(date)}</option>)}</select></label>
              {view === "week" && <label>주 선택<select aria-label="주간 범위 필터" value={weekFilter || options.weeks[0] || ""} onChange={(event) => setWeekFilter(event.target.value)}>{options.weeks.map((week) => <option key={week} value={week}>{formatDate(week)} 시작</option>)}</select></label>}
            </div>
            {visibleRounds.length === 0 ? <div className="calendar-no-results">선택한 조건에 해당하는 일정이 없습니다.</div> : <div className="calendar-day-list">{groupedRounds.map(([day, rounds]) => <section className="calendar-day" key={day}><header><strong>{formatDate(day)}</strong><span>{rounds.length}회 배정</span></header><div className="calendar-day-rounds">{rounds.map((round) => <article className="calendar-round" key={round.scheduled_round_id}>
              <div className="calendar-round-time"><span>{round.departure_time}</span><small><Clock3 size={12} /> 공급자 출발</small></div>
              <div className="calendar-round-main"><strong>{round.provider_name} <span>→</span> {round.area_name}</strong><p>{round.service_start_time}–{round.service_end_time} · {SERVICE_LABELS[round.service_type] || round.service_type} · {round.service_units}단위</p><small>이동 {minutes(round.travel_before_s)} + 귀환 {minutes(round.travel_after_s)} · {(round.travel_distance_m / 1000).toFixed(1)}km</small></div>
              <div className="calendar-round-cost"><b>{money(round.total_cost_won)}</b><span>서비스 {money(round.service_cost_won)} · 이동 {money(round.travel_cost_won)}</span>{round.minimum_compensation_topup_won > 0 && <span>최소보상 보전 {money(round.minimum_compensation_topup_won)}</span>}</div>
              <Link href={`/providers/${round.provider_id}`} className={`calendar-round-status ${round.participation_status.toLowerCase()}`}><Store size={13} />{STATUS_LABELS[round.participation_status] || round.participation_status}<ArrowRight size={12} /></Link>
            </article>)}</div></section>)}</div>}
            <div className="calendar-route-disclaimer"><Route size={15} /> 각 회차는 공급자 거점→권역→거점의 개별 왕복 경로입니다. 다중 경유 최적화 전이며, 지도 직선거리를 사용하지 않습니다.</div>
          </section>
          {plan.summary.unmet_criteria.length > 0 && <section className="calendar-unmet-panel"><div className="section-heading"><div><div className="eyebrow small">UNMET CONSTRAINTS</div><h2>미충족 기준과 사유</h2></div><span>{plan.summary.uncovered_areas}개 권역 미배정 · {plan.summary.unmet_criteria.length}개 권역 수요 미충족</span></div><ul>{plan.summary.unmet_criteria.map((item) => <li key={item.area_id}><b>{item.area_name}</b><span>{item.units}단위 미충족</span><strong>{REASON_LABELS[item.reason] || item.reason}</strong></li>)}</ul></section>}
          <p className="calendar-provenance-note"><MapPinned size={14} /> 도로시간·거리는 Kakao 도로 캐시, 공급자·가용성·단가·수요·회차는 합성자료, 배정 결과는 OR-Tools 최적화 결과입니다. 일정 생성은 참여 확정이나 계약이 아닙니다.</p>
        </>}
        <footer className="page-footer"><span>일정 및 비용은 정책 비교용 계산결과입니다.</span><span>공급자 opt-in 후에도 행정 검토가 필요합니다.</span></footer>
      </div>
    </main>
  );
}
