"use client";

import { useState } from "react";
import { ArrowRight, Check, CircleHelp, LockKeyhole, WandSparkles } from "lucide-react";
import { structureDemand } from "@/lib/api";

const sample = "장곡면 어르신들은 겨울에 세탁 서비스가 필요하고, 병원 가는 화요일은 피했으면 좋겠다고 함. 월 2회 요청.";
const labels: Record<string, string> = {
  laundry: "세탁", daily_necessities: "생필품", home_repair: "주거 수리",
  mobility_support: "이동 지원", unknown: "서비스 확인 필요",
};
const dayLabels: Record<string, string> = {
  monday: "월요일", tuesday: "화요일", wednesday: "수요일", thursday: "목요일",
  friday: "금요일", saturday: "토요일", sunday: "일요일",
};

export default function DemandPage() {
  const [text, setText] = useState(sample);
  const [result, setResult] = useState<Awaited<ReturnType<typeof structureDemand>> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await structureDemand(text));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "구조화 요청에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page-main">
      <header className="topbar"><div className="breadcrumb"><span>정책 설계</span><span className="breadcrumb-sep">/</span><strong>주민 요청 구조화</strong></div><div className="topbar-right"><span className="pre-rnd-pill"><i /> PRE-R&amp;D 검증</span><span className="avatar">VC</span></div></header>
      <div className="content-page">
        <div className="content-hero">
          <div className="eyebrow"><span className="eyebrow-line" /> AI STRUCTURING DEMO</div>
          <h1>전화·회의 기록을 계획에 쓸 수 있게</h1>
          <p>AI는 주민 메모에서 서비스 종류와 시기·빈도·제약을 구조화합니다. 경로와 예산 배분은 별도의 최적화 엔진이 계산합니다.</p>
        </div>
        <div className="demand-layout">
          <section className="content-card">
            <h2>주민 요청 메모</h2>
            <form onSubmit={submit}>
              <textarea className="demand-textarea" value={text} onChange={(event) => setText(event.target.value)} maxLength={10000} aria-label="주민 요청 메모 입력" placeholder="예: 겨울철 세탁 서비스를 월 2회 원하고, 병원 방문일은 피하고 싶다고 함." />
              <div className="demand-actions"><span>민감정보는 알려진 패턴을 마스킹하며, 입력 원문은 저장하지 않습니다.</span><button type="submit" className="button button-dark" disabled={loading || !text.trim()}><WandSparkles size={15} /> {loading ? "구조화 중…" : "요청 구조화"}</button></div>
            </form>
            {error && <div className="request-warning">{error}</div>}
            {result && <div className="request-card" aria-live="polite">
              <strong>구조화 결과 <span className="pill">{result.method === "gemini_structured_output" ? "Gemini Structured Output" : "규칙 기반 안전 대체"}</span></strong>
              {result.requests.length ? result.requests.map((request, index) => (
                <div key={`${request.service_type}-${index}`} className="request-card">
                  <div className="request-fields">
                    <span>서비스: {labels[request.service_type] || request.service_type}</span>
                    {request.requested_period && <span>시기: {request.requested_period === "winter" ? "겨울" : request.requested_period === "summer" ? "여름" : request.requested_period}</span>}
                    {request.frequency_per_month !== null && <span>빈도: 월 {request.frequency_per_month}회</span>}
                    {request.preferred_days.map((day) => <span key={day}>희망: {dayLabels[day] || day}</span>)}
                    {request.excluded_days.map((day) => <span key={day}>제외: {dayLabels[day] || day}</span>)}
                    {request.constraints.map((constraint) => <span key={constraint}>제약: {constraint}</span>)}
                  </div>
                </div>
              )) : <p>명확한 서비스 요청을 찾지 못했습니다.</p>}
              <div className={result.needs_followup_survey ? "request-warning" : "balanced-note"}>
                {result.needs_followup_survey ? <CircleHelp size={15} /> : <Check size={15} />}
                <span>{result.needs_followup_survey ? result.followup_reason || "추가 확인이 필요합니다." : "구조화 결과를 확인한 뒤 담당자가 최종 승인해야 합니다."}</span>
              </div>
              {result.confidence !== null && <p className="privacy-confirm">AI 구조화 확신도 {Math.round(result.confidence * 100)}% · 추출 초안의 보조 신호이며 실제 수요 증거를 뜻하지 않습니다.</p>}
              <div className="request-warning">
                <CircleHelp size={15} />
                <span>현재 입력은 기록 {result.evidence_assessment.observation_count}건입니다. 증거 충분도: {result.evidence_assessment.status} · 결정론 점수 {Math.round(result.evidence_assessment.deterministic_confidence * 100)}%. 단일 메모만으로 권역 전체 수요를 확정하지 않습니다.</span>
              </div>
              {result.source_text_was_redacted && <p className="privacy-confirm"><LockKeyhole size={13} /> 개인정보 패턴을 마스킹해 외부 AI에 전달하지 않았습니다.</p>}
            </div>}
          </section>
          <aside>
            <section className="content-card">
              <h2>구조화 범위</h2>
              <div className="service-steps">
                <div className="service-step"><span className="step-no">01</span><strong>서비스 종류</strong><p>세탁·생필품·주거수리·이동지원</p></div>
                <div className="service-step"><span className="step-no">02</span><strong>시기와 빈도</strong><p>명시된 계절, 월 요청 횟수</p></div>
                <div className="service-step"><span className="step-no">03</span><strong>시간 제약</strong><p>희망 요일, 제외 요일, 추가 확인</p></div>
              </div>
            </section>
            <section className="content-card privacy-card">
              <h2><LockKeyhole size={16} /> 데이터 보호</h2>
              <p>휴대전화·이메일·식별번호와 일부 호칭 패턴을 검사합니다. 마스킹된 입력은 원문을 저장하지 않고 안전한 규칙 기반 구조화로 처리합니다.</p>
              <p>Gemini는 JSON schema를 따르는 초안만 반환하며, 모호한 요청이나 서로 다른 빈도 표현은 담당자 확인 대상으로 남깁니다.</p>
              <p>LLM confidence는 수요 사실로 간주하지 않으며, 서비스 경로를 생성하지 않습니다.</p>
            </section>
            <section className="content-card">
              <h2>예시 문장</h2>
              <button className="sample-prompt" onClick={() => { setText(sample); setResult(null); }}>겨울철 세탁 서비스를 월 2회 제공하고 화요일은 피하고 싶다고 함 <ArrowRight size={14} /></button>
              <button className="sample-prompt" onClick={() => { setText("마을회의 내용: 다음 회의는 다음 달 첫째 주에 다시 논의하기로 함."); setResult(null); }}>수요 표현이 없는 회의 기록 <ArrowRight size={14} /></button>
              <button className="sample-prompt" onClick={() => { setText("세탁 서비스를 월 2회로 원함. 다른 분은 월 4회를 요청함."); setResult(null); }}>서로 다른 빈도 요청 <ArrowRight size={14} /></button>
            </section>
          </aside>
        </div>
      </div>
    </main>
  );
}
