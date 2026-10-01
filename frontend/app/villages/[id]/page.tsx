"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, CircleHelp, MapPin, SearchCheck } from "lucide-react";
import { createSurvey, fetchVillage } from "@/lib/api";
import type { ScenarioKey, SurveyServiceType, SurveyType } from "@/lib/types";

const scenarioNames: Record<ScenarioKey, string> = { efficiency: "효율 우선", balanced: "균형", minimum_coverage: "최소 서비스 보장" };
const surveyTypeLabels: Record<SurveyType, string> = {
  phone: "전화",
  village_meeting: "마을회의",
  proxy: "이장·대리조사",
  field: "현장조사",
};
const serviceLabels: Record<SurveyServiceType, string> = {
  laundry: "세탁",
  daily_necessities: "생활용품 전달·지원",
  home_repair: "간단한 주거생활 지원",
};
const weekdays = [
  ["monday", "월요일"], ["tuesday", "화요일"], ["wednesday", "수요일"],
  ["thursday", "목요일"], ["friday", "금요일"], ["saturday", "토요일"],
  ["sunday", "일요일"],
] as const;

export default function VillageDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchVillage>> | null>(null);
  const [error, setError] = useState("");
  const [surveyType, setSurveyType] = useState<SurveyType>("phone");
  const [surveyDate, setSurveyDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [serviceType, setServiceType] = useState<SurveyServiceType>("laundry");
  const [frequency, setFrequency] = useState("2");
  const [preferredPeriod, setPreferredPeriod] = useState("");
  const [preferredDays, setPreferredDays] = useState<string[]>([]);
  const [constraints, setConstraints] = useState("");
  const [freeTextNote, setFreeTextNote] = useState("");
  const [savingSurvey, setSavingSurvey] = useState(false);
  const [surveyMessage, setSurveyMessage] = useState("");
  const [surveyError, setSurveyError] = useState("");
  const today = new Date().toISOString().slice(0, 10);

  useEffect(() => {
    if (id) fetchVillage(id, 5_000_000).then(setData).catch((cause) => setError(cause.message));
  }, [id]);

  async function submitSurvey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!id) return;
    setSavingSurvey(true);
    setSurveyError("");
    setSurveyMessage("");
    try {
      await createSurvey(id, {
        survey_type: surveyType,
        survey_date: surveyDate,
        service_type: serviceType,
        frequency_per_month: frequency ? Number(frequency) : null,
        preferred_period: preferredPeriod.trim() || null,
        preferred_days: preferredDays,
        constraints: constraints.split("\n").map((value) => value.trim()).filter(Boolean),
        free_text_note: freeTextNote,
      });
      const refreshed = await fetchVillage(id, 5_000_000);
      setData(refreshed);
      setSurveyMessage(`저장 완료 · ${refreshed.evidence.status} · 관측 ${refreshed.evidence.observation_count}건`);
      setFreeTextNote("");
    } catch (cause) {
      setSurveyError(cause instanceof Error ? cause.message : "조사 기록을 저장하지 못했습니다.");
    } finally {
      setSavingSurvey(false);
    }
  }

  return (
    <main className="page-main">
      <header className="topbar"><div className="breadcrumb"><Link href="/">공급계획</Link><span className="breadcrumb-sep">/</span><strong>권역 상세</strong></div><div className="topbar-right"><span className="pre-rnd-pill"><i /> PRE-R&amp;D 검증</span><span className="avatar">VC</span></div></header>
      <div className="content-page">
        <Link href="/" className="back-link"><ArrowLeft size={15} /> 공급계획으로 돌아가기</Link>
        {error && <div className="alert-box"><CircleHelp size={16} /> {error}</div>}
        {!data && !error && <div className="loading-card"><span className="spinner" /> 권역 근거를 불러오는 중입니다.</div>}
        {data && <>
          <div className="content-hero">
            <div className="eyebrow"><span className="eyebrow-line" /> VILLAGE SERVICE AREA</div>
            <h1>{data.area.name}</h1>
            <p><MapPin size={14} /> 법정동 코드 {data.area.legal_code} · 홍성군 장곡면 · 인구 통계 기준 {data.area.public_data_reference_date}</p>
          </div>
          <section className="content-card">
            <h2>공개 인구 자료 <span className="provenance-badge real">REAL PUBLIC DATA</span></h2>
            <div className="village-detail-grid">
              <div className="village-detail-item"><span>전체 인구</span><strong>{data.area.population_total.toLocaleString("ko-KR")}명</strong></div>
              <div className="village-detail-item"><span>65세 이상</span><strong>{data.area.population_65_plus.toLocaleString("ko-KR")}명 · {((data.area.elderly_ratio_65 || 0) * 100).toFixed(1)}%</strong></div>
              <div className="village-detail-item"><span>75세 이상</span><strong>{data.area.population_75_plus.toLocaleString("ko-KR")}명</strong></div>
              <div className="village-detail-item"><span>80세 이상</span><strong>{data.area.population_80_plus.toLocaleString("ko-KR")}명</strong></div>
              <div className="village-detail-item"><span>1인세대</span><strong>{data.area.single_households_total.toLocaleString("ko-KR")}세대</strong></div>
              <div className="village-detail-item"><span>65세 이상 1인세대</span><strong>{data.area.single_households_65_plus.toLocaleString("ko-KR")}세대</strong></div>
              <div className="village-detail-item"><span>시설 앵커 기록</span><strong>{data.area.facility_count}곳</strong></div>
              <div className="village-detail-item"><span>주민 요청 기록 <i className="provenance-badge simulated">SIMULATED</i></span><strong>{data.area.demand_observation_count}건 · 모의값</strong></div>
              <div className="village-detail-item"><span>월간 서비스 필요량 <i className="provenance-badge simulated">SIMULATED</i></span><strong>{data.area.simulated_monthly_demand}회 · 모의값</strong></div>
            </div>
            <p className="source-footnote">시설 좌표는 공개 마을회관·경로당 위치입니다. 도로 거리와 시간은 Kakao 경로 응답을 캐시한 실제 도로자료입니다.</p>
          </section>
          <section className="lowdata-explanation">
            <span className="lowdata-icon">?</span>
            <div><strong>{data.evidence.status} · 관측 {data.evidence.observation_count}건 · 조사 {data.evidence.survey_count}건</strong><p>{data.evidence.evidence_reasons.join(" ")}</p><b>필요한 다음 조사: {data.survey_recommendation}</b></div>
          </section>
          <section className="content-card survey-workflow" aria-labelledby="survey-heading">
            <div className="survey-title-row">
              <h2 id="survey-heading">기초조사 등록</h2>
              <span className="provenance-badge simulated">SIMULATED INPUT</span>
            </div>
            <p>전화·마을회의·대리·현장 조사 결과를 저장하면 수요 근거와 충분도를 다시 계산합니다.</p>
            <div className="survey-simulation-notice">시연용 합성 조사 입력입니다. 실제 주민 개인정보나 연락처를 입력하지 마세요.</div>
            <form className="survey-form" onSubmit={submitSurvey}>
              <div className="survey-fields-grid">
                <label>조사 방식
                  <select value={surveyType} onChange={(event) => setSurveyType(event.target.value as SurveyType)}>
                    {Object.entries(surveyTypeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                  </select>
                </label>
                <label>조사일
                  <input type="date" value={surveyDate} max={today} required onChange={(event) => setSurveyDate(event.target.value)} />
                </label>
                <label>서비스 유형
                  <select value={serviceType} onChange={(event) => setServiceType(event.target.value as SurveyServiceType)}>
                    {Object.entries(serviceLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                  </select>
                </label>
                <label>월 희망 횟수
                  <input type="number" min="1" max="31" value={frequency} onChange={(event) => setFrequency(event.target.value)} placeholder="미확인" />
                </label>
                <label>희망 시기
                  <input value={preferredPeriod} maxLength={80} onChange={(event) => setPreferredPeriod(event.target.value)} placeholder="예: 겨울철, 매월 초" />
                </label>
              </div>
              <fieldset className="survey-weekdays">
                <legend>희망 요일</legend>
                {weekdays.map(([value, label]) => <label key={value}>
                  <input type="checkbox" checked={preferredDays.includes(value)} onChange={(event) => setPreferredDays((current) => event.target.checked ? [...current, value] : current.filter((day) => day !== value))} />
                  {label}
                </label>)}
              </fieldset>
              <label className="survey-long-field">제약·제외 조건
                <textarea value={constraints} onChange={(event) => setConstraints(event.target.value)} placeholder="한 줄에 조건 하나씩 입력하세요." />
              </label>
              <label className="survey-long-field">조사 메모
                <textarea className="survey-note" value={freeTextNote} maxLength={3000} onChange={(event) => setFreeTextNote(event.target.value)} placeholder="합성 예시: 겨울철 세탁을 월 2회 희망하고 화요일은 피하고 싶음." />
              </label>
              {surveyError && <div className="request-warning" role="alert">{surveyError}</div>}
              {surveyMessage && <div className="survey-success" role="status">{surveyMessage}</div>}
              <div className="survey-submit-row"><span>저장 시 알려진 전화번호·이메일·식별번호·호칭 이름 패턴은 마스킹됩니다.</span><button type="submit" className="button button-dark" disabled={savingSurvey}>{savingSurvey ? "저장 중…" : "조사 기록 저장"}</button></div>
            </form>
            <h3>저장된 조사 기록</h3>
            {data.surveys.length === 0 ? <p className="survey-empty">아직 등록된 조사가 없습니다.</p> : <div className="survey-history">
              {data.surveys.map((survey) => <article className="survey-history-row" key={survey.survey_id}>
                <div><strong>{surveyTypeLabels[survey.survey_type]} · {serviceLabels[survey.service_type]}</strong><span>{survey.survey_date} · 월 {survey.frequency_per_month ?? "미확인"}회 · {survey.preferred_period || "시기 미확인"}</span></div>
                <span className="provenance-badge simulated">{survey.provenance}</span>
                {survey.free_text_note && <p>{survey.free_text_note}</p>}
              </article>)}
            </div>}
          </section>
          <section className="content-card">
            <h2><SearchCheck size={16} /> 시나리오별 서비스 배정</h2>
            {(Object.keys(scenarioNames) as ScenarioKey[]).map((key) => {
              const item = data.scenario_assessments[key];
              return <div className="scenario-result-row" key={key}><strong>{scenarioNames[key]} <i className="provenance-badge simulated">SIMULATED PLAN</i></strong><span>{item.status} · 월 {item.served_units}/{item.demand_units}회</span><b>{item.cost_won.toLocaleString("ko-KR")}원</b></div>;
            })}
          </section>
          <p className="provenance-footer"><span className="provenance-badge real">REAL PUBLIC DATA</span> 법정동·인구·고령인구·1인가구·시설 위치·Kakao 도로 경로 · <span className="provenance-badge simulated">SIMULATED FOR PRE-R&amp;D</span> 요청 기록·필요량·제공자 일정/용량·가격·운영 조건 <Link href="/data-quality">출처 확인 <ArrowLeft size={12} /></Link></p>
        </>}
      </div>
    </main>
  );
}
