import { CircleCheck, CircleDashed, CircleX, Clock } from "lucide-react";

const STATUS: Record<string, { feasible: string; optimal: string; tone: string; Icon: typeof CircleCheck }> = {
  OPTIMAL: { feasible: "실행 가능한 계획", optimal: "최적성 확인 완료", tone: "ok", Icon: CircleCheck },
  FEASIBLE: { feasible: "실행 가능한 계획", optimal: "최적성 미확인", tone: "warn", Icon: CircleDashed },
  TIME_LIMIT: { feasible: "실행 가능한 계획", optimal: "제한시간 도달 · 최적성 미확인", tone: "warn", Icon: Clock },
  INFEASIBLE: { feasible: "실행 가능한 계획 없음", optimal: "-", tone: "bad", Icon: CircleX },
  UNKNOWN: { feasible: "계획 상태 확인 불가", optimal: "-", tone: "bad", Icon: CircleX },
};

/** Two separate facts: is there an executable plan, and was optimality proven? */
export function SolverStatus({ status, hasPlan = true, scope }: { status: string; hasPlan?: boolean; scope?: string | null }) {
  const meta = STATUS[status] ?? STATUS.UNKNOWN;
  const feasibleText = hasPlan ? meta.feasible : "실행 가능한 계획 없음";
  return (
    <span className={`solver-status tone-${hasPlan ? meta.tone : "bad"}`}>
      <meta.Icon size={14} aria-hidden="true" />
      <span>{feasibleText}</span>
      <span className="solver-status-sep" aria-hidden="true">·</span>
      <span>{meta.optimal}{scope === "ALLOCATION_MODEL_WITH_ROUND_TRIP_COSTS" && status === "OPTIMAL" ? " (왕복 비용 모델 기준)" : ""}</span>
    </span>
  );
}
