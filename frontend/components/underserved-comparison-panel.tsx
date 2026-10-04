"use client";

import { useCallback, useState } from "react";
import { Scale } from "lucide-react";
import { ApiErrorNotice } from "@/components/api-error";
import {
  UNDERSERVED_STATUS_LABEL,
  fetchUnderservedComparison,
  seedUnderservedDemo,
  type UnderservedComparison,
  type UnderservedStatus,
} from "@/lib/underserved";

export default function UnderservedComparisonPanel({ regionId, budgetWon }: { regionId: string; budgetWon: number }) {
  const [comparison, setComparison] = useState<UnderservedComparison | null>(null);
  const [seedNotice, setSeedNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (seed: boolean) => {
    setLoading(true);
    setError(null);
    try {
      if (seed) setSeedNotice((await seedUnderservedDemo(regionId)).notice);
      setComparison(await fetchUnderservedComparison(regionId, budgetWon));
    } catch (reason) {
      setError(reason);
    } finally {
      setLoading(false);
    }
  }, [regionId, budgetWon]);

  return (
    <section className="panel underserved-panel" aria-labelledby="underserved-title">
      <h2 id="underserved-title"><Scale size={17} aria-hidden="true" /> 소외 최소화 비교 <span className="provenance-badge simulated">SIMULATION</span></h2>
      <p className="feedback-note">서비스 공백 이력(월별)에 따라 네 정책과 요청 건수 기준선을 비교합니다. 시뮬레이션이며 실제 수혜 인원이나 감소율을 뜻하지 않습니다.</p>
      <div className="button-row">
        <button type="button" className="ghost-button" onClick={() => void load(false)} disabled={loading}>{loading ? "계산 중" : "비교 계산"}</button>
        <button type="button" className="ghost-button" onClick={() => void load(true)} disabled={loading}>가상 이력 넣고 계산 (데모)</button>
      </div>
      {seedNotice ? <p className="feedback-note" role="status">{seedNotice}</p> : null}
      {error ? <ApiErrorNotice error={error} /> : null}
      {comparison ? (
        <>
          <p className="feedback-signal" role="status">
            {(Object.keys(comparison.status_counts) as UnderservedStatus[]).map((key) => `${UNDERSERVED_STATUS_LABEL[key]} ${comparison.status_counts[key]}`).join(" · ")}
          </p>
          <div className="table-wrap">
            <table className="data-table">
              <caption className="sr-only">정책별 소외 최소화 시뮬레이션 비교</caption>
              <thead>
                <tr>
                  <th scope="col">정책</th>
                  <th scope="col">제공 회차</th>
                  <th scope="col">현재 계획에서 서비스 미배정 권역</th>
                  <th scope="col">장기·만성 권역 신규 배정</th>
                  <th scope="col">공백 가점 반영</th>
                </tr>
              </thead>
              <tbody>
                {comparison.rows.map((row) => (
                  <tr key={row.policy}>
                    <th scope="row">{row.label_ko}</th>
                    <td>{row.served_units ?? "-"}</td>
                    <td>{row.ZERO_SERVICE_AREA_COUNT}곳</td>
                    <td>{row.REDUCED_EXCLUSION_COUNT}곳</td>
                    <td>{row.underserved_points_covered} / {row.underserved_points_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="plain-list">
            {Object.entries(comparison.kpi_definitions).map(([key, text]) => <li key={key}><b>{key}</b>: {text}</li>)}
          </ul>
          <p className="feedback-note">{comparison.notice}</p>
        </>
      ) : null}
    </section>
  );
}
