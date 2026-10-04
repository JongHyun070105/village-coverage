"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { MessageSquareText } from "lucide-react";
import { ApiErrorNotice } from "@/components/api-error";
import {
  FEEDBACK_STATUS_LABEL,
  FEEDBACK_TYPE_LABEL,
  FRESHNESS_LABEL,
  fetchAreaFeedback,
  type AreaFeedbackSummary,
} from "@/lib/feedback";
import { koreanDate } from "@/lib/format";

export default function RecentFeedbackPanel({ areaId }: { areaId: string }) {
  const [summary, setSummary] = useState<AreaFeedbackSummary | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let active = true;
    fetchAreaFeedback(areaId)
      .then((body) => { if (active) { setSummary(body); setError(null); } })
      .catch((reason: unknown) => { if (active) setError(reason); });
    return () => { active = false; };
  }, [areaId]);

  return (
    <section className="content-card recent-feedback-panel" aria-labelledby="recent-feedback-heading">
      <div className="survey-title-row">
        <h2 id="recent-feedback-heading"><MessageSquareText size={16} aria-hidden="true" /> 최근 주민 의견</h2>
        <span className="provenance-badge simulated">LOCAL OBSERVATION · 검증 전 주장</span>
      </div>
      {error ? <ApiErrorNotice error={error} /> : null}
      {summary ? (
        <>
          <p className="feedback-note">{summary.note} 의견은 수요·예측·계획을 자동으로 바꾸지 않습니다.</p>
          <p className="feedback-signal" role="status">
            접수 {summary.total}건 · 검토 대기 {summary.signal.pending_feedback_count}건 · 열린 충돌 {summary.signal.open_conflict_count}건
            {summary.signal.needs_survey ? " · 조사로 확인 필요" : ""}
          </p>
          {summary.recent.length === 0 ? <p className="survey-empty">접수된 주민 의견이 없습니다.</p> : (
            <ul className="feedback-recent-list">
              {summary.recent.map((item) => (
                <li key={item.feedback_id}>
                  <strong>{FEEDBACK_TYPE_LABEL[item.feedback_type]}</strong>
                  <span>{FEEDBACK_STATUS_LABEL[item.status]} · {koreanDate(item.submitted_at)} · {FRESHNESS_LABEL[item.freshness]}</span>
                  <p>{item.description}</p>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : error ? null : <p className="loading-line" role="status">불러오는 중입니다…</p>}
      <Link href={`/feedback?area_id=${encodeURIComponent(areaId)}`} className="text-link">주민 의견·정정 화면에서 검토</Link>
    </section>
  );
}
