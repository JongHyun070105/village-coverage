"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, CircleHelp, Database, MapPinCheckInside, ShieldCheck } from "lucide-react";
import { fetchQuality } from "@/lib/api";
import type { QualityReport } from "@/lib/types";

const fmt = (value: number) => value.toLocaleString("ko-KR");

export default function DataQualityPage() {
  const [report, setReport] = useState<QualityReport | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { fetchQuality().then(setReport).catch((cause) => setError(cause.message)); }, []);
  const metrics = report?.metrics;
  return (
    <main className="page-main">
      <header className="topbar"><div className="breadcrumb"><span>정책 설계</span><span className="breadcrumb-sep">/</span><strong>데이터 출처와 품질</strong></div><div className="topbar-right"><span className="pre-rnd-pill"><i /> PRE-R&amp;D 검증</span><span className="avatar">VC</span></div></header>
      <div className="content-page">
        <div className="content-hero">
          <div className="eyebrow"><span className="eyebrow-line" /> DATA QUALITY &amp; PROVENANCE</div>
          <h1>무슨 데이터로 계산했는지 공개합니다</h1>
          <p>홍성군 장곡면 파일럿의 원본 행 수, 기준월, 법정동 코드 연결 상태를 보여줍니다. 운영 수요와 비용은 실측치가 아니라 시뮬레이션입니다.</p>
        </div>
        {error && <div className="alert-box"><AlertTriangle size={16} /> {error}</div>}
        {metrics && <>
          <div className="quality-grid">
            <div className="quality-stat"><span>인구·가구 코드 연결</span><strong>{Math.round(Number(metrics.pilot_household_join_rate) * 100)}<small>%</small></strong></div>
            <div className="quality-stat"><span>시설 좌표 커버리지</span><strong>{Math.round(Number(metrics.facility_coordinate_coverage) * 100)}<small>%</small></strong></div>
            <div className="quality-stat"><span>좌표 기반 법정리 매핑</span><strong>{Math.round(Number(metrics.facility_reverse_geocode_match_rate) * 100)}<small>%</small></strong></div>
            <div className="quality-stat"><span>세 출처 완전 연결 권역</span><strong>{fmt(Number(metrics.areas_with_population_household_facility))}<small> / {fmt(Number(metrics.pilot_population_area_count))}</small></strong></div>
          </div>

          <section className="content-card">
            <h2><Database size={16} /> 공개 데이터 출처</h2>
            <div className="source-row"><strong>주민등록 인구</strong><p>행정안전부 지역별 법정동 성별·연령별 인구수. 기준 {report?.sources.population_reference_date}. 원본 {fmt(Number(report?.sources.population_rows || 0))}행. 매월 고령인구 구간을 연령별 컬럼 합계로 계산했습니다.</p><span className="source-tag">REAL PUBLIC DATA</span></div>
            <div className="source-row"><strong>1인세대</strong><p>행정안전부 지역별 법정동 성별·연령별 주민등록 1인세대수. 기준 {report?.sources.household_reference_date}. 원본 {fmt(Number(report?.sources.household_rows || 0))}행.</p><span className="source-tag">REAL PUBLIC DATA</span></div>
            <div className="source-row"><strong>마을회관·경로당</strong><p>전국 마을회관 및 경로당 표준데이터. 원본 {fmt(Number(report?.sources.facility_rows || 0))}건 중 파일럿 주소 후보 {fmt(Number(metrics.facility_text_candidates))}건의 좌표를 법정동 코드와 연결했습니다.</p><span className="source-tag">REAL PUBLIC DATA</span></div>
            <div className="source-row"><strong>도로 거리·시간</strong><p>Kakao Mobility의 실제 도로 경로 응답을 SQLite에 저장했습니다. 현재 파일럿은 모든 16×16 방향 경로 240건을 보유합니다.</p><span className="source-tag">REAL PUBLIC DATA</span></div>
            <div className="source-row"><strong>운영 시뮬레이션</strong><p>주민 요청 기록·월간 서비스 필요량·제공자 일정·용량·가격·운영 조건은 고정 seed 2026의 Pre-R&amp;D 모의 입력입니다. 실제 조사나 업체 운영조건이 아닙니다.</p><span className="source-tag simulated">SIMULATED FOR PRE-R&amp;D</span></div>
          </section>

          <section className="content-card">
            <h2><MapPinCheckInside size={16} /> 지리 연결 품질</h2>
            <div className="stat-pairs">
              <div className="stat-pair"><span>파일럿 법정리</span><strong>{fmt(Number(metrics.pilot_population_area_count))}개</strong></div>
              <div className="stat-pair"><span>인구 ↔ 1인세대 조인</span><strong>{fmt(Number(metrics.pilot_household_join_count))}개 / 16개</strong></div>
              <div className="stat-pair"><span>장곡면 시설 좌표</span><strong>{fmt(Number(metrics.facility_coordinate_count))}개 / {fmt(Number(metrics.facility_text_candidates))}개</strong></div>
              <div className="stat-pair"><span>좌표 중복 시설기록</span><strong>{fmt(Number(metrics.facility_records_sharing_coordinates))}건 · 좌표 {fmt(Number(metrics.distinct_facility_coordinates))}곳</strong></div>
              <div className="stat-pair"><span>시설 주소 문자열 단일 매칭</span><strong>{fmt(Number(metrics.facility_addresses_with_one_text_area_match))}건</strong></div>
              <div className="stat-pair"><span>주소 문자열 미매칭</span><strong>{fmt(Number(metrics.facility_addresses_without_text_area_match))}건</strong></div>
            </div>
            <div className="balanced-note"><ShieldCheck size={15} /><span>인구·1인가구 통계는 <b>정확한 10자리 법정동 코드</b>만 조인합니다. 행정리 명칭이 다르다는 이유로 인구를 임의 비율로 나누지 않습니다. Kakao 좌표 역지오코딩으로 66개 시설을 확인했습니다.</span></div>
          </section>

          <div className="alert-box"><AlertTriangle size={16} /><span><strong>공식 인구 배포 파일 범위 제한:</strong> <a href="https://www.data.go.kr/data/15099158/fileData.do" target="_blank" rel="noreferrer">행정안전부 카탈로그</a>의 법정동 지역별 데이터 페이지에서 현재 연결된 CSV는 1개였습니다. 공식 페이지의 범위 설명은 법정동별이지만, 그 단일 다운로드 2,088행은 충청남도만 포함합니다. 다른 지역 파일 선택 또는 다운로드 실패 흔적은 확인되지 않았습니다. 원인이 제공자 업로드인지 게시 설정인지는 확인할 수 없습니다. 1인가구 CSV는 18,624행·16개 시도이며, 인구 파일에 없는 16,536개 코드는 연결하거나 추정하지 않았습니다.</span></div>

          <section className="content-card">
            <h2><CircleHelp size={16} /> 저데이터 보호 정책</h2>
            <p>데모 관측건수는 시뮬레이션 값이며 실측 요청량이 아닙니다. 4건 미만은 “조사 필요”, 4~6건은 “주의”로 표시하고, 낮은 건수를 0 수요로 바꾸지 않습니다. 최적화 입력의 모의 서비스 필요량은 별도 필드로 관리합니다.</p>
            <p>관측 수, 최근성, 출처 다양성, 필수 항목 누락률을 이용한 결정론적 점수를 먼저 계산합니다. AI confidence는 입력돼도 25% 이하 보조 신호로만 반영하며, 5건 미만은 항상 조사 필요로 유지합니다.</p>
            <Link href="/methodology" className="text-link">산정 방법 전체 보기 <ArrowRight size={14} /></Link>
          </section>
          <p className="provenance-footer">품질 보고서 재생성: <code>uv run python scripts/build_demo_data.py</code></p>
        </>}
      </div>
    </main>
  );
}
