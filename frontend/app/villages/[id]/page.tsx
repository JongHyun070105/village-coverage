"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, CircleHelp, MapPin, SearchCheck } from "lucide-react";
import { fetchVillage } from "@/lib/api";
import type { ScenarioKey } from "@/lib/types";

const scenarioNames: Record<ScenarioKey, string> = { efficiency: "효율 우선", balanced: "균형", minimum_coverage: "최소보장" };

export default function VillageDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchVillage>> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (id) fetchVillage(id, 5_000_000).then(setData).catch((cause) => setError(cause.message));
  }, [id]);

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
            <h2>공개 인구 자료</h2>
            <div className="village-detail-grid">
              <div className="village-detail-item"><span>전체 인구</span><strong>{data.area.population_total.toLocaleString("ko-KR")}명</strong></div>
              <div className="village-detail-item"><span>65세 이상</span><strong>{data.area.population_65_plus.toLocaleString("ko-KR")}명 · {((data.area.elderly_ratio_65 || 0) * 100).toFixed(1)}%</strong></div>
              <div className="village-detail-item"><span>75세 이상</span><strong>{data.area.population_75_plus.toLocaleString("ko-KR")}명</strong></div>
              <div className="village-detail-item"><span>80세 이상</span><strong>{data.area.population_80_plus.toLocaleString("ko-KR")}명</strong></div>
              <div className="village-detail-item"><span>1인세대</span><strong>{data.area.single_households_total.toLocaleString("ko-KR")}세대</strong></div>
              <div className="village-detail-item"><span>65세 이상 1인세대</span><strong>{data.area.single_households_65_plus.toLocaleString("ko-KR")}세대</strong></div>
              <div className="village-detail-item"><span>시설 앵커 기록</span><strong>{data.area.facility_count}곳</strong></div>
              <div className="village-detail-item"><span>서비스 수요</span><strong>시뮬레이션 전용</strong></div>
            </div>
          </section>
          <section className="lowdata-explanation">
            <span className="lowdata-icon">?</span>
            <div><strong>{data.evidence.status} · 관측 {data.evidence.observation_count}건</strong><p>{data.evidence.evidence_reasons.join(" ")}</p><b>필요한 다음 조사: {data.survey_recommendation}</b></div>
          </section>
          <section className="content-card">
            <h2><SearchCheck size={16} /> 시나리오별 서비스 배정</h2>
            {(Object.keys(scenarioNames) as ScenarioKey[]).map((key) => {
              const item = data.scenario_assessments[key];
              return <div className="scenario-result-row" key={key}><strong>{scenarioNames[key]}</strong><span>{item.status} · {item.served_units}/{item.demand_units}회 · {item.beneficiaries}명</span><b>{item.cost_won.toLocaleString("ko-KR")}원</b></div>;
            })}
          </section>
          <p className="provenance-footer">실제 행정 통계와 시뮬레이션된 운영 수요를 분리해서 해석해 주세요. <Link href="/data-quality">출처 확인 <ArrowLeft size={12} /></Link></p>
        </>}
      </div>
    </main>
  );
}
