"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, BadgeAlert, Check, CircleHelp, Clock3, MapPinned, ShieldCheck, Store } from "lucide-react";
import { fetchProvider, updateProviderParticipation } from "@/lib/api";
import type { ProviderDetail, ProviderForecastMonth, ProviderParticipationStatus, ProviderRound } from "@/lib/types";

const SERVICE_LABELS: Record<string, string> = {
  laundry: "세탁",
  daily_necessities: "생활용품 전달·지원",
  home_repair: "간단한 주거생활 지원",
};
const WEEKDAYS: Record<string, string> = {
  monday: "월", tuesday: "화", wednesday: "수", thursday: "목", friday: "금", saturday: "토", sunday: "일",
};
const money = (value: number) => `${value.toLocaleString("ko-KR")}원`;
const dateLabel = (value: string) => new Intl.DateTimeFormat("ko-KR", { month: "long", day: "numeric", weekday: "short" }).format(new Date(`${value}T00:00:00`));
const forecastMonthLabel = (value: string) => {
  const [year, month] = value.split("-");
  return `${year}년 ${Number(month)}월`;
};
const STATUS_LABELS: Record<ProviderParticipationStatus, string> = {
  AVAILABLE: "미정",
  OPTED_IN: "참여 의사 표시",
  DECLINED: "이번 회차 불참",
  UNAVAILABLE: "불가",
  COMPLETED: "완료",
  CANCELLED: "취소",
};

export default function ProviderDetailPage() {
  const params = useParams<{ id: string }>();
  const providerId = params.id;
  const [provider, setProvider] = useState<ProviderDetail | null>(null);
  const [error, setError] = useState("");
  const [busyRound, setBusyRound] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    fetchProvider(providerId)
      .then((result) => { if (active) { setProvider(result); setError(""); } })
      .catch((reason: Error) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [providerId]);

  async function setStatus(round: ProviderRound, status: Extract<ProviderParticipationStatus, "OPTED_IN" | "DECLINED" | "AVAILABLE">) {
    setBusyRound(round.round_id);
    setMessage("");
    try {
      const result = await updateProviderParticipation(providerId, round.round_id, status);
      setProvider(result.provider);
      setMessage(result.message);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "참여 상태를 저장하지 못했습니다.");
    } finally {
      setBusyRound("");
    }
  }

  if (error && !provider) return <main className="main-content provider-content"><header className="topbar"><Link href="/providers" className="text-link"><ArrowLeft size={15} /> 공급자 목록</Link></header><div className="dashboard-content"><div className="loading-card">{error}</div></div></main>;
  if (!provider) return <main className="main-content provider-content"><header className="topbar"><Link href="/providers" className="text-link"><ArrowLeft size={15} /> 공급자 목록</Link></header><div className="dashboard-content"><div className="loading-card"><span className="spinner" /> 공급자 정보를 불러오는 중…</div></div></main>;

  const history = provider.participation;
  const availability = provider.availability.map((item) => `${WEEKDAYS[item.weekday]} ${item.start_time}–${item.end_time}`).join(" · ");
  const forecastStatus = provider.forecast.status === "DATA_INSUFFICIENT"
    ? "데이터 부족"
    : provider.forecast.survey_required ? "일부 추가 조사 필요" : "비구속 전망";

  return (
    <main className="main-content provider-content">
      <header className="topbar"><div className="breadcrumb"><Link href="/providers">공급자</Link> <span>/</span> {provider.name}</div><span className="demo-chip">PRE-R&amp;D 시뮬레이션</span></header>
      <div className="dashboard-content">
        <section className="provider-detail-hero">
          <div className="provider-detail-title"><span className="provider-avatar large"><Store size={23} /></span><div><div className="eyebrow"><span className="eyebrow-line" /> SIMULATED PROVIDER</div><h1>{provider.name}</h1><p><MapPinned size={15} />{provider.base_location}</p></div></div>
          <Link href="/providers" className="text-link"><ArrowLeft size={15} /> 공급자 목록</Link>
        </section>

        <div className="provider-provenance"><BadgeAlert size={17} /><span>아래 프로필·운영조건·참여기록은 모두 시연용 합성자료이며, 가상 거점 좌표는 실제 공급자 주소가 아닙니다.</span></div>

        <section className="provider-profile-grid" aria-label="공급자 역량">
          <article className="provider-info-card"><h2>서비스 역량</h2><div className="provider-tags">{provider.supported_services.map((service) => <span key={service}>{SERVICE_LABELS[service] || service}</span>)}</div><p>제공 가능 단위: 회차당 최대 {provider.service_capacity}개 서비스 대상</p></article>
          <article className="provider-info-card"><h2>운영 가능 시간</h2><p className="provider-availability">{availability || "등록된 시간이 없습니다."}</p><p>하루 최대 {provider.max_daily_hours}시간 · 월 최대 {provider.max_monthly_rounds}회</p></article>
          <article className="provider-info-card"><h2>이동과 보상 기준</h2><p>최대 이동 허용 <b>{provider.max_travel_time_minutes}분</b></p><p>월 최소 보상 기준 <b>{money(provider.minimum_compensation_won)}</b></p></article>
        </section>

        <section className="provider-history-panel">
          <div className="section-heading"><div><div className="eyebrow small">PARTICIPATION HISTORY</div><h2>참여 이력과 안정성 신호</h2></div><span className="provider-history-window">최근 모의 기회 {history.opportunities}회</span></div>
          <div className="provider-history-metrics"><div><small>참여 수락</small><strong>{history.accepted}회</strong></div><div><small>완료</small><strong>{history.completed}회</strong></div><div><small>불참</small><strong>{history.declined}회</strong></div><div><small>완료율</small><strong>{history.completion_rate === null ? "산정 자료 없음" : `${Math.round(history.completion_rate * 100)}%`}</strong></div></div>
          <div className={`provider-agreement-signal ${history.long_term_agreement_candidate ? "eligible" : ""}`}><ShieldCheck size={18} /><span><b>{history.long_term_agreement_candidate ? "장기협약 검토 후보" : "참여 이력 축적 중"}</b><small>{history.reliability_label} · 참고 신호이며 자동 계약이나 법적 판단이 아닙니다.</small></span></div>
        </section>

        <section className="provider-forecast-panel">
          <div className="section-heading"><div><div className="eyebrow small">NON-BINDING OUTLOOK</div><h2>앞으로 3개월 예상 수요</h2></div><span className="forecast-status">{forecastStatus}</span></div>
          {provider.forecast.months.length > 0 ? <div className="provider-forecast-months">{provider.forecast.months.map((month) => <ForecastMonthCard key={`${month.region_id}-${month.service_type}-${month.month}`} month={month} />)}</div> : <div className="forecast-empty"><CircleHelp size={18} /><span><b>추가 조사 필요 · 전망 범위를 산출하지 않았습니다.</b><small>{provider.forecast.message}</small></span></div>}
          <p className="forecast-method-note">모델 {provider.forecast.model_version} · {provider.forecast.message} · {provider.forecast.provenance}</p>
          <p className="nonbinding-note">전망이 제공될 경우에도 확정 일정이나 계약상 의무가 아닙니다.</p>
        </section>

        <section className="provider-opportunities">
          <div className="section-heading"><div><div className="eyebrow small">UPCOMING OPPORTUNITIES</div><h2>참여 가능한 회차</h2><p>회차별 참여 의사를 표시해도 계약이나 확정 배정이 발생하지 않습니다.</p></div></div>
          {message && <div className="provider-action-message" role="status">{message}</div>}
          {provider.upcoming_rounds.length === 0 ? <div className="loading-card">현재 등록된 회차 기회가 없습니다.</div> : <div className="provider-round-list">{provider.upcoming_rounds.map((round) => {
            const pending = busyRound === round.round_id;
            return <article className="provider-round-card" key={round.round_id}>
              <div className="round-date"><strong>{dateLabel(round.round_date)}</strong><span>{round.start_time} · {round.duration_minutes}분</span></div>
              <div className="round-location"><b>{round.area_name}</b><span>{SERVICE_LABELS[round.service_type] || round.service_type}</span></div>
              <div className="round-terms"><span><Clock3 size={14} /> 도로 이동 {round.travel_time_minutes === null || round.travel_distance_km === null ? "미산정" : `${round.travel_time_minutes}분 · ${round.travel_distance_km.toFixed(1)}km`}</span><span>예상 회차 보상 {money(round.estimated_compensation_won)} <small>모의값</small></span></div>
              <div className={`round-state ${round.status.toLowerCase()}`}><span>{round.status === "OPTED_IN" && <Check size={13} />}{STATUS_LABELS[round.status]}</span>
                <div className="round-actions">
                  {round.status === "AVAILABLE" ? <><button disabled={pending} onClick={() => void setStatus(round, "OPTED_IN")}>{pending ? "저장 중" : "참여 의사 표시"}</button><button className="secondary" disabled={pending} onClick={() => void setStatus(round, "DECLINED")}>이번 회차 불참</button></> : round.status === "OPTED_IN" ? <button className="secondary" disabled={pending} onClick={() => void setStatus(round, "AVAILABLE")}>참여 의사 취소</button> : round.status === "DECLINED" ? <button className="secondary" disabled={pending} onClick={() => void setStatus(round, "OPTED_IN")}>참여 검토</button> : null}
                </div>
              </div>
            </article>;
          })}</div>}
          <div className="provider-route-note"><MapPinned size={15} /> 사전 시연 기회 중 도로 경로가 없는 회차는 이동 미산정으로 표시합니다. 새 일정의 이동비·시간·거리는 Kakao 도로 캐시를 사용하며, 미산정 값을 0으로 간주하지 않습니다.</div>
        </section>

        <footer className="page-footer"><span>공급자 참여 시뮬레이션 · 무인증 데모 행위자</span><span>참여 의사는 계약 또는 확정 일정이 아닙니다.</span></footer>
      </div>
    </main>
  );
}

function ForecastMonthCard({ month }: { month: ProviderForecastMonth }) {
  const service = SERVICE_LABELS[month.service_type] || month.service_type;
  const available = month.evidence_status === "SUFFICIENT_OBSERVED"
    && month.expected_rounds_low !== null
    && month.expected_rounds_mid !== null
    && month.expected_rounds_high !== null;

  return <article className={`provider-forecast-month ${available ? "available" : "insufficient"}`}>
    <div className="forecast-month-heading"><strong>{forecastMonthLabel(month.month)}</strong><span>{service}</span></div>
    <small className="forecast-region">{month.region_name}</small>
    {available ? <>
      <b className="forecast-range">{month.expected_rounds_low}–{month.expected_rounds_high}회</b>
      <small>중앙 추정 {month.expected_rounds_mid}회 · 신뢰도 {month.confidence ?? "미산정"}</small>
      <small>관측 {month.observation_count}건 · {month.observed_area_count}/{month.region_area_count}개 권역</small>
      <small>산출 근거 {month.model_basis === "SEASONAL_MEDIAN_MAD" ? "계절 중앙값·변동폭" : "최근 관측 중앙값·변동폭"}</small>
    </> : <>
      <b className="forecast-no-value">데이터 부족 · 추가 조사 필요</b>
      <small>관측 {month.observation_count}건 · {month.observed_area_count}/{month.region_area_count}개 권역</small>
    </>}
  </article>;
}
