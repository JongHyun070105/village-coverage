"use client";

import { useCallback, useEffect, useState } from "react";
import { BookOpenText, Database, Info, ShieldAlert } from "lucide-react";
import { ApiErrorNotice } from "@/components/api-error";
import { ProvenanceBadge, type ProvenanceKind } from "@/components/provenance-badge";
import { count, koreanDate, percent } from "@/lib/format";
import {
  fetchEvidencePriors,
  fetchEvidenceSources,
  fetchHomeDoctor,
  fetchKosis,
  SERVICE_LABELS_V4,
  type KosisTable,
  type PriorsPayload,
  type SourceEntry,
} from "@/lib/v4";

const REALITY_LABEL: Record<string, string> = { REAL: "실제", REFERENCE: "참고", SIMULATED: "모의" };
const ROLE_TO_BADGE: Record<string, ProvenanceKind> = {
  PUBLIC_DATA: "PUBLIC_DATA",
  EXTERNAL_EMPIRICAL_PRIOR: "EXTERNAL_EMPIRICAL",
  EXTERNAL_CONTEXT: "EXTERNAL_EMPIRICAL",
  EXTERNAL_OPERATIONAL_REFERENCE: "EXTERNAL_OPERATIONAL_REFERENCE",
  SIMULATION: "SIMULATION",
};
const SNAPSHOT_LABEL: Record<string, string> = {
  LIVE_VERIFIED: "실시간 API 확인",
  CACHED: "캐시 사용",
  ENCODED_FROM_REPORT: "보고서 원문 수록",
  UNAVAILABLE: "사용 불가",
};

type HomeDoctor = Awaited<ReturnType<typeof fetchHomeDoctor>>;
type Kosis = Awaited<ReturnType<typeof fetchKosis>>;

export default function EvidencePage() {
  const [sources, setSources] = useState<SourceEntry[] | null>(null);
  const [priors, setPriors] = useState<PriorsPayload | null>(null);
  const [kosis, setKosis] = useState<Kosis | null>(null);
  const [homeDoctor, setHomeDoctor] = useState<HomeDoctor | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [reloadVersion, setReloadVersion] = useState(0);

  const load = useCallback(() => {
    setError(null);
    setReloadVersion((version) => version + 1);
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([fetchEvidenceSources(), fetchEvidencePriors(), fetchKosis(), fetchHomeDoctor()])
      .then(([sourceBody, priorBody, kosisBody, homeBody]) => {
        if (!active) return;
        setSources(sourceBody.sources);
        setPriors(priorBody);
        setKosis(kosisBody);
        setHomeDoctor(homeBody);
      })
      .catch((reason: unknown) => { if (active) setError(reason); });
    return () => { active = false; };
  }, [reloadVersion]);

  return (
    <main className="page-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">근거·출처</p>
          <h1>어떤 숫자가 실제이고, 무엇이 참고·모의인가</h1>
          <p className="page-lede">각 출처의 실제/참고/모의 구분, 기준일, 공간범위, 갱신주기, 사용목적과 한계를 한 곳에서 확인합니다.</p>
        </div>
      </header>

      {error ? <ApiErrorNotice error={error} onRetry={load} /> : null}
      {!sources && !error ? <p className="loading-line" role="status">근거 목록을 불러오는 중입니다…</p> : null}

      {sources ? (
        <section className="panel" aria-labelledby="source-table-title">
          <h2 id="source-table-title"><Database size={17} aria-hidden="true" /> 출처 목록</h2>
          <div className="table-wrap">
            <table className="data-table">
              <caption className="sr-only">데이터 출처별 구분, 기준일, 범위, 사용목적과 한계</caption>
              <thead>
                <tr><th scope="col">출처</th><th scope="col">구분</th><th scope="col">기준일</th><th scope="col">공간범위</th><th scope="col">갱신주기</th><th scope="col">사용목적</th><th scope="col">한계·금지</th><th scope="col">상태</th></tr>
              </thead>
              <tbody>
                {sources.map((source) => (
                  <tr key={source.source_id}>
                    <th scope="row">
                      <span className="cell-title">{source.name_ko}</span>
                      <span className="cell-sub">{source.publisher}</span>
                    </th>
                    <td>
                      <span className={`reality-tag reality-${source.reality.toLowerCase()}`}>{REALITY_LABEL[source.reality]}</span>{" "}
                      {ROLE_TO_BADGE[source.role] ? <ProvenanceBadge kind={ROLE_TO_BADGE[source.role]} compact /> : null}
                    </td>
                    <td>{source.reference_date}</td>
                    <td>{source.spatial_scope}</td>
                    <td>{source.update_cycle}</td>
                    <td>{source.purpose}</td>
                    <td>
                      <ul className="plain-list">
                        {source.limitations.map((item) => <li key={item}>{item}</li>)}
                        {source.must_not.map((item) => <li key={item} className="must-not">금지: {item}</li>)}
                      </ul>
                    </td>
                    <td>
                      <span className="cell-title">{source.snapshot_status ? SNAPSHOT_LABEL[source.snapshot_status] ?? source.snapshot_status : "-"}</span>
                      {source.cache_note ? <span className="cell-sub">{source.cache_note}</span> : null}
                      <span className={`cell-sub ${source.ingest_status === "INGEST_BLOCKED" ? "text-bad" : ""}`}>
                        {source.ingest_status === "INGEST_BLOCKED" ? "수집 차단 (라이선스 불명확)" : `이용조건 ${source.license_status}`} · 확인 {koreanDate(source.checked_at)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {priors ? (
        <section className="panel" aria-labelledby="prior-title">
          <h2 id="prior-title"><BookOpenText size={17} aria-hidden="true" /> 농촌 외부 조사 기준값 ({priors.source.report_id as string})</h2>
          <p className="muted">{priors.source.source_title as string} · {priors.source.publisher as string} · {priors.source.table_id as string} · 표본 크기: 보고서에 명시되지 않음</p>
          <div className="prior-grid">
            {priors.demo_services.map((prior) => (
              <article className="prior-card" key={prior.service_label} aria-label={`${SERVICE_LABELS_V4[prior.service_type ?? ""] ?? prior.service_label} 외부 조사 기준값`}>
                <header>
                  <h3>{SERVICE_LABELS_V4[prior.service_type ?? ""] ?? prior.service_label}</h3>
                  <ProvenanceBadge kind="EXTERNAL_EMPIRICAL" />
                </header>
                <dl className="metric-list">
                  <div><dt>필요도</dt><dd>{percent(prior.need_rate)}</dd></div>
                  <div><dt>필요자 이용률</dt><dd>{percent(prior.usage_rate)}</dd></div>
                  <div><dt>미충족률</dt><dd>{percent(prior.unmet_rate)}</dd></div>
                </dl>
                <p className="warning-line" role="note"><ShieldAlert size={14} aria-hidden="true" /> {prior.interpretation_warning}</p>
                <details>
                  <summary>정의 보기</summary>
                  <ul className="plain-list">
                    {Object.entries(prior.definitions).map(([key, value]) => <li key={key}><strong>{key}</strong>: {value}</li>)}
                  </ul>
                  <p className="cell-sub">생활돌봄 지원사업 수행지역 미충족 {percent(prior.unmet_rate_program_area)} / 미수행 {percent(prior.unmet_rate_non_program_area)}</p>
                </details>
              </article>
            ))}
          </div>
          <h3 className="subhead">사용하지 않는 용도</h3>
          <ul className="plain-list">{priors.not_intended_uses.map((item) => <li key={item}>{item}</li>)}</ul>

          <h3 className="subhead">세탁 서비스 사례 (사례 참고용 · 기본값 아님)</h3>
          <div className="table-wrap">
            <table className="data-table">
              <caption className="sr-only">KREI 세탁 서비스 사례</caption>
              <thead><tr><th scope="col">사례</th><th scope="col">운영 방식</th><th scope="col">운영 주체</th><th scope="col">대상·요금</th><th scope="col">인력·설비</th><th scope="col">돌봄 연계</th></tr></thead>
              <tbody>
                {priors.laundry_cases.map((item) => (
                  <tr key={item.case_id}>
                    <th scope="row"><span className="cell-title">{item.name}</span><span className="cell-sub">{item.location}</span></th>
                    <td>{item.operation_type}</td>
                    <td>{item.operator}</td>
                    <td>{[item.eligible_population, item.general_fee].filter(Boolean).join(" · ") || "-"}</td>
                    <td>{[item.staffing, item.vehicle_count ? `차량 ${item.vehicle_count}대` : null, item.daily_capacity].filter(Boolean).join(" · ") || "-"}</td>
                    <td>{item.care_linkage ? "있음" : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {kosis ? <KosisSection kosis={kosis} /> : null}

      {homeDoctor ? (
        <section className="panel" aria-labelledby="hd-title">
          <h2 id="hd-title"><Info size={17} aria-hidden="true" /> 관리홈닥터 월별지원현황 <ProvenanceBadge kind="EXTERNAL_OPERATIONAL_REFERENCE" /></h2>
          <p className="warning-line" role="note"><ShieldAlert size={14} aria-hidden="true" /> 임대주택 취약계층 운영자료입니다. 농촌 마을 수요 기준값으로 쓰지 않고, 예측 방법 검증에만 사용합니다.</p>
          <p className="muted">
            {homeDoctor.live_verified ? "실시간 API 확인" : homeDoctor.cache_note ?? "캐시 사용"} · 수집 {koreanDate(homeDoctor.retrieved_at)} · 제공기관 안내: {String(homeDoctor.summary.official_limitation ?? "-")}
          </p>
          <div className="table-wrap">
            <table className="data-table compact">
              <caption>최근 12개월 전국 합계 (지원내용 총건수)</caption>
              <thead><tr><th scope="col">월</th><th scope="col">단지 수</th><th scope="col">총건수</th></tr></thead>
              <tbody>
                {(homeDoctor.summary.national_monthly ?? []).slice(-12).map((row) => (
                  <tr key={row.period}><th scope="row">{row.period}</th><td>{count(row.complex_count)}</td><td>{count(row.total)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </main>
  );
}

function KosisSection({ kosis }: { kosis: Kosis }) {
  const tables = kosis.tables.filter((table): table is KosisTable & { data: NonNullable<KosisTable["data"]> } => Boolean(table.data));
  return (
    <section className="panel" aria-labelledby="kosis-title">
      <h2 id="kosis-title"><Database size={17} aria-hidden="true" /> KOSIS 사회서비스수요·공급실태조사 <ProvenanceBadge kind="EXTERNAL_EMPIRICAL" /></h2>
      <p className="warning-line" role="note"><ShieldAlert size={14} aria-hidden="true" /> {kosis.scope_rule}</p>
      <div className="table-wrap">
        <table className="data-table">
          <caption className="sr-only">확인된 KOSIS 통계표</caption>
          <thead><tr><th scope="col">통계표</th><th scope="col">기간</th><th scope="col">차원</th><th scope="col">최종 갱신</th><th scope="col">상태</th></tr></thead>
          <tbody>
            {tables.map((table) => (
              <tr key={table.table_id}>
                <th scope="row"><span className="cell-title">{table.data.table_name}</span><span className="cell-sub">117 · {table.table_id}{table.data.definition ? ` · ${table.data.definition}` : ""}</span></th>
                <td>{table.data.period}</td>
                <td>{table.data.dimensions.join(", ")}</td>
                <td>{koreanDate(table.data.last_updated)}</td>
                <td>{table.status === "LIVE" ? "실시간 API 확인" : table.cache_note ?? table.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">카탈로그에서 찾지 못한 항목: {kosis.topics_not_found.map((item) => item.topic).join(", ")} (추정하지 않음)</p>
    </section>
  );
}
