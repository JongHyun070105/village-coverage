"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, CircleHelp, MapPin, SearchCheck } from "lucide-react";
import { createSurvey, fetchVillage } from "@/lib/api";
import EvidenceReviewPanel from "@/components/evidence-review-panel";
import RecentFeedbackPanel from "@/components/recent-feedback-panel";
import { koreaDateValue } from "@/lib/date";
import type { ScenarioKey, SurveyServiceType, SurveyType } from "@/lib/types";

const scenarioNames: Record<ScenarioKey, string> = { efficiency: "효율 우선", balanced: "균형", minimum_coverage: "최소 서비스 보장", underserved_first: "소외 최소화" };
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
  const [surveyDate, setSurveyDate] = useState(() => koreaDateValue());
  const [serviceType, setServiceType] = useState<{ areaId: string; value: SurveyServiceType } | null>(null);
  const [frequency, setFrequency] = useState("2");
  const [preferredPeriod, setPreferredPeriod] = useState("");
  const [preferredDays, setPreferredDays] = useState<string[]>([]);
  const [constraints, setConstraints] = useState("");
  const [freeTextNote, setFreeTextNote] = useState("");
  const [savingSurvey, setSavingSurvey] = useState(false);
  const [evidenceReviewRevision, setEvidenceReviewRevision] = useState(0);
  const [surveyMessage, setSurveyMessage] = useState("");
  const [surveyError, setSurveyError] = useState("");
  const today = koreaDateValue();
  const village = data?.area.id === id ? data : null;
  const suggestedServiceType = village && village.area.service_type in serviceLabels
    ? village.area.service_type as SurveyServiceType
    : "laundry";
  const selectedServiceType = serviceType && village && serviceType.areaId === village.area.id
    ? serviceType.value
    : suggestedServiceType;

  useEffect(() => {
    if (!id) return;
    let active = true;
    fetchVillage(id, 5_000_000)
      .then((village) => {
        if (!active) return;
        setData(village);
        setError("");
      })
      .catch((cause) => { if (active) setError(cause.message); });
    return () => { active = false; };
  }, [id]);

  async function submitSurvey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!id || !village) return;
    setSavingSurvey(true);
    setSurveyError("");
    setSurveyMessage("");
    try {
      await createSurvey(id, {
        survey_type: surveyType,
        survey_date: surveyDate,
        service_type: selectedServiceType,
        frequency_per_month: frequency ? Number(frequency) : null,
        preferred_period: preferredPeriod.trim() || null,
        preferred_days: preferredDays,
        constraints: constraints.split("\n").map((value) => value.trim()).filter(Boolean),
        free_text_note: freeTextNote,
      });
      const refreshed = await fetchVillage(id, 5_000_000);
      setData(refreshed);
      setEvidenceReviewRevision((revision) => revision + 1);
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
      <header className="topbar"><div className="breadcrumb"><Link href="/">공급계획</Link><span className="breadcrumb-sep">/</span><strong>권역 상세</strong></div><div className="topbar-right"><span className="pre-rnd-pill"><i /> 현장 검증 전</span><span className="avatar">VC</span></div></header>
      <div className="content-page">
        <Link href="/" className="back-link"><ArrowLeft size={15} /> 공급계획으로 돌아가기</Link>
        {error && <div className="alert-box"><CircleHelp size={16} /> {error}</div>}
        {!village && !error && <div className="loading-card"><span className="spinner" /> 권역 근거를 불러오는 중입니다.</div>}
        {village && <>
          <div className="content-hero">
            <div className="eyebrow"><span className="eyebrow-line" /> VILLAGE SERVICE AREA</div>
            <h1>{village.area.name}</h1>
            <p><MapPin size={14} /> 법정동 코드 {village.area.legal_code} · {village.area.county} {village.area.town} · 인구 통계 기준 {village.area.public_data_reference_date}</p>
          </div>
          <section className="content-card">
            <h2>공개 인구 자료 <span className="provenance-badge real">공개 자료</span></h2>
            <div className="village-detail-grid">
              <div className="village-detail-item"><span>전체 인구</span><strong>{village.area.population_total.toLocaleString("ko-KR")}명</strong></div>
              <div className="village-detail-item"><span>65세 이상</span><strong>{village.area.population_65_plus.toLocaleString("ko-KR")}명 · {((village.area.elderly_ratio_65 || 0) * 100).toFixed(1)}%</strong></div>
              <div className="village-detail-item"><span>75세 이상</span><strong>{village.area.population_75_plus.toLocaleString("ko-KR")}명</strong></div>
              <div className="village-detail-item"><span>80세 이상</span><strong>{village.area.population_80_plus.toLocaleString("ko-KR")}명</strong></div>
              <div className="village-detail-item"><span>1인세대</span><strong>{village.area.single_households_total.toLocaleString("ko-KR")}세대</strong></div>
              <div className="village-detail-item"><span>65세 이상 1인세대</span><strong>{village.area.single_households_65_plus.toLocaleString("ko-KR")}세대</strong></div>
              <div className="village-detail-item"><span>공개 시설 집계</span><strong>{village.area.facility_count}곳</strong></div>
              <div className="village-detail-item"><span>주민 요청 기록 <i className="provenance-badge simulated">시연용 모의값</i></span><strong>{village.area.demand_observation_count}건 · 모의값</strong></div>
              <div className="village-detail-item"><span>합성 월간 기준수요 <i className="provenance-badge simulated">시연용 모의값</i></span><strong>{(village.area.baseline_monthly_demand ?? village.area.simulated_monthly_demand).toLocaleString("ko-KR")}회</strong></div>
              {village.area.survey_frequency_floor_monthly !== null && village.area.survey_frequency_floor_monthly !== undefined && <div className="village-detail-item"><span>최근 조사 월 요청빈도 <i className="provenance-badge simulated">조사 입력</i></span><strong>최소 {village.area.survey_frequency_floor_monthly.toLocaleString("ko-KR")}회 · {village.area.survey_frequency_observation_count ?? 0}건</strong></div>}
              <div className="village-detail-item"><span>기존 월간 제공 회차 <i className="provenance-badge">가져온 자료</i></span><strong>{village.area.existing_service_monthly_rounds === null || village.area.existing_service_monthly_rounds === undefined ? village.area.existing_service_status === "STALE" ? "오래된 자료 · 미반영" : "자료 없음 · 확인 필요" : `${village.area.existing_service_monthly_rounds.toLocaleString("ko-KR")}회 · ${village.area.existing_service_program_count ?? 0}개 프로그램`}</strong></div>
              <div className="village-detail-item"><span>추가 계획 검토량 <i className="provenance-badge simulated">계산값</i></span><strong>{village.area.simulated_monthly_demand.toLocaleString("ko-KR")}회</strong>{village.area.existing_service_as_of_date && <small>기존 실적 기준일 {village.area.existing_service_as_of_date}</small>}</div>
            </div>
            <div className="facility-records" aria-live="polite">
              <h3>개별 시설 공개 속성 <span className="provenance-badge real">공개 자료</span></h3>
              {village.facility_detail_status === "AGGREGATE_ONLY" ? (
                <p>현재 원천 스냅샷에는 법정동별 시설 수와 대표 위치만 보존되어 있습니다. 개별 시설 행은 가져오지 않아 목록을 제공하지 않습니다.</p>
              ) : (
                <ul>
                  {village.facilities.map((facility) => (
                    <li key={facility.facility_id}>
                      <strong>{facility.facility_type}</strong>
                      <span>{facility.operating_status || "운영 상태 미확인"} · 위도 {facility.latitude.toFixed(5)}, 경도 {facility.longitude.toFixed(5)}</span>
                      <span>자료 기준일 {facility.source_reference_date} · 데이터셋 {facility.source_dataset_id}</span>
                      {(facility.built_date || facility.floor_area_sqm !== null) && <span>건립 {facility.built_date || "미확인"} · 면적 {facility.floor_area_sqm === null ? "미확인" : `${facility.floor_area_sqm.toLocaleString("ko-KR")}㎡`}</span>}
                    </li>
                  ))}
                </ul>
              )}
              <small>시설명·주소·전화번호·관리자 정보는 저장하거나 표시하지 않습니다.</small>
            </div>
            <p className="source-footnote">시설 집계와 대표 좌표는 공개 마을회관·경로당 원천을 법정동 코드에 연결한 자료입니다. 도로 거리와 시간은 Kakao 경로 응답을 캐시한 실제 도로자료입니다. 추가 계획 검토량은 합성 기준수요와 중앙 신선도 정책상 유효한 조사에서 확인한 월 요청빈도 중 큰 값에서 확인된 기존 제공 회차를 뺍니다. 조사 빈도는 중복 합산하거나 마을 전체로 확대하지 않으며, 미등록·오래된 실적은 0회로 간주하지 않습니다.</p>
          </section>
          <section className="lowdata-explanation">
            <span className="lowdata-icon">?</span>
            <div><strong>{village.evidence.status} · 관측 {village.evidence.observation_count}건 · 조사 {village.evidence.survey_count}건</strong><p>{village.evidence.evidence_reasons.join(" ")}</p><b>필요한 다음 조사: {village.survey_recommendation}</b></div>
          </section>
          <section className="content-card survey-workflow" aria-labelledby="survey-heading">
            <div className="survey-title-row">
              <h2 id="survey-heading">기초조사 등록</h2>
              <span className="provenance-badge simulated">시연용 합성 입력</span>
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
                  <select value={selectedServiceType} onChange={(event) => setServiceType({ areaId: village.area.id, value: event.target.value as SurveyServiceType })}>
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
            {village.surveys.length === 0 ? <p className="survey-empty">아직 등록된 조사가 없습니다.</p> : <div className="survey-history">
              {village.surveys.map((survey) => <article className="survey-history-row" key={survey.survey_id}>
                <div><strong>{surveyTypeLabels[survey.survey_type]} · {serviceLabels[survey.service_type]}</strong><span>{survey.survey_date} · 월 {survey.frequency_per_month ?? "미확인"}회 · {survey.preferred_period || "시기 미확인"}</span></div>
                <span className="provenance-badge simulated">{survey.provenance}</span>
                {survey.free_text_note && <p>{survey.free_text_note}</p>}
              </article>)}
            </div>}
            <EvidenceReviewPanel areaId={village.area.id} refreshKey={evidenceReviewRevision} />
          </section>
          <RecentFeedbackPanel areaId={village.area.id} />
          <section className="content-card">
            <h2><SearchCheck size={16} /> 시나리오별 서비스 배정</h2>
            {(Object.keys(scenarioNames) as ScenarioKey[]).map((key) => {
              const item = village.scenario_assessments[key];
              return <div className="scenario-result-row" key={key}><strong>{scenarioNames[key]} <i className="provenance-badge simulated">시연용 모의 계획</i></strong><span>{item.status} · 월 {item.served_units}/{item.demand_units}회</span><b>{item.cost_won.toLocaleString("ko-KR")}원</b></div>;
            })}
          </section>
          <p className="provenance-footer"><span className="provenance-badge real">공개 자료</span> 법정동·인구·고령인구·1인가구·시설 위치·Kakao 도로 경로 · <span className="provenance-badge simulated">시연용 모의값</span> 요청 기록·필요량·제공자 일정/용량·가격·운영 조건 <Link href="/data-quality">출처 확인 <ArrowLeft size={12} /></Link></p>
        </>}
      </div>
    </main>
  );
}
