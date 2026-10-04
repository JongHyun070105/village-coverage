"use client";

import { useState } from "react";
import { ApiErrorNotice } from "@/components/api-error";
import { fetchFallbackCandidates, fetchReserveComparison, type FallbackCandidateResult, type ReserveComparison } from "@/lib/provider-resilience";
import { won } from "@/lib/format";
import type { ScenarioKey } from "@/lib/types";

const RESERVE_LABEL: Record<ReserveComparison["options"][number]["option"], string> = {
  NO_RESERVE: "예비 없음",
  BUDGET_RESERVE: "예산 예비",
  PROVIDER_FALLBACK: "대체 공급자",
  BOTH: "예산 + 대체 공급자",
};

export default function ProviderResiliencePanel({
  regionId,
  budgetWon,
  scenario = "balanced",
}: {
  regionId: string;
  budgetWon: number;
  scenario?: ScenarioKey;
}) {
  const [reservePct, setReservePct] = useState(10);
  const [fallbacks, setFallbacks] = useState<FallbackCandidateResult | null>(null);
  const [comparison, setComparison] = useState<ReserveComparison | null>(null);
  const [loading, setLoading] = useState<"fallback" | "reserve" | "">("");
  const [error, setError] = useState<unknown>(null);

  async function loadFallbacks() {
    setLoading("fallback");
    setError(null);
    try {
      setFallbacks(await fetchFallbackCandidates(regionId, budgetWon, scenario));
    } catch (reason) {
      setError(reason);
    } finally {
      setLoading("");
    }
  }

  async function loadReserveComparison() {
    setLoading("reserve");
    setError(null);
    try {
      setComparison(await fetchReserveComparison(regionId, budgetWon, reservePct, scenario));
    } catch (reason) {
      setError(reason);
    } finally {
      setLoading("");
    }
  }

  return (
    <section className="panel provider-resilience-panel" aria-labelledby="provider-resilience-title">
      <h2 id="provider-resilience-title">공급자 불참 대비</h2>
      <p className="feedback-note">후보와 예산 비율은 담당자가 검토할 모의 비교입니다. 실제 참여 확인·계약·가격으로 간주하지 않습니다.</p>
      <div className="provider-resilience-controls">
        <button type="button" className="ghost-button" onClick={() => void loadFallbacks()} disabled={loading !== ""}>
          {loading === "fallback" ? "후보 계산 중" : "2순위·3순위 후보 계산"}
        </button>
        <label>예비 비율
          <select value={reservePct} onChange={(event) => setReservePct(Number(event.target.value))}>
            {[0, 5, 10, 15].map((value) => <option key={value} value={value}>{value}%</option>)}
          </select>
        </label>
        <button type="button" className="ghost-button" onClick={() => void loadReserveComparison()} disabled={loading !== ""}>
          {loading === "reserve" ? "불참 상황 비교 중" : "예비 정책 비교"}
        </button>
      </div>
      {error ? <ApiErrorNotice error={error} /> : null}
      {fallbacks && <div className="provider-resilience-results" aria-live="polite">
        <p>대체 후보 {fallbacks.round_count - fallbacks.rounds_without_fallback}/{fallbacks.round_count}회차 · 수동 확인 필요</p>
        <div className="table-wrap"><table className="data-table">
          <caption className="sr-only">회차별 공급자 대체 후보</caption>
          <thead><tr><th scope="col">마을</th><th scope="col">서비스일</th><th scope="col">기본 제공자</th><th scope="col">대체 후보</th><th scope="col">추가 모의비용</th></tr></thead>
          <tbody>{fallbacks.rounds.map((row, index) => <tr key={`${row.area_id}-${row.scheduled_date}-${index}`}>
            <th scope="row">{row.area_id}</th><td>{row.scheduled_date}</td><td>{row.primary_provider_id}</td>
            <td>{row.fallbacks.length ? row.fallbacks.map((item) => `${item.tier === "SECONDARY" ? "2순위" : "3순위"} ${item.provider_name}`).join(" · ") : "후보 없음"}</td>
            <td>{row.fallbacks.length ? won(Math.max(...row.fallbacks.map((item) => item.extra_cost_vs_primary_won))) : "-"}</td>
          </tr>)}</tbody>
        </table></div>
        <p className="feedback-note">{fallbacks.notice}</p>
      </div>}
      {comparison && <div className="provider-resilience-results" aria-live="polite">
        <p>담당자 선택 예비 {comparison.reserve_pct}% · {comparison.label}</p>
        <div className="table-wrap"><table className="data-table">
          <caption className="sr-only">공급자 불참 시 예비 정책 비교</caption>
          <thead><tr><th scope="col">비교 방식</th><th scope="col">불참 전 배정 권역</th><th scope="col">불참 후 서비스 미배정 권역</th><th scope="col">회복 사례</th><th scope="col">추가 모의비용</th><th scope="col">최악 상황 잔여예산</th></tr></thead>
          <tbody>{comparison.options.map((option) => <tr key={option.option}>
            <th scope="row">{RESERVE_LABEL[option.option]}</th>
            <td>{option.no_decline.covered_areas}곳 · {option.no_decline.served_units}회</td>
            <td>{option.worst_zero_service_after_decline ?? "계산 불가"}곳</td>
            <td>{option.replan_success_rate === null ? "불참 대상 없음" : `${option.decline_cases_with_recovery}/${option.decline_case_count} (${Math.round(option.replan_success_rate * 100)}%)`}</td>
            <td>{won(option.worst_extra_cost_vs_no_decline_won)}</td>
            <td>{won(option.unused_budget_at_worst_case_won)}</td>
          </tr>)}</tbody>
        </table></div>
        <p className="feedback-note">회복 사례는 불참이 없을 때보다 서비스 회차가 한 건 이상 늘어난 모의 불참 사례입니다. 예산은 모든 불참 사례에서 한도를 지켜야 통과합니다.</p>
        <p className="feedback-note">{comparison.notice}</p>
      </div>}
    </section>
  );
}
