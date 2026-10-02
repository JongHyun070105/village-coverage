"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, ChartNoAxesCombined } from "lucide-react";
import { fetchForecastBacktest } from "@/lib/api";
import type { ForecastBacktestResponse } from "@/lib/types";

const percent = (value: number | null) =>
  value === null ? "—" : `${(value * 100).toFixed(0)}%`;
const metric = (value: number | null) =>
  value === null ? "—" : value.toFixed(2);

const serviceLabels: Record<string, string> = {
  laundry: "세탁",
  daily_necessities: "생활용품 지원",
  home_repair: "주거생활 지원",
};

export default function ForecastBacktestPanel() {
  const [report, setReport] = useState<ForecastBacktestResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchForecastBacktest()
      .then(setReport)
      .catch((cause) => setError(cause instanceof Error ? cause.message : "검증 결과를 불러오지 못했습니다."));
  }, []);

  const reports = report?.reports.filter((item) => item.origin_count > 0) ?? [];
  return (
    <section className="content-card backtest-panel">
      <div className="section-heading">
        <div>
          <h2><ChartNoAxesCombined size={16} /> 과거 예측 검증</h2>
          <p>각 cutoff 이전 근거로만 학습하고 다음 세 달을 holdout으로 평가합니다.</p>
        </div>
        {report && <span className={`forecast-status ${report.status === "AVAILABLE" ? "available" : "insufficient"}`}>{report.status === "AVAILABLE" ? "평가 가능" : "자료 부족"}</span>}
      </div>
      {error && <p className="backtest-message" role="alert">{error}</p>}
      {!report && !error && <p className="backtest-message">과거 cutoff와 holdout을 계산하고 있습니다.</p>}
      {report && reports.length === 0 && (
        <p className="backtest-message"><AlertTriangle size={14} /> 아직 연속 월별 관측 이력이 없어 정확도 점수를 만들지 않았습니다. 모의 자료를 관측 사실로 바꾸지 않습니다.</p>
      )}
      {reports.length > 0 && (
        <div className="backtest-table-wrap">
          <table className="backtest-table">
            <thead><tr><th>지역·서비스</th><th>근거 구분</th><th>cutoff</th><th>MAE</th><th>WAPE</th><th>bias</th><th>구간 포함률</th><th>가용률</th><th>미산출</th></tr></thead>
            <tbody>{reports.map((item) => <tr key={`${item.region_id}:${item.service_type}`}>
              <td>{item.region_name} · {serviceLabels[item.service_type] || item.service_type}</td>
              <td><span className={item.backtest_type === "SYNTHETIC BACKTEST" ? "provenance-badge simulated" : "provenance-badge"}>{item.backtest_type}</span></td>
              <td>{item.origin_count}</td>
              <td>{metric(item.metrics.mae)}</td>
              <td>{item.metrics.wape_status === "UNDEFINED_ZERO_ACTUAL_TOTAL" ? "정의 안 됨 (actual 합 0)" : percent(item.metrics.wape)}</td>
              <td>{metric(item.metrics.bias)}</td>
              <td>{percent(item.metrics.interval_coverage)}</td>
              <td>{percent(item.metrics.forecast_availability_rate)}</td>
              <td>{item.metrics.forecast_unavailable_count}/{item.metrics.evaluation_case_count}</td>
            </tr>)}</tbody>
          </table>
        </div>
      )}
      {reports.length > 0 && <p className="backtest-message">{reports[0].metrics.accuracy_scope}</p>}
      <p className="backtest-message">T+1, T+2, T+3별 결과도 함께 저장된 응답에 포함됩니다. 모든 forecast가 생성되지 않은 경우 정확도는 공란이며, 가용률 0%와 미산출 건수를 별도로 표시합니다.</p>
    </section>
  );
}
