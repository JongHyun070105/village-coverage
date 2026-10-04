import { CircleCheck, CircleDashed, CircleX, Clock } from "lucide-react";

const STATUS: Record<string, { feasible: string; optimal: string; tone: string; Icon: typeof CircleCheck }> = {
  OPTIMAL: { feasible: "실행 가능한 계획", optimal: "최적성 확인 완료", tone: "ok", Icon: CircleCheck },
  FEASIBLE: { feasible: "실행 가능한 계획", optimal: "최적성 미확인", tone: "warn", Icon: CircleDashed },
  TIME_LIMIT: { feasible: "실행 가능한 계획", optimal: "제한시간 도달 · 최적성 미확인", tone: "warn", Icon: Clock },
  INFEASIBLE: { feasible: "실행 가능한 계획 없음", optimal: "-", tone: "bad", Icon: CircleX },
  UNKNOWN: { feasible: "계획 상태 확인 불가", optimal: "-", tone: "bad", Icon: CircleX },
};

const STRATEGY_LABEL: Record<string, string> = {
  BASELINE_MONOLITHIC: "기본 통합 계산",
  BASELINE_DECOMPOSED: "기본 단계별 계산",
  GEOGRAPHIC_CLUSTER: "지역별 계산 후 전체 조정",
  ROLLING_HORIZON: "기간별 재계산",
  GEOGRAPHIC_ROLLING: "지역·기간별 계산 후 전체 조정",
  BASELINE_FALLBACK: "기본 방식으로 다시 계산",
};

const FALLBACK_REASON_LABEL: Record<string, string> = {
  GEOGRAPHIC_RECONCILIATION_FAILED: "지역별 결과를 전체 자원 기준으로 조정하지 못했습니다",
  GEOGRAPHIC_SCHEDULE_VALIDATION_FAILED: "전체 일정 검증을 통과하지 못했습니다",
  GEOGRAPHIC_GLOBAL_VALIDATION_FAILED: "전체 운영 조건을 통과하지 못했습니다",
  ROLLING_HORIZON_WINDOW_VALIDATION_FAILED: "기간별 일정 검증을 통과하지 못했습니다",
  ROLLING_HORIZON_WINDOW_SOLVE_FAILED: "기간별 계획 계산을 완료하지 못했습니다",
  ROLLING_HORIZON_COMMITTED_NO_ROUNDS: "기간별 계산에서 서비스 일정을 만들지 못했습니다",
  ROLLING_MINIMUM_OBLIGATION_NOT_MET: "필수 최소 서비스 기준을 충족하지 못했습니다",
  ROLLING_QUALITY_BELOW_FULL_LOOKAHEAD: "전체 기간 계산보다 품질이 낮아졌습니다",
};

/** Two separate facts: is there an executable plan, and was optimality proven? */
export function SolverStatus({
  status,
  hasPlan = true,
  scope,
  strategyUsed,
  fallbackUsed = false,
  fallbackReason,
  solveTimeMs,
}: {
  status: string;
  hasPlan?: boolean;
  scope?: string | null;
  strategyUsed?: string | null;
  fallbackUsed?: boolean;
  fallbackReason?: string | null;
  solveTimeMs?: number | null;
}) {
  const meta = STATUS[status] ?? STATUS.UNKNOWN;
  const feasibleText = hasPlan ? meta.feasible : "실행 가능한 계획 없음";
  return (
    <div className="solver-status-details">
      <span className={`solver-status tone-${hasPlan ? meta.tone : "bad"}`}>
        <meta.Icon size={14} aria-hidden="true" />
        <span>{feasibleText}</span>
        <span className="solver-status-sep" aria-hidden="true">·</span>
        <span>{meta.optimal}{scope === "ALLOCATION_MODEL_WITH_ROUND_TRIP_COSTS" && status === "OPTIMAL" ? " (왕복 비용 모델 기준)" : ""}</span>
      </span>
      {strategyUsed || solveTimeMs != null ? (
        <small className="solver-status-method">
          {strategyUsed ? STRATEGY_LABEL[strategyUsed] ?? strategyUsed : null}
          {strategyUsed && solveTimeMs != null ? " · " : null}
          {solveTimeMs != null ? `계산 ${Math.round(solveTimeMs).toLocaleString("ko-KR")}ms` : null}
        </small>
      ) : null}
      {fallbackUsed ? (
        <p className="solver-status-fallback" role="status">
          {fallbackReason && FALLBACK_REASON_LABEL[fallbackReason]
            ? `${FALLBACK_REASON_LABEL[fallbackReason]}. 기본 계산 방식으로 다시 계산했습니다.`
            : "대체 계산 경로를 사용했습니다."}
        </p>
      ) : null}
    </div>
  );
}
