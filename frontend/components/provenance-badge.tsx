import { Building2, Calculator, ClipboardList, FlaskConical, Library, Route, Telescope } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type ProvenanceKind =
  | "PUBLIC_DATA"
  | "EXTERNAL_EMPIRICAL"
  | "EXTERNAL_OPERATIONAL_REFERENCE"
  | "LOCAL_OBSERVATION"
  | "MODEL_ESTIMATE"
  | "SIMULATION"
  | "OPTIMIZATION_RESULT";

const PROVENANCE: Record<ProvenanceKind, { label: string; icon: LucideIcon; help: string }> = {
  PUBLIC_DATA: { label: "공공데이터", icon: Building2, help: "행정안전부·공공데이터포털 등 실제 공개 통계입니다." },
  EXTERNAL_EMPIRICAL: { label: "외부 조사 기준값", icon: Library, help: "농촌 외부 조사(KREI) 값입니다. 이 마을의 실제 수요가 아닙니다." },
  EXTERNAL_OPERATIONAL_REFERENCE: { label: "외부 운영자료 참고", icon: Telescope, help: "임대주택 관리홈닥터 운영자료입니다. 농촌 수요로 쓰지 않습니다." },
  LOCAL_OBSERVATION: { label: "지역 조사", icon: ClipboardList, help: "이 지역에서 직접 받은 조사·기록입니다." },
  MODEL_ESTIMATE: { label: "모델 추정", icon: Calculator, help: "근거를 결합해 계산한 범위 추정치입니다." },
  SIMULATION: { label: "모의 데이터", icon: FlaskConical, help: "알고리즘 검증용 시뮬레이션 값입니다. 실제 자료가 아닙니다." },
  OPTIMIZATION_RESULT: { label: "최적화 결과", icon: Route, help: "입력 조건에서 계산한 계획 결과입니다." },
};

export function ProvenanceBadge({ kind, compact = false }: { kind: ProvenanceKind; compact?: boolean }) {
  const meta = PROVENANCE[kind];
  const Icon = meta.icon;
  const className = kind === "SIMULATION" ? "provenance-badge simulated" : "provenance-badge";
  return (
    <span className={className} title={meta.help} aria-label={`${meta.label}: ${meta.help}`}>
      <Icon size={12} aria-hidden="true" />
      {compact ? null : <span>{meta.label}</span>}
    </span>
  );
}

export function provenanceHelp(kind: ProvenanceKind) {
  return PROVENANCE[kind].help;
}
