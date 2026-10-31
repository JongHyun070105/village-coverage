import { AlertTriangle, RotateCcw } from "lucide-react";
import { ApiError } from "@/lib/api";

const GUIDANCE: Record<string, { what: string; todo: string }> = {
  DEMO_MODE_RESTRICTED: { what: "이 공개 데모에서는 사용할 수 없는 요청입니다.", todo: "공개 데모에서 제공하는 화면과 기능을 이용하세요." },
  DEMO_RATE_LIMITED: { what: "잠시 요청이 많습니다.", todo: "잠깐 기다린 뒤 다시 시도해 주세요." },
  DEMO_SESSION_RATE_LIMITED: { what: "새 공개 데모 세션을 잠시 만들 수 없습니다.", todo: "잠깐 기다린 뒤 다시 접속해 주세요." },
  DEMO_SESSION_EXPIRED: { what: "이 브라우저 세션이 만료되었습니다.", todo: "공개 데모를 새로고침해 새 세션으로 시작하세요." },
  DEMO_SESSION_CAPACITY: { what: "공개 데모가 현재 사용할 수 있는 세션 수에 도달했습니다.", todo: "잠시 기다린 뒤 다시 시도해 주세요." },
  DEMO_SESSION_UNAVAILABLE: { what: "공개 데모 세션을 확인할 수 없습니다.", todo: "잠시 기다린 뒤 새로고침해 주세요." },
  DEMO_SESSION_PLAN_LIMIT: { what: "이 브라우저 세션에서 만들 수 있는 계획 수에 도달했습니다.", todo: "잠시 기다린 뒤 다시 시도해 주세요." },
  DEMO_STORAGE_CAPACITY: { what: "공개 데모 저장 공간이 현재 가득 찼습니다.", todo: "잠시 뒤 다시 시도해 주세요." },
  DEMO_SOLVER_CAPACITY: { what: "계획 계산 요청이 많습니다.", todo: "잠시 기다린 뒤 다시 시도해 주세요." },
  SERVER_WAKE_TIMEOUT: { what: "데모 서버 연결 준비 시간이 초과되었습니다.", todo: "잠시 후 다시 불러오기를 눌러 주세요." },
  TEMPORARY_UPSTREAM_FAILURE: { what: "데모 서버가 일시적으로 응답하지 않습니다.", todo: "잠시 기다린 뒤 최신 데이터를 다시 불러와 주세요." },
  REQUEST_TIMEOUT: { what: "데모 서버 응답 시간이 초과되었습니다.", todo: "잠시 기다린 뒤 최신 데이터를 다시 불러와 주세요." },
  API_CONTRACT_ERROR: { what: "데모 서버가 예상한 형식의 응답을 보내지 않았습니다.", todo: "잠시 뒤 다시 시도해 주세요." },
  VALIDATION_ERROR: { what: "입력값이 허용 범위를 벗어났습니다.", todo: "표시된 항목을 확인해 다시 입력하세요." },
  DATA_INSUFFICIENT: { what: "판단에 필요한 조사·기록이 부족합니다.", todo: "수요·조사 화면에서 조사계획을 만들고 기록을 추가하세요." },
  EVIDENCE_CONFLICT: { what: "같은 마을의 조사 결과가 서로 다릅니다.", todo: "마을 상세의 근거 검토에서 충돌을 해결하세요." },
  ROUTE_UNAVAILABLE: { what: "도로 경로 자료가 없는 구간이 있습니다.", todo: "경로 캐시를 갱신하거나 해당 권역을 제외해 다시 계산하세요." },
  PLAN_INFEASIBLE: { what: "현재 조건으로 실행 가능한 계획이 없습니다.", todo: "공급자 참여·예산·시간대를 조정하세요." },
  BUDGET_INSUFFICIENT: { what: "예산이 최소 조건보다 적습니다.", todo: "최소보장 분석에서 필요한 예산을 확인하세요." },
  PROVIDER_CAPACITY_EXCEEDED: { what: "공급자 용량을 초과했습니다.", todo: "공급자를 추가하거나 회차를 조정하세요." },
  PROVIDER_UNAVAILABLE: { what: "참여 가능한 공급자가 없습니다.", todo: "공급자 화면에서 참여 상태를 확인하세요." },
  VERSION_CONFLICT: { what: "다른 작업으로 상태가 바뀌었습니다.", todo: "화면을 새로고침한 뒤 다시 시도하세요." },
  IDEMPOTENCY_CONFLICT: { what: "같은 요청이 이미 처리되었습니다.", todo: "결과 목록을 확인하세요." },
};

const PUBLIC_STATUS_GUIDANCE: Record<number, { what: string; todo: string }> = {
  403: { what: "이 요청을 처리할 권한이 없습니다.", todo: "공개 데모에서 제공하는 화면을 이용하세요." },
  404: { what: "요청한 자료를 찾을 수 없습니다.", todo: "목록을 새로고침한 뒤 다시 선택하세요." },
  410: { what: "이 브라우저 세션이 만료되었습니다.", todo: "공개 데모를 새로고침해 새 세션으로 시작하세요." },
  409: { what: "다른 요청으로 상태가 바뀌었습니다.", todo: "화면을 새로고침한 뒤 최신 상태를 확인하세요." },
  422: { what: "입력값을 처리할 수 없습니다.", todo: "입력한 지역과 예산을 확인한 뒤 다시 시도하세요." },
  429: { what: "잠시 요청이 많습니다.", todo: "잠깐 기다린 뒤 다시 시도해 주세요." },
  500: { what: "서버에서 요청을 처리하지 못했습니다.", todo: "잠시 기다린 뒤 다시 시도해 주세요." },
  502: { what: "데모 서버가 일시적으로 응답하지 않습니다.", todo: "잠시 뒤 최신 데이터를 다시 불러와 주세요." },
  503: { what: "데모 서버를 일시적으로 사용할 수 없습니다.", todo: "잠시 기다린 뒤 다시 시도해 주세요." },
  504: { what: "데모 서버 응답 시간이 초과되었습니다.", todo: "잠시 기다린 뒤 최신 데이터를 다시 불러와 주세요." },
  520: { what: "데모 서버 연결 중 응답이 끊겼습니다.", todo: "계획이 이미 생성됐을 수 있습니다. 같은 요청을 다시 실행하기 전에 계획 목록에서 저장 여부를 확인하세요." },
};

const PUBLIC_NETWORK_GUIDANCE = {
  what: "데모 서버에 연결할 수 없습니다.",
  todo: "잠시 기다린 뒤 다시 시도해 주세요.",
};

const WRITE_SAFETY_TODOS = {
  "ambiguous-write": "계획 목록에서 저장 여부를 확인하세요. 확인 전에는 같은 요청을 다시 실행하지 마세요.",
  "plans-created": "계획은 생성됐지만 후속 분석이 끝나지 않았습니다. 결과 카드와 계획 목록을 확인하세요. 비교 실행을 반복하면 계획이 추가 생성됩니다.",
} as const;
const EXPLANATION_GUIDANCE = {
  what: "계획은 생성됐지만 권역별 설명을 불러오지 못했습니다.",
  todo: "계획의 회차와 비용은 아래 카드에서 확인할 수 있습니다.",
};

export function ApiErrorNotice({ error, onRetry, retryLabel = "다시 시도", id, retrySafety }: {
  error: unknown;
  onRetry?: () => void;
  retryLabel?: string;
  id?: string;
  retrySafety?: keyof typeof WRITE_SAFETY_TODOS | "explanation-unavailable";
}) {
  const code = error instanceof ApiError ? error.code : "NETWORK";
  const message = error instanceof Error ? error.message : "알 수 없는 오류";
  const publicDemo = process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true";
  const guide = retrySafety === "explanation-unavailable"
    ? EXPLANATION_GUIDANCE
    : GUIDANCE[code]
    ?? (publicDemo && error instanceof ApiError ? PUBLIC_STATUS_GUIDANCE[error.status] : undefined)
    ?? (publicDemo && !(error instanceof ApiError) ? PUBLIC_NETWORK_GUIDANCE : undefined)
    ?? { what: message, todo: "백엔드 서버 연결(포트 8000)을 확인하고 다시 시도하세요." };
  const todo = retrySafety && retrySafety !== "explanation-unavailable"
    ? WRITE_SAFETY_TODOS[retrySafety]
    : guide.todo;
  const retryAfter = error instanceof ApiError && error.status === 429
    ? error.retryAfterSeconds
    : undefined;
  const hidePublicServerDetail = publicDemo
    && error instanceof ApiError
    && (error.status === 429 || error.status >= 500);
  const safeMessage = message === code
    || (publicDemo && code === "NETWORK")
    || hidePublicServerDetail
    ? ""
    : message;
  const retryIsAmbiguous = error instanceof ApiError && error.status === 520;
  return (
    <div className="api-error" role="alert" id={id}>
      <AlertTriangle size={18} aria-hidden="true" />
      <div>
        <strong>{guide.what}</strong>
        {safeMessage !== guide.what && safeMessage ? <p>{safeMessage}</p> : null}
        <p className="api-error-todo">할 일: {retryAfter && !retrySafety ? `약 ${retryAfter}초 기다린 뒤 다시 시도해 주세요.` : todo}</p>
        <small>오류 코드 {code}</small>
      </div>
      {onRetry && !retryIsAmbiguous && !retrySafety ? <button type="button" className="ghost-button" onClick={onRetry}><RotateCcw size={14} aria-hidden="true" /> {retryLabel}</button> : null}
    </div>
  );
}
