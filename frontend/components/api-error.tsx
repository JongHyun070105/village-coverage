import { AlertTriangle, RotateCcw } from "lucide-react";
import { ApiError } from "@/lib/api";

const GUIDANCE: Record<string, { what: string; todo: string }> = {
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

export function ApiErrorNotice({ error, onRetry, id }: { error: unknown; onRetry?: () => void; id?: string }) {
  const code = error instanceof ApiError ? error.code : "NETWORK";
  const message = error instanceof Error ? error.message : "알 수 없는 오류";
  const guide = GUIDANCE[code] ?? { what: message, todo: "백엔드 서버 연결(포트 8000)을 확인하고 다시 시도하세요." };
  return (
    <div className="api-error" role="alert" id={id}>
      <AlertTriangle size={18} aria-hidden="true" />
      <div>
        <strong>{guide.what}</strong>
        <p>{message !== guide.what ? message : null}</p>
        <p className="api-error-todo">할 일: {guide.todo}</p>
        <small>오류 코드 {code}</small>
      </div>
      {onRetry ? <button type="button" className="ghost-button" onClick={onRetry}><RotateCcw size={14} aria-hidden="true" /> 다시 시도</button> : null}
    </div>
  );
}
