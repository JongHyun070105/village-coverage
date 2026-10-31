"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { getApiReadiness, subscribeApiReadiness } from "@/lib/api";

export function ApiReadinessNotice({ onRetry }: { onRetry: () => void }) {
  const state = useSyncExternalStore(subscribeApiReadiness, getApiReadiness, () => "INITIAL_LOADING");
  const [manualRetry, setManualRetry] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setManualRetry(true), 15_000);
    return () => clearTimeout(timer);
  }, []);
  const publicDemo = process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true";
  const preparing = publicDemo && ["INITIAL_LOADING", "SERVER_WAKING", "RETRY_AVAILABLE"].includes(state);
  return (
    <section className="loading-card api-readiness" role="status" aria-live="polite" aria-atomic="true"
      data-state={manualRetry && preparing ? "RETRY_AVAILABLE" : state === "SERVER_READY" ? "DATA_LOADING" : state}>
      <span className="spinner" aria-hidden="true" />
      <div>
        <h2>{preparing ? "데모 서버 연결을 준비하고 있습니다" : "계획 데이터를 불러오고 있습니다"}</h2>
        {preparing ? <>
          <p>무료 시연 서버가 시작 중이거나 현재 요청이 일시적으로 집중되어 있습니다. 연결이 가능해지면 데이터를 자동으로 불러옵니다.</p>
          <p>연결 상태를 확인하는 중입니다.</p>
        </> : <p>연결이 확인되었습니다. 선택한 지역의 데이터를 불러오고 있습니다.</p>}
        {manualRetry ? <button type="button" className="button button-dark" onClick={onRetry}>다시 불러오기</button> : null}
      </div>
    </section>
  );
}
