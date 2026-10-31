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
        <h2>{preparing ? "데모 서버를 준비하고 있습니다" : "계획 데이터를 불러오고 있습니다"}</h2>
        {preparing ? <>
          <p>현재 무료 공개 데모 환경을 사용하고 있어, 일정 시간 접속이 없으면 서버가 절전 상태로 전환됩니다. 처음 접속할 때는 서버를 다시 시작하는 데 시간이 걸릴 수 있습니다.</p>
          <p>연결이 준비되면 데이터를 자동으로 불러옵니다.</p>
        </> : <p>연결이 확인되었습니다. 선택한 지역의 데이터를 불러오고 있습니다.</p>}
        {manualRetry ? <button type="button" className="button button-dark" onClick={onRetry}>다시 불러오기</button> : null}
      </div>
    </section>
  );
}
