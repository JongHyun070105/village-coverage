"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, CircleHelp, Database, FileCheck2, Store, Upload } from "lucide-react";
import { fetchPilotSetupReadiness, fetchRegions, type PilotSetupReadiness } from "@/lib/api";
import type { RegionOption } from "@/lib/types";

const statusLabel: Record<string, string> = {
  READY: "확인됨",
  MISSING: "자료 없음",
  LIMITED: "제한적",
  REVIEW_REQUIRED: "검토 필요",
  NEEDS_SELECTION: "지역 선택 필요",
};

export default function PilotSetupPage() {
  const [regions, setRegions] = useState<RegionOption[]>([]);
  const [selectedRegion, setSelectedRegion] = useState("");
  const [areaCode, setAreaCode] = useState("");
  const [serviceType, setServiceType] = useState("laundry");
  const [readiness, setReadiness] = useState<PilotSetupReadiness | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchRegions().then((result) => {
      setRegions(result.regions);
      setSelectedRegion(result.regions[0]?.county ?? "");
    }).catch((cause: Error) => setError(cause.message));
  }, []);

  useEffect(() => {
    fetchPilotSetupReadiness(serviceType, areaCode || undefined, selectedRegion || undefined)
      .then(setReadiness)
      .catch((cause: Error) => setError(cause.message));
  }, [serviceType, areaCode, selectedRegion]);

  const start = async () => {
    setError("");
    try {
      setReadiness(await fetchPilotSetupReadiness(
        serviceType,
        areaCode || undefined,
        selectedRegion || undefined,
      ));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "준비도를 불러오지 못했습니다.");
    }
  };

  return (
    <main className="page-main">
      <header className="topbar"><div className="breadcrumb"><span>업무 시작</span><span className="breadcrumb-sep">/</span><strong>파일럿 초기 설정</strong></div><span className="pre-rnd-pill"><i /> 데모 계획 데이터</span></header>
      <div className="content-page">
        <div className="content-hero">
          <div className="eyebrow"><span className="eyebrow-line" /> PILOT SETUP</div>
          <h1>지역 파일럿 준비 현황</h1>
          <p>기초자료, 주민 근거, 공급조건에서 빠진 항목을 확인합니다. 자료가 부족하면 임의 숫자 대신 부족 상태를 그대로 표시합니다.</p>
        </div>
        <div className="balanced-note"><CircleHelp size={16} /><span>이 화면은 파일럿 입력의 준비 상태를 보여줍니다. 현재 계획 생성은 기존 데모 시뮬레이션 입력을 사용하며, 파일럿 import를 계획 엔진에 자동 합치지 않습니다. 실제 파일럿 계획으로 사용하기 전에 해당 연결과 지역별 근거 검증이 필요합니다.</span></div>

        {error && <div className="alert-box" role="alert">{error}</div>}
        <section className="content-card pilot-setup-form" aria-labelledby="pilot-region-heading">
          <h2 id="pilot-region-heading"><Database size={16} /> 1. 지역·서비스 선택</h2>
          <label htmlFor="pilot-region">지역</label>
          <select id="pilot-region" value={selectedRegion} onChange={(event) => setSelectedRegion(event.target.value)}>
            {regions.map((region) => <option key={region.region_id} value={region.county}>{region.province} {region.county} {region.town}</option>)}
          </select>
          <label htmlFor="pilot-area-code">법정동 코드 (자료 조회 시 선택)</label>
          <input id="pilot-area-code" inputMode="numeric" pattern="[0-9]{10}" maxLength={10} value={areaCode} onChange={(event) => setAreaCode(event.target.value.replace(/\D/g, "").slice(0, 10))} placeholder="10자리 법정동 코드" />
          <label htmlFor="pilot-service">서비스 유형</label>
          <select id="pilot-service" value={serviceType} onChange={(event) => setServiceType(event.target.value)}>
            <option value="laundry">세탁</option><option value="daily_necessities">생활필수품</option><option value="home_repair">간단 집수리</option>
          </select>
          <button type="button" className="secondary-button" onClick={start}>현재 준비도 다시 확인</button>
        </section>

        {readiness && <>
          <section className="content-card" aria-labelledby="pilot-steps-heading">
            <h2 id="pilot-steps-heading">초기 설정 업무 흐름</h2>
            <ol className="pilot-steps">{readiness.steps.map((step) => <li key={step.step}><span className="pilot-step-number">{step.step}</span><div><strong>{step.label}</strong><span>{statusLabel[step.status] ?? step.status}</span></div></li>)}</ol>
          </section>

          <section className="content-card" aria-labelledby="pilot-readiness-heading">
            <h2 id="pilot-readiness-heading">자료 준비 상태</h2>
            <p>현재 import workspace 전체 기준입니다. 지역 선택은 추후 실제 지자체 자료 계약과 연결해야 합니다.</p>
            <div className="pilot-dimension-list">{readiness.dimensions.map((item) => <div className="pilot-dimension" key={item.id}><strong>{item.label}</strong><span>{statusLabel[item.status] ?? item.status}</span><small>{item.records.toLocaleString("ko-KR")}행{item.detail ? ` · ${item.detail}` : ""}</small></div>)}</div>
          </section>

          <section className="content-card" aria-labelledby="calibration-heading">
            <h2 id="calibration-heading">지역 보정 준비도 · {readiness.calibration.status}</h2>
            <p>이 상태는 준비도 판정입니다. 모델 입력을 자동 보정하지 않습니다. 행 수만으로 승격하지 않으며 unique observation, 기간, 분모, 표본 완결성, 출처 다양성, 신선도와 충돌을 함께 확인합니다.</p>
            <ul>{readiness.calibration.missing_requirements.map((item) => <li key={item}>수요 보정 조건 미충족: {item}</li>)}{readiness.calibration.operational_missing_requirements.map((item) => <li key={item}>운영 검증 조건 미충족: {item}</li>)}</ul>
            <Link className="text-link" href="/methodology">보정 기준 자세히 보기 <ArrowRight size={14} /></Link>
          </section>
        </>}

        <section className="content-card pilot-setup-actions" aria-label="다음 작업">
          <Link className="primary-button" href="/pilot-imports"><Upload size={16} /> 파일럿 CSV 검토하기</Link>
          <Link className="secondary-button" href="/providers"><Store size={16} /> 공급자 디렉터리 확인</Link>
          <Link className="secondary-button" href="/plans"><FileCheck2 size={16} /> 기존 계획 검토</Link>
        </section>
        <p className="provenance-footer">파일럿 import 기록은 출처·batch·row fingerprint를 보존합니다. 실제 수행성과, 운영가능성, 지자체 승인 또는 실증 결과로 해석할 수 없습니다.</p>
      </div>
    </main>
  );
}
