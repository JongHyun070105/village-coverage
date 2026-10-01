# Proposal requirements traceability

## Audit baseline

- Audit date: 2026-10-01
- Git baseline: `acf16d745b841d2c4409dc338de1be66ec9f14e2`
- Source: the original VillageCoverage proposal DOCX supplied with the project,
  cross-checked against the R1–R13 acceptance requirements in the V2 task.
- Scope: implemented behavior in the backend, frontend, fixtures, and tests.
  A UI label or design note alone is not counted as a workflow.
- Status at baseline: **COMPLETE 1 · PARTIAL 9 · MISSING 3 · BLOCKED 0**.

| ID | 원 제안 요구사항 | 현재 구현 | 상태 | 부족한 부분 | 구현 파일 | 테스트 |
|---|---|---|---|---|---|---|
| R1 | 인구·거리·기존 서비스·요청 기록과 기초 전화/마을조사를 함께 반영하고, 저데이터를 수요 0으로 취급하지 않는다. | 인구·가구 공개 snapshot을 SQLite에 적재하고, 조사 폼이 조사·관측·근거를 저장한다. 평가를 재계산해 관측 수·출처·최근성·누락률과 `제한적 계획 가능`을 표시하며 추가 조사 필요도 유지한다. | PARTIAL | 현재 수요 baseline과 조사는 시연용 합성자료다. 기존 서비스 일정과 요청별 과거 이력을 함께 평가하는 연동은 없고, 시설은 권역별 집계/앵커에 머문다. | `backend/database.py`, `backend/demand.py`, `backend/main.py`, `backend/optimization.py`, `data/demo.json`, `frontend/app/page.tsx`, `frontend/app/villages/[id]/page.tsx` | `tests/test_demand.py::test_deterministic_evidence_keeps_low_data_at_survey_required`; `test_recent_baseline_survey_moves_low_data_to_limited_planning`; `tests/test_database.py::test_app_database_migrates_once_and_contains_traceable_v2_tables`; `test_reference_seed_keeps_public_snapshots_and_excluded_service_policy`; `test_survey_creates_observation_and_evidence_rows`; `tests/test_api.py::test_survey_persists_synthetic_evidence_and_refreshes_low_data_assessment` |
| R2 | 전화·주민 메모·회의·대리/현장조사를 서비스·시기·날짜/시간·빈도·반복·제외/선호일·제약·근거·확신도·긴급도·후속조사로 구조화하고 사람이 검토·수정·승인한다. | Gemini JSON Schema와 규칙 기반 대체가 서비스·계절·월 빈도·요일·일부 제약을 추출하고 원문 근거 밖 결과를 거부한다. 화면은 결과 초안을 보여준다. | PARTIAL | 정확한 날짜/시간, recurring pattern, evidence source, 근거 있는 urgency가 스키마에 없고, 결과를 수정·승인해 저장하는 흐름도 없다. | `backend/demand.py`, `backend/main.py`, `frontend/app/demand/page.tsx`, `frontend/lib/api.ts` | `tests/test_demand.py::test_explicit_request_is_schema_valid_and_separated_from_route_planning`; `test_model_output_must_match_locally_supported_facts`; `test_remote_output_uses_json_schema_and_returns_canonical_verified_facts`; `tests/test_api.py::test_demand_api_uses_schema_valid_local_fallback_without_credentials` |
| R3 | 충분한 데이터에서만 반복성·시기·계절성·향후 범위를 재현 가능하게 예측하고, 부족하면 예측 대신 조사 필요를 반환한다. | 없음. 고정 시드 시뮬레이션은 테스트용 운영 입력 생성이며 관측 이력 기반 예측이 아니다. | MISSING | 충분도에 따른 forecast 가능 여부, 결정론적 범위 모델, 불확실성 표현이 없다. | `backend/demand.py`, `backend/simulation.py`는 인접 기능만 제공; forecast 구현 파일/API/UI 없음 | 예측 테스트 없음 |
| R4 | 공급자가 지역·서비스별 향후 3개월 예상 회차 범위·시기·신뢰도·충분도를 비구속 전망으로 본다. | 없음. | MISSING | 3개월 forecast 데이터/API/UI와 `NON-BINDING FORECAST` 고지가 없다. | forecast 구현 파일/API/UI 없음 | 전망 테스트 없음 |
| R5 | 서비스·거점·요일/시간·일/월 용량·최대 이동·최소보상·참여이력을 가진 Provider를 모델링하고 회차별 AVAILABLE/OPTED_IN/DECLINED/UNAVAILABLE 상태를 관리한다. | SQLite Provider/서비스/가용시간/회차/참여 모델과 공급자 목록·상세, 서비스/시간/월 용량 검사, 회차별 참여/불참 저장 화면이 있다. 기회와 공급자 속성은 합성 시드다. | PARTIAL | 회차 기회가 optimizer 결과·Kakao 경로·예산/시간창 제약에서 생성되지 않는다. provider별 일정 최적화 및 미정 이동비용 연결이 남았다. | `backend/database.py`, `backend/main.py`, `frontend/app/providers/page.tsx`, `frontend/app/providers/[id]/page.tsx`, `frontend/lib/api.ts` | `tests/test_database.py::test_provider_profiles_history_availability_and_opt_in_persist`; `test_provider_opt_in_rejects_unsupported_service_unavailability_and_capacity`; `tests/test_api.py::test_provider_directory_detail_and_round_opt_in_are_persistent`; `test_provider_opt_in_rejects_unsupported_service_and_unknown_round` |
| R6 | 반복 참여·완료 이력과 신뢰도를 바탕으로 장기협약 검토 후보를 제안하되 계약을 자동 체결하지 않는다. | 최근 12회 합성 이력에서 수락·완료·불참·취소·완료율을 계산하고 반복 참여 후보를 표시한다. 자동 계약은 없다. | COMPLETE | 이력은 검증된 실제 사업자 운영자료가 아닌 합성 시연 입력이다. | `backend/database.py`, `backend/main.py`, `frontend/app/providers/[id]/page.tsx` | `tests/test_database.py::test_provider_profiles_history_availability_and_opt_in_persist`; `tests/test_api.py::test_provider_directory_detail_and_round_opt_in_are_persistent` |
| R7 | 효율 우선안이 회차·충족/미충족 권역·이동비/시간·사용/잔여 예산을 제공한다. | CP-SAT이 회차·권역별 충족·미충족·이동시간/비용·총 사용액/잔액을 계산한다. 경로는 중앙 권역과 각 권역 간 왕복 합이다. | PARTIAL | 이동거리 출력과 실제 provider/일정 배정이 없고, 독립 왕복이므로 실제 운행 일정/비용이 아니다. | `backend/optimization.py`, `backend/travel.py`, `backend/main.py`, `frontend/app/page.tsx` | `tests/test_optimization.py::test_scenarios_obey_budget_capacity_demand_and_seed_invariants`; `test_incomplete_travel_matrix_never_uses_straight_line_distance` |
| R8 | 균형안이 서비스량·지역 분산·고령/고령 1인가구·저데이터·미충족·집중도·이동비의 정책 trade-off를 드러낸다. | 균형 목적식은 서비스량을 먼저 보존하고 권역 수·조사 필요 권역·취약도·집중도·이동비/시간을 사전식으로 비교한다. 화면에 효율안 대비 차이를 표시한다. | PARTIAL | 정책 가중치/우선순위를 사용자가 설정할 수 없고 실제 provider·미충족 대기기간은 반영하지 않는다. | `backend/optimization.py`, `backend/settings.py`, `frontend/app/page.tsx`, `docs/OPTIMIZATION_MODEL.md` | `tests/test_optimization.py::test_scenarios_have_distinct_policy_outcomes`; `test_balanced_vulnerability_scale_is_centralized_and_normalized`; `test_balanced_preserves_maximum_service_volume_and_prioritizes_area_count` |
| R9 | 권역별 최소 기준을 설정하고 불가능하면 required/current budget·gap·충족/미충족 권역·필요/부족 용량을 정직하게 공개한다. | 최소 권역 수를 우선하는 시나리오와 필요예산·예산 gap·covered/uncovered·aggregate capacity feasibility가 있다. 예산 또는 capacity 부족 시 100% 달성을 주장하지 않는다. | PARTIAL | 기준이 월 1회로 고정되고, required/missing capacity를 회차 단위로 보여주지 않으며 원인별 불가 설명이 부족하다. | `backend/optimization.py`, `backend/main.py`, `frontend/app/page.tsx` | `tests/test_optimization.py::test_minimum_coverage_does_not_claim_success_below_required_budget`; `test_minimum_budget_achieves_all_areas_when_fully_funded`; `test_budget_and_demand_inputs_are_fail_closed_but_capacity_gap_is_reported` |
| R10 | 시나리오별 공급자 이동시간/거리·회차·서비스비·이동비·최소보상·총액·추가 공공재원을 공개하고 모르는 비용을 0원으로 위장하지 않는다. | 시나리오 총액은 모의 회차 단가와 Kakao 왕복 이동비로 구성되고 이동시간/이동비·추가 필요예산을 일부 반환한다. | PARTIAL | 이동거리, provider minimum compensation, service/travel/minimum-pay/subsidy별 합계 breakdown이 없고 미산정 항목의 상태값도 없다. | `backend/optimization.py`, `backend/travel.py`, `frontend/app/page.tsx`, `docs/OPTIMIZATION_MODEL.md` | 경로 cache 테스트는 `tests/test_travel.py`; 비용 항목 합계/최소보상/보조금 테스트 없음 |
| R11 | 예산 부족 시 실패만 반환하지 않고 미충족 권역·용량 부족·예산 gap·서비스 공급 부재 등 충족하지 못한 기준을 공개한다. | 결과에 미충족 권역 수와 assignment 상태, 최소안의 예산 gap 또는 capacity feasibility를 표시한다. | PARTIAL | 권역별 실패 원인을 예산·공급자 부재·시간·용량·데이터 부족으로 분류하지 않는다. 공급자별 제약도 없어 원인 증명이 불가능하다. | `backend/optimization.py`, `frontend/app/page.tsx`, `frontend/app/villages/[id]/page.tsx` | 최소예산/capacity 테스트는 `tests/test_optimization.py`; 원인 분류 테스트 없음 |
| R12 | AI는 비정형 기록 구조화·제한적 수요패턴 보조만 맡고 route/allocation/schedule/capacity/budget은 최적화 엔진이 결정한다. | Gemini 또는 결정론적 parser는 메모 초안을 만든다. OR-Tools CP-SAT이 budget/capacity 제약의 권역 회차를 정하고 Kakao road matrix가 이동 비용·시간을 제공한다. | COMPLETE | 이 분리는 현재 구현에서 확인됨. 향후 forecast도 LLM이 숫자/배정을 결정하지 않도록 경계를 유지해야 한다. | `backend/demand.py`, `backend/optimization.py`, `backend/travel.py`, `backend/main.py`, `docs/ARCHITECTURE.md`, `docs/OPTIMIZATION_MODEL.md` | `tests/test_demand.py::test_explicit_request_is_schema_valid_and_separated_from_route_planning`; `tests/test_optimization.py::test_scenarios_obey_budget_capacity_demand_and_seed_invariants` |
| R13 | 의료·법률 등 인허가 대상 서비스는 초기 공급 범위에서 제외하고 추가 시 REGULATED/EXCLUDED로 통제한다. | 최적화 단가는 세탁·생필품·주거수리만 받지만 구조화 parser는 병원동행/이동지원을 유효 서비스로 추출한다. 별도 서비스 정책 registry는 없다. | PARTIAL | 추출 단계에서 규제/제외 서비스를 거부·검토 상태로 전환하지 않고, 서비스 추가 시 규제 여부를 관리하는 모델/테스트가 없다. | `backend/demand.py`, `backend/optimization.py`, `frontend/app/demand/page.tsx`, `frontend/lib/types.ts` | 금지/규제 서비스 제외 테스트 없음 |

## 구현 추적 순서

이 감사는 기능 완료 보고가 아니다. 상태는 각 세로 기능을 구현하고 관련 자동/브라우저 테스트를 추가할 때마다 다시 확인한다.

### 진행 기록 (2026-10-01)

- Phase A traceability 감사는 `fce05b4`로 커밋하고 `origin/v2-proposal-complete`에 push했다.
- Phase B/C 첫 수직 조각은 버전 관리 SQLite schema, 공개 인구/가구 snapshot 적재, synthetic Survey → DemandObservation/DemandEvidence 저장, DemandAssessment 재계산, 권역 상세 조사 폼/이력까지 구현했다.
- R1은 기존 서비스·요청별 실측 이력이 아직 없어 PARTIAL이다. R2의 AI 구조화 결과 수정·승인 저장, provider 일정·경로 통합, forecast 및 이후 단계는 미완료다.
- 조사 여정 브라우저 확인: 저데이터 `장곡면 도산리` synthetic phone survey 1건을 등록하고 `조사 필요 · 2건`에서 `제한적 계획 가능 · 3건`으로 바뀌는 응답과 저장 이력을 확인했다. 이 검증은 `/tmp/village-coverage-e2e.sqlite`를 사용했다.
- Phase D provider slice: schema v2 migration, provider/service/weekly availability, 12회 synthetic participation history, 4 upcoming rounds/provider, capability/month-cap checks, participation API, provider list/detail and opt-in/decline UI added. R5 remains PARTIAL until rounds derive from provider-specific optimization and road routes; R6 is COMPLETE for the prototype because the review-only agreement signal is calculated and shown. Browser opt-in state persisted in `/tmp/village-coverage-provider-qa-2.sqlite`.
- Provider browser QA initially exposed concurrent first-request SQLite lock during repeated page effects. Connection initialization now serializes within the app process and no longer re-runs `journal_mode=WAL` on every connection; the provider journey was reloaded and checked against the migrated schema.

1. Survey와 demand evidence를 저장하고 assessment를 재계산한다 (R1, R2).
2. Provider/회차 opt-in/참여 이력은 합성 prototype 흐름을 구현했다. optimizer·road route를 쓰는 provider별 일정/여정은 남았다 (R5 partial, R6 complete).
3. provider별 일정·다중 경유 경로·원인별 infeasibility와 비용 breakdown을 연결한다 (R5, R7–R11).
4. 충분도에 fail-closed하는 재현 가능한 3개월 전망과 공급자 화면을 만든다 (R3, R4).
5. 정책 입력, multi-region, CSV import, calendar, provenance/export, proposal acceptance checker를 연결한다.
6. R1–R13 자동/브라우저 acceptance와 전체 사용자 여정을 현재 코드에서 다시 실행한다.
