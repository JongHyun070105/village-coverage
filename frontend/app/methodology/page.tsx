import Link from "next/link";
import { ArrowRight, CircleHelp, Route, Scale, ShieldCheck } from "lucide-react";
import ForecastBacktestPanel from "@/components/forecast-backtest-panel";

const PUBLIC_DEMO_MODE = process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true";

const scenarios = [
  { name: "효율 우선", key: "A", text: "서비스 횟수를 늘리면서 공급가와 왕복 도로 이동비를 예산 제약에 넣습니다. 가까운 권역이나 운영비가 낮은 서비스가 더 선택될 수 있습니다." },
  { name: "균형", key: "B", text: "같은 예산에서 가능한 월간 서비스 회차와 권역 수를 우선하고, 조사 필요·취약성·장기 서비스 공백을 반영합니다. 그 뒤 권역별 필요량 대비 배정 집중도와 이동비를 낮춥니다. 각 0~100% 취약성 신호에는 각각 최대 500점을 줍니다." },
  { name: "소외 최소화", key: "C", text: "입력된 서비스 공백 이력에서 장기·만성 미수혜 권역을 먼저 고려하고, 그다음 서비스 권역 수와 총 회차를 비교합니다. 이력이 없거나 불확실한 권역은 소외로 단정하지 않습니다." },
  { name: "최소 서비스 보장", key: "D", text: "담당자가 정한 권역별 월 최소 회차 목표(기본 1회)를 달성하는 권역 수를 우선 늘립니다. 예산·수요·공급·경로 조건에 따라 목표에 못 미치는 권역이 남을 수 있으며, 별도 필요예산 계산도 불가능하거나 최적성이 확인되지 않으면 금액을 제시하지 않습니다." },
];

export default function MethodologyPage() {
  return (
    <main className="page-main">
      <header className="topbar"><div className="breadcrumb"><span>정책 설계</span><span className="breadcrumb-sep">/</span><strong>기획 방법</strong></div><div className="topbar-right"><span className="pre-rnd-pill"><i /> 현장 검증 전</span><span className="avatar">VC</span></div></header>
      <div className="content-page">
        <div className="content-hero">
          <div className="eyebrow"><span className="eyebrow-line" /> 산정 기준</div>
          <h1>AI는 기록을 정리하고, 최적화는 비용을 계산합니다</h1>
          <p>적은 요청 기록을 낮은 수요로 오해하지 않으면서, 예산과 형평성 사이 선택의 결과를 숨김없이 보여줍니다.</p>
        </div>
        <ForecastBacktestPanel />
        <div className="method-principle-grid">
          <section className="content-card principle-card"><span className="principle-icon"><CircleHelp size={18} /></span><h2>저데이터 보호</h2><p>요청 기록이 적으면 “수요 없음”으로 처리하지 않습니다. 불확실성을 표시하고 전화·회의 확인을 제안합니다.</p></section>
          <section className="content-card principle-card"><span className="principle-icon blue"><Route size={18} /></span><h2>{PUBLIC_DEMO_MODE ? "직선거리 기반 이동 모델 추정" : "도로 경로 기반 이동비 추정"}</h2><p>{PUBLIC_DEMO_MODE ? "공개 데모는 외부 길찾기 API 없이 공개 좌표로 직선거리 × 1.3, 고정 속도로 이동을 추정합니다. 실제 도로 경로·시간·운행 비용이 아닙니다." : "Kakao Mobility의 방향별 도로 거리와 시간을 SQLite에 캐시해 비교합니다. 직선거리로 대신 계산하지 않으며, 이 값은 실제 운행 비용이나 확정 경로가 아닙니다."}</p></section>
          <section className="content-card principle-card"><span className="principle-icon amber"><Scale size={18} /></span><h2>비용을 투명하게</h2><p>공급가와 이동비를 따로 보여주고, 선택한 최소 회차 기준을 충족하는 데 필요한 예산은 조건이 가능하고 최적성이 증명된 경우에 계산합니다.</p></section>
        </div>
        <section className="content-card">
          <h2>네 가지 계획 시나리오</h2>
          {scenarios.map((item) => <div className="scenario-method" key={item.key}><span>{item.key}</span><div><strong>{item.name}</strong><p>{item.text}</p></div></div>)}
        </section>
        <section className="content-card">
          <h2>공급자 일정의 균형 점수</h2>
          <p>공급자 일정의 균형안은 각 항목을 10,000점 기준으로 정규화해 회차 63, 권역 범위 27, 조사 필요 보호 5, 취약성 3, 권역별 집중도 1, 이동비 1의 기본 비중으로 합산합니다. {PUBLIC_DEMO_MODE ? "이 공개 데모에서 이동비는 직선거리 기반 MODEL ESTIMATE를 사용합니다." : "실제 도로 이동비는 Kakao 경로 캐시를 사용합니다."} 조사 보호는 조사 필요 보호 가중치/1,000, 취약성은 고령인구와 고령 1인가구 가중치 합계(최대 1,000)/1,000만큼 해당 기본 비중을 조정합니다. 기본 비중과 계획을 만들 때 선택한 세 정책 입력값을 저장 일정에 함께 기록합니다. 이 점수는 담당자가 선택한 정책 규칙이며 AI 권고가 아닙니다.</p>
        </section>
        <section className="content-card">
          <h2>자료의 실제·모의 구분</h2>
          <div className="provenance-grid">
            <div><span className="provenance-badge real">공개 자료</span><strong>법정동 코드·주민등록 인구·고령 인구·1인세대</strong><p>행정안전부 공개 파일을 정확한 법정동 코드로 연결했습니다. 시설 좌표는 마을회관·경로당 공개 위치입니다. {PUBLIC_DEMO_MODE ? "이동거리는 공개 좌표로 생성한 직선거리 MODEL ESTIMATE입니다." : "이동거리는 Kakao 도로 경로 캐시입니다."}</p></div>
            <div><span className="provenance-badge simulated">시연용 모의값</span><strong>주민 요청·서비스 필요량·제공자 일정과 용량</strong><p>서비스 가격과 운영 조건도 모의 입력입니다. 결과는 월간 배정 계획의 시뮬레이션이며 실제 수요나 실제 이용 주민 수를 뜻하지 않습니다.</p></div>
          </div>
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
            <li>서비스 단가와 운영조건은 실측이 아닌 Pre-R&amp;D 가정입니다. 실제 이용 주민 수는 산정하지 않습니다. 예산은 지역 업체 견적 조사 후 다시 설정해야 합니다.</li>
            <li>교통시간은 요청 시점의 추천 경로 요약이며, 반복 운행의 실제 정차 순서나 계절별 도로 상황을 나타내지 않습니다.</li>
            <li>균형 시나리오의 우선순위와 취약성 점수는 실증연구로 보정되지 않은 공개 정책 선택입니다. 실제 효과를 입증하는 결과가 아닙니다.</li>
            <li>시뮬레이션은 공공 정책 결정을 대신하지 않습니다. 저데이터 지역은 기초조사 후 재계산해야 합니다.</li>
          </ul>
          <Link href="/data-quality" className="text-link">데이터 출처와 품질 지표 보기 <ArrowRight size={14} /></Link>
        </section>
      </div>
    </main>
  );
}
