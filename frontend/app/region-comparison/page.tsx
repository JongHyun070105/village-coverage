"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, BarChart3, CircleHelp, Users } from "lucide-react";
import { fetchRegionComparison } from "@/lib/api";
import type { RegionComparison, RegionComparisonReport } from "@/lib/types";

const number = (value: number) => value.toLocaleString("ko-KR");
const money = (value: number) => `${number(value)}원`;
const percent = (value: number) => `${(value * 100).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`;

const LICENSE_LABELS: Record<string, string> = {
  DETAIL_AVAILABLE: "시설 상세 공개 이용허락 확인",
  AGGREGATE_ONLY: "집계 자료만 제공",
  LICENSE_RESTRICTED: "이용허락 제한",
  LICENSE_UNKNOWN: "이용허락 확인 불가",
};

const COVERAGE_LABELS: Record<string, string> = {
  MET_WITHIN_REFERENCE_BUDGET: "기준 예산에서 최소 회차 충족",
  MONEY_SHORTAGE: "예산 부족 가능성",
  PROVIDER_CAPACITY_SHORTAGE: "공급 용량 부족",
  NOT_VERIFIABLE: "계산 확인 불가",
};

function RegionCard({ region }: { region: RegionComparison }) {
  const real = region.public_statistics;
  const normalized = region.normalized_indicators;
  const ops = region.operational_estimates;
  const coverage = ops.minimum_coverage;
  const statusLabel = COVERAGE_LABELS[coverage.status] ?? coverage.status;

  return (
    <article className="region-comparison-card" aria-label={`${region.region_name} 비교 지표`}>
      <header className="region-comparison-card-header">
        <div>
          <span className="region-comparison-eyebrow">{number(region.area_count)}개 서비스 권역</span>
          <h2>{region.region_name}</h2>
        </div>
        <span className={`coverage-screen-status ${coverage.status === "NOT_VERIFIABLE" ? "unknown" : ""}`}>
          {statusLabel}
        </span>
      </header>

      <section className="comparison-metric-group" aria-label="실제 공공통계">
        <div className="comparison-group-heading"><span>REAL</span><strong>공공 통계</strong></div>
        <dl className="comparison-metrics-grid">
          <div><dt>인구</dt><dd>{number(real.population_total)}명</dd></div>
          <div><dt>고령 인구 비율</dt><dd>{percent(real.elderly_ratio)}</dd></div>
          <div><dt>65세 이상 인구</dt><dd>{number(real.population_65_plus)}명</dd></div>
          <div><dt>고령 1인가구</dt><dd>{number(real.single_households_65_plus)}세대</dd></div>
          <div><dt>권역당 평균 인구</dt><dd>{number(normalized.population_per_area)}명</dd></div>
          <div><dt>고령 1인가구 / 인구 1,000명</dt><dd>{number(normalized.single_elderly_per_1000_pop)}세대</dd></div>
          <div><dt>시설 집계</dt><dd>{number(real.facility_count)}곳 · 권역당 {normalized.facilities_per_area}</dd></div>
          <div><dt>시설 이용허락</dt><dd>{LICENSE_LABELS[real.facility_licensing_status] ?? real.facility_licensing_status}</dd></div>
        </dl>
      </section>

      <section className="comparison-metric-group simulated" aria-label="시뮬레이션 지표">
        <div className="comparison-group-heading"><span>시연용 모의값</span><strong>운영 가정과 사전 점검</strong></div>
        <dl className="comparison-metrics-grid">
          <div><dt>월간 모의 수요</dt><dd>{number(ops.simulated_monthly_demand_units)}단위</dd></div>
          <div><dt>조사 필요 권역</dt><dd>{number(ops.survey_required_areas_count)}곳 · {percent(ops.survey_required_ratio)}</dd></div>
          <div><dt>데이터 충분</dt><dd>{number(ops.data_sufficiency_breakdown.SUFFICIENT)}곳</dd></div>
          <div><dt>제한적 / 조사 필요</dt><dd>{number(ops.data_sufficiency_breakdown.LIMITED)}곳 / {number(ops.data_sufficiency_breakdown.SURVEY_REQUIRED)}곳</dd></div>
          <div><dt>권역 공간 분산 참고</dt><dd>{ops.route_spatial_spread_km.toFixed(2)}km</dd></div>
          <div><dt>모의 공급자 / 월간 용량</dt><dd>{coverage.provider_count}곳 / {coverage.available_capacity === null ? "확인 불가" : `${number(coverage.available_capacity)}단위`}</dd></div>
          <div><dt>최소 서비스 회차</dt><dd>{coverage.required_capacity === null ? "확인 불가" : `${number(coverage.required_capacity)}회`}</dd></div>
          <div><dt>공급 용량 부족분</dt><dd>{coverage.missing_capacity === null || coverage.missing_capacity === undefined ? "확인 불가" : `${number(coverage.missing_capacity)}회`}</dd></div>
          <div className="comparison-metric-wide">
            <dt>최소 서비스 예산</dt>
            <dd>{coverage.required_budget_won === null ? "계산 확인 불가" : money(coverage.required_budget_won)}</dd>
            {coverage.budget_gap_won !== null && coverage.budget_gap_won > 0 && <small>기준 예산보다 {money(coverage.budget_gap_won)} 추가 필요</small>}
          </div>
        </dl>
        <p className="coverage-screen-note">
          {coverage.status === "PROVIDER_CAPACITY_SHORTAGE"
            ? "공급 용량 제약은 예산 증액만으로 해결되지 않습니다."
            : coverage.status === "MONEY_SHORTAGE"
              ? "공급 조건을 고정한 월간 집계 모델에서 예산 차이를 계산했습니다."
              : coverage.minimum_coverage_met === true
                ? "월간 집계 모델에서 기준 예산 안에 최소 회차를 배정했습니다."
                : "현재 결과로 최소 회차 달성 여부를 확인하지 못했습니다."}
        </p>
        <small className="comparison-scope">모델 범위: {coverage.scope === "MONTHLY_AGGREGATE_CAPACITY_ESTIMATE" ? "월간 집계·중앙 거점 왕복 비용 추정" : coverage.scope}. 요일별 운영 시간과 다중 경유 경로는 반영하지 않습니다.</small>
      </section>
    </article>
  );
}

export default function RegionComparisonPage() {
  const [report, setReport] = useState<RegionComparisonReport | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchRegionComparison().then(setReport).catch((cause) => {
      setError(cause instanceof Error ? cause.message : "지역 비교를 불러오지 못했습니다.");
    });
  }, []);

  return (
    <main className="page-main">
      <header className="topbar">
        <div className="breadcrumb"><span>정책 설계</span><span className="breadcrumb-sep">/</span><strong>지역 비교</strong></div>
        <div className="topbar-right"><span className="pre-rnd-pill"><i /> 현장 검증 전</span></div>
      </header>
      <div className="content-page region-comparison-page">
        <div className="content-hero">
          <div className="eyebrow"><span className="eyebrow-line" /> 지역별 조건 비교</div>
          <h1>세 시범 지역의 조건을 나란히 봅니다</h1>
          <p>지역을 순위로 평가하지 않습니다. 공공 통계와 시뮬레이션 운영 가정을 구분해 규모와 공급 여건을 비교합니다.</p>
        </div>

        <div className="comparison-provenance-note">
          <BarChart3 size={17} />
          <span><b>공개 자료</b> 인구·가구·시설 통계 · <b>시연용 모의값</b> 서비스 수요·공급자·예산 점검</span>
          <Link href="/data-quality">출처와 품질 <ArrowLeft size={13} /></Link>
        </div>

        {error && <div className="alert-box"><AlertTriangle size={16} />{error}</div>}
        {!report && !error && <div className="content-card comparison-loading"><Users size={18} /> 지역별 공개 통계와 모의 공급 조건을 불러오는 중입니다.</div>}
        {report && <>
          <div className="comparison-report-summary"><strong>{report.total_regions}개 지역</strong><span>{number(report.total_areas)}개 서비스 권역</span><span>서열화 없이 지표별로 비교</span></div>
          <div className="region-comparison-grid">
            {report.regions.map((region) => <RegionCard key={region.region_id} region={region} />)}
          </div>
          <section className="comparison-method-note">
            <CircleHelp size={16} />
            <div>
              <strong>비교 결과를 읽는 방법</strong>
              <p>시설 이용허락 상태가 집계 전용인 지역의 시설 정보는 개별 시설 상세로 제공하지 않습니다. 공간 분산 값은 권역 좌표의 참고 지표이며 실제 도로 이동거리나 시간을 뜻하지 않습니다.</p>
              <p>최소 서비스 비용과 용량은 고정된 시뮬레이션 입력을 월간 집계한 참고 계획입니다. 실측 수요, 확정 공급 약속, 요일별 일정의 실행 가능성을 의미하지 않습니다.</p>
            </div>
          </section>
        </>}
      </div>
    </main>
  );
}
