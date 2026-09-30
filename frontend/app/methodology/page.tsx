import Link from "next/link";
import { ArrowRight, CircleHelp, Route, Scale, ShieldCheck } from "lucide-react";

const scenarios = [
  { name: "효율 우선", key: "A", text: "서비스 횟수를 늘리면서 공급가와 왕복 도로 이동비를 예산 제약에 넣습니다. 가까운 권역이나 운영비가 낮은 서비스가 더 선택될 수 있습니다." },
  { name: "균형", key: "B", text: "효율 점수에 65세 이상 인구 비율, 고령 1인가구 비율, 조사 필요 신호를 가중치로 반영합니다. 저데이터 기록은 수요가 적다는 근거로 취급하지 않습니다." },
  { name: "최소보장", key: "C", text: "각 법정리 권역에 월 1회 서비스를 우선 배정합니다. 예산이 부족하면 달성하지 못한 권역을 그대로 표시하고, 모든 권역에 필요한 최소 예산과 현재 부족액을 계산합니다." },
];

export default function MethodologyPage() {
  return (
    <main className="page-main">
      <header className="topbar"><div className="breadcrumb"><span>정책 설계</span><span className="breadcrumb-sep">/</span><strong>기획 방법</strong></div><div className="topbar-right"><span className="pre-rnd-pill"><i /> PRE-R&amp;D 검증</span><span className="avatar">VC</span></div></header>
      <div className="content-page">
        <div className="content-hero">
          <div className="eyebrow"><span className="eyebrow-line" /> METHODOLOGY</div>
          <h1>AI는 기록을 정리하고, 최적화는 비용을 계산합니다</h1>
          <p>적은 요청 기록을 낮은 수요로 오해하지 않으면서, 예산과 형평성 사이 선택의 결과를 숨김없이 보여줍니다.</p>
        </div>
        <div className="method-principle-grid">
          <section className="content-card principle-card"><span className="principle-icon"><CircleHelp size={18} /></span><h2>저데이터 보호</h2><p>요청 기록이 적으면 “수요 없음”으로 처리하지 않습니다. 불확실성을 표시하고 전화·회의 확인을 제안합니다.</p></section>
          <section className="content-card principle-card"><span className="principle-icon blue"><Route size={18} /></span><h2>실제 도로 비용</h2><p>Kakao Mobility의 방향별 도로 거리와 시간을 SQLite에 캐시합니다. 직선거리 추정은 서비스 경로 비용에 사용하지 않습니다.</p></section>
          <section className="content-card principle-card"><span className="principle-icon amber"><Scale size={18} /></span><h2>비용을 투명하게</h2><p>공급가와 이동비를 따로 보여주고, 월 최소 서비스를 모든 마을에 보장하는 데 필요한 예산도 계산합니다.</p></section>
        </div>
        <section className="content-card">
          <h2>세 가지 계획 시나리오</h2>
          {scenarios.map((item) => <div className="scenario-method" key={item.key}><span>{item.key}</span><div><strong>{item.name}</strong><p>{item.text}</p></div></div>)}
        </section>
        <section className="content-card">
          <h2>최적화 계산 흐름</h2>
          <div className="service-steps">
            <div className="service-step"><span className="step-no">01</span><strong>법정리 권역</strong><p>법정동 코드로 인구·1인세대를 연결하고 시설 좌표를 서비스 앵커로 삼습니다.</p></div>
            <div className="service-step"><span className="step-no">02</span><strong>운영 시뮬레이션</strong><p>고정 seed로 모의 수요, 제공 가능량, 가격을 만듭니다. 실측으로 표현하지 않습니다.</p></div>
            <div className="service-step"><span className="step-no">03</span><strong>CP-SAT 배정</strong><p>예산, 모의 공급자 수용량, 권역별 필요량, 도로 이동비를 반영해 월간 단위를 배정합니다.</p></div>
          </div>
        </section>
        <section className="content-card">
          <h2><ShieldCheck size={16} /> 결과 해석과 한계</h2>
          <ul>
            <li>서비스 단가와 모의 수혜 인원은 실측이 아닌 Pre-R&amp;D 가정입니다. 예산은 지역 업체 견적 조사 후 다시 설정해야 합니다.</li>
            <li>교통시간은 요청 시점의 추천 경로 요약이며, 반복 운행의 실제 정차 순서나 계절별 도로 상황을 나타내지 않습니다.</li>
            <li>균형 시나리오의 가중치는 실증연구로 보정되지 않았습니다. 담당자가 가중치를 공개적으로 조정하도록 설계했습니다.</li>
            <li>시뮬레이션은 공공 정책 결정을 대신하지 않습니다. 저데이터 지역은 기초조사 후 재계산해야 합니다.</li>
          </ul>
          <Link href="/data-quality" className="text-link">데이터 출처와 품질 지표 보기 <ArrowRight size={14} /></Link>
        </section>
      </div>
    </main>
  );
}
