# Submission evidence index

이 문서는 제출자료를 만들 때 바로 선택할 수 있는 evidence 경로와 허용되는 문장을 정리합니다. 최종 보고서나 발표자료는 아닙니다. artifacts의 생성일·기준 SHA·provenance를 함께 보존하고, 오래된 acceptance 파일을 최신 수치로 덮어쓰지 않습니다.

## Evidence inventory

| 주제 | 주요 evidence | 상태와 사용 한계 |
|---|---|---|
| Original proposal requirements | `docs/PROPOSAL_REQUIREMENTS_TRACEABILITY.md`, `artifacts/proposal_acceptance_rc1.json` | 원 제안 R1–R13 acceptance 범위. acceptance pass는 simulated prototype 기능 수용이지 field effectiveness가 아님. |
| R1–R13 acceptance | `artifacts/proposal_acceptance_rc1.json` | 현재 RC source SHA로 새로 실행한 결과. 각 요구 ID와 mapped tests를 함께 제시. |
| Demand evidence | `artifacts/demand_model_benchmark.json`, `artifacts/forecast_backtest.json`, `docs/MODEL_CARD_DEMAND.md` | 통제 합성 truth, 외부 운영자료, local series 결과를 분리. local predictive validation은 없음. |
| Public source ingestion | `artifacts/public_schema_manifest.json`, `artifacts/data_quality_report.json`, `artifacts/provider_source_audit.json`, `artifacts/provider_ingestion_summary.json`, `data/provider_snapshots/` | 공개 catalog/source/date/license를 함께 말함. 자활기업·마을기업만 snapshot ingest; social enterprise 미수집; cooperative blocked. 마을기업 catalog와 원본 row count 차이는 공개. |
| Forecast validation | `artifacts/forecast_backtest.json` | synthetic, Home Doctor, local observations를 풀링하지 않음. local series가 없으므로 실제 농촌 예측 정확도 주장은 불가. |
| Optimizer benchmark | `artifacts/v5_2_solver_smoke_rc1.json`, `artifacts/v5_2_readiness_v52_current_20261006.json`, `docs/OPTIMIZER_CARD.md` | 고정 synthetic inputs의 solver/invariant·runtime evidence. `TIME_LIMIT`/`UNKNOWN` 유지; 현장 성능이 아님. |
| Stress tests | `artifacts/stress_v5_1_current_tree.json`, `artifacts/stress_v5_1_current_tree.csv`, `artifacts/v5_2_solver_smoke_rc1.json` | synthetic case matrix에서 invariant 위반 수와 unresolved outcome을 별도 보고. invariant pass는 서비스 coverage pass가 아님. |
| Policy experiment | `artifacts/public_value_experiment.json`, `artifacts/experiment_results.json`, `artifacts/underserved_experiment_v2.json` | 입력 가정이 정한 controlled simulation. 실제 주민 영향률로 제시하지 않음. |
| Provider fallback | `artifacts/pilot_rehearsal_rc1.json`, `tests/test_provider_realism_v5.py`, `frontend/e2e/pilot-loop.spec.ts` | 현재 RC에서 재실행한 synthetic decline/replan 경로. 실제 공급자 거절이나 대체 성공으로 말하지 않음. |
| Pilot workflow | `artifacts/pilot_rehearsal_rc1.json`, `docs/PILOT_DATA_LIFECYCLE.md`, `docs/PILOT_EXECUTION_FEEDBACK_LOOP.md` | 현재 RC의 동일 synthetic context import→plan→decline/replan→approval→execution flow. `NOT FIELD RESULTS`. |
| Accessibility | `artifacts/accessibility_audit_v5_2.json`, `frontend/e2e/keyboard-accessibility.spec.ts`, `frontend/e2e/pilot-accessibility.spec.ts`, `docs/VERIFIED_METRICS.md` | 자동 keyboard/focus/responsive smoke. 수동 screen-reader 평가와 현장 접근성은 pending. |
| Privacy | `docs/PII_INVENTORY.md`, privacy-related backend tests, current secret scan in `artifacts/v5_2_rc1_acceptance.json` | automated redaction/export/error evidence와 제한을 함께 사용. 키가 Git에 없다는 점은 현재/history scan scope와 함께 표기. best-effort mask는 익명화 인증이 아님. |
| Field-pilot readiness | `docs/V5_2_FIELD_PILOT_READINESS_AUDIT.md`, `artifacts/v5_2_field_pilot_readiness_audit.json`, `artifacts/v5_2_rc1_acceptance.json` | technical readiness와 field-validation status를 분리. `FIELD_VALIDATION_PENDING` / `NOT_STARTED` 유지. |

## Claim → evidence mapping

| Claim | Evidence | Artifact | Status | 제출 사용 |
|---|---|---|---|---|
| 적은 요청 기록만으로 수요가 없다고 결론내리지 않고 조사 필요로 남긴다. | low-data evidence gates, API/frontend regression | `artifacts/proposal_acceptance_rc1.json`, `tests/test_demand.py`, `tests/test_api.py` | `IMPLEMENTED_LIMITED` | YES, prototype 기능으로 표현 |
| 제안서 R1–R13 prototype acceptance가 통과했다. | current-commit proposal acceptance runner | `artifacts/proposal_acceptance_rc1.json` | `PASS` (software acceptance) | YES, test scope와 현장 한계 병기 |
| 동일 synthetic context에서 import부터 approval·execution·post-metrics까지 실행된다. | lifecycle rehearsal invariants | `artifacts/pilot_rehearsal_v5_2_completion.json` | `SIMULATED` | YES, synthetic rehearsal로 표시할 때 |
| 통제 모의실험에서 request-count 기준안과 비교해 서비스 미배정 지역을 줄일 수 있다. | fixed-input counterfactual result and provenance | `artifacts/experiment_results.json`, `artifacts/public_value_experiment.json` | `SIMULATED` | YES, 조건·지역·예산·simulation을 함께 표시 |
| 실제 농촌에서 서비스 미배정 마을이 줄었다. | 실제 현장 결과 없음 | 없음 | `NOT_VERIFIABLE` | NO |
| 실제 공급자 availability, capacity, price, 참여 의사를 확인했다. | official directory와 local input path만 검증 | `artifacts/provider_source_audit.json`, `docs/PROVIDER_DATA_GUIDE.md` | `FIELD_VALIDATION_PENDING` | NO |
| AI가 실제 지역 수요를 정확하게 예측한다. | local longitudinal series와 forecast validation 없음 | `artifacts/forecast_backtest.json`, `docs/MODEL_CARD_DEMAND.md` | `NOT_VERIFIABLE` | NO |
| 최소 서비스 보장이 전체 주민 요청을 충족한다. | 정책은 최소 접근 기준, 자원 부족 시 미충족 유지 | `docs/OPTIMIZER_CARD.md`, `artifacts/public_value_experiment.json` | 지원하지 않는 주장 | NO |
| 승인 화면이 실제 담당자 인증 또는 조달 승인을 대체한다. | role selector는 prototype | `docs/PUBLIC_SECTOR_WORKFLOW.md`, `docs/LIMITATIONS.md` | `NOT_IMPLEMENTED` | NO |

### Safe wording

허용 예: **“통제된 모의실험에서 요청 건수 중심 기준안과 균형안의 배정 범위·비용 차이를 비교했다.”** 이 문장에 실제 농촌 성과를 덧붙이지 않습니다.

금지 예: “실제 농촌에서 소외마을을 줄였다”, “공급자 가용성이 검증됐다”, “AI가 수요를 정확히 예측한다”, “정책 효과를 입증했다”, “production ready”.

## Key numbers

제출에 쓸 수치의 단일 출처는 [VERIFIED_METRICS.md](VERIFIED_METRICS.md)입니다. 그 문서에 없는 수치는 README나 발표 자료에 새로 복사하지 말고, 원 artifact의 범위·날짜·provenance를 먼저 확인합니다.
