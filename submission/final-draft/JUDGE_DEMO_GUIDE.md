# 심사위원용 시연 안내 초안

## 2026-10-26 verified public demo route

The 2026-10-24 pre-deployment notes below are historical. Use this section for the current demo route.

Latest release is main/API SHA `5d51954a8785fcce9bd1874e5da516c30789d989` (CI `40305861335` PASS). The public Web deploy is `27d5142`; the API is `5d51954`. A browser run verified Dashboard, Hongseong Janggok selection, a complete 4M four-policy comparison, minimum-analysis endpoint, plan detail/reload, synthetic provider decline and replan, Decision Memo, CSV/PDF, and A/B session isolation (16/16 steps). A separate 5M compare verified all four policy cards and the minimum-analysis response.

### Use in the judge demo

1. Open the public Web URL, confirm the `공개 데모 · 합성/공개 데이터` notice, and show Dashboard provenance.
2. At Scenario Compare, use **4,000,000원** for the full journey. Run four policies sequentially, then show the plan, synthetic provider-decline/replan flow and exports.
3. If the judge asks for the higher budget, run **5,000,000원** compare separately. The measured one-run compare took 87.716 seconds; one 4M compare took 92.787 seconds.
4. Explain `FEASIBLE` as a feasible solver result, not an optimality proof. Minimum-cost fields in remote analysis were `NOT_PROVEN` and should be shown as such.
5. Keep the synthetic/public source labels visible. State that Gemini live inference and field outcomes have not been verified.

Screenshots: [`artifacts/qa/render_public_demo_journey_20261026_v2_0/`](../../artifacts/qa/render_public_demo_journey_20261026_v2_0/). Service details, resource limits and limitations: `docs/FINAL_REMOTE_SCENARIO_ACCEPTANCE.md` and `docs/FINAL_RELEASE_READINESS_20261026.md`.

**Caution for the live demo:** Render Free API CPU reached a minute-average 98.9% of its 0.15 vCPU limit during scenario runs. Keep this a guided, low-volume run and allow up to roughly 90 seconds for the four-policy comparison. The 5M run is compare-only evidence; it did not repeat the full provider/replan/export journey. The historical HTTP 520 root cause remains unknown.


## 2026-10-24 20시 재개 검증

동결 실행 소스 `9a8c4bed60bca57cce2941a028945b2f002c6f01`의 [CI 40073124556](https://github.com/JongHyun070105/village-coverage/actions/runs/40073124556)가 전체 성공했다. SECURITY_PASS / FULL_REGRESSION_PASS는 해당 RC 소스 범위다. 원격 endpoint 5개는 단발 조회에서 200이었으나 Render 현재 SHA·추적 branch·rollback·최종 UI 시연은 여전히 NOT_VERIFIABLE이다. 후보 배포는 NOT_DEPLOYED, 제출 준비는 PARTIAL이며 동결 완료로 표시하지 않는다. Office/영상은 미검증·미제작, Gemini는 REAL_MODEL_NOT_VERIFIED를 유지한다. 아래 기존 작성 기록은 당시 범위이며 최신 근거는 `docs/FINAL_RELEASE_AUDIT_20261024.md`를 우선한다.


## 2026-10-24 현재 안내

실행 코드 `9a8c4bed60bca57cce2941a028945b2f002c6f01`의 로컬 회귀와 공개 Render 검증을 구분한다. 최신 RC는 아직 Render에 배포하지 않았다. 공개 URL의 현재 이미지 SHA·전체 화면 흐름·안전한 rollback 확인은 NOT_VERIFIABLE이며 작동 보증된 최종 심사 링크로 확정하지 않는다.

로컬에서 확인한 촬영 순서: Dashboard → `시나리오 비교` → 지역 선택 → `4안 비교 실행` → `계획 상세·승인으로 이동` → 계획 v1 새로고침 → 해당 제공자 상세의 `데모 불참` → 계획의 `불참 1건 반영해 새 버전` → v2·같은 계획 계보 → `인쇄용 검토보고서`/`검토보고서 PDF`/`회차 CSV` → `근거·출처`. 실제 버튼 문구는 계획의 불참 건수에 따라 달라진다. 이는 로컬 UI 실행 증거이며 원격 최종 SHA 시연은 별도 수행한다.

소량 원격 관측에서 Web / 43.438초, /api/regions 29.924초, /api/schedules 0.360초 후 200이었다. API health 두 요청은 65초 timeout이었다. 약 1분 cold start는 일반적인 대기 안내이며 이번 오류의 원인으로 확정하지 않는다. 쓰기 버튼은 결과가 확인될 때까지 반복 클릭하지 않는다. 에러 후 POST 자동 재실행은 없다.

Gemini 실호출은 REAL_MODEL_NOT_VERIFIED이고 익명 AI API는 차단 상태다. 규칙 기반 Evidence Policy·CP-SAT 계산·사람의 정책 선택 및 최종 승인을 구분한다. 합성 실험 수치를 실제 주민 성과로 설명하지 않는다.

아래 가이드는 기존 작성 기록이다. 현재 원격 판정은 `docs/FINAL_REMOTE_SCENARIO_ACCEPTANCE.md`와 `docs/FINAL_RELEASE_READINESS_20261026.md`를 따른다.

## 핵심 질문

**요청 기록이 적다는 이유로 생활서비스가 필요한 마을이 공급계획에서 사라지지 않도록, 근거 공백과 정책별 결과를 함께 검토할 수 있는가?**

VillageCoverage는 서비스를 직접 제공하거나 행정 결정을 자동 승인하는 시스템이 아니라 공급계획 검토를 돕는 Pre-R&D 시제품입니다.

## 보실 흐름

1. **근거와 한계** - 공개 통계·출처가 확인된 자료, 외부 참고, 합성 운영값을 구분합니다. 부족하거나 충돌하는 근거는 조사 필요/UNKNOWN으로 남깁니다.
2. **네 정책** - 효율 중심, 균형, 소외 최소화, 최소보장 결과를 동일한 지역·예산 조건에서 비교합니다. 목적이 다른 정책이며 우열은 미리 정해져 있지 않습니다.
3. **불참 대응** - 공개 데모에서 공급자 불참은 합성 상태입니다. 반영 후 새 계획 버전과 남은 미배정 사유를 확인합니다.
4. **검토 메모** - 계획 가정·비용·미배정·근거를 정리한 초안입니다. 법적 결재나 기관 승인 기록은 아닙니다.

## 통제 합성 실험 (별도 artifact)

`artifacts/experiment_results.json`의 `experiment_1_request_count_vs_balanced`는 홍성군 장곡면 16개 권역, 예산 5,000,000원, 각 19개 서비스 단위 조건에서 요청 건수 기준안과 균형안을 비교합니다. 배정 권역은 3/16 대 12/16, 미배정은 13 대 4, 조사 필요 권역 배정은 0/8 대 7/8입니다. 이는 `SIMULATED FOR PRE-R&D` 실험이며 실제 주민 서비스·현장 효과가 아닙니다. 제품 화면의 네 정책 비교와는 별개의 실험입니다.

## 현재 원격 시연 상태

2026-10-13 새 브라우저에서 공개 웹 UI와 데모 고지는 열렸지만, 데이터 재조회 뒤 `계획 데이터를 불러오지 못했습니다`가 다시 표시되어 원격 시나리오 비교·불참·재계획·메모·내보내기 흐름은 검증하지 못했습니다. 따라서 이 URL을 작동 확인된 심사 시연 링크라고 아직 안내하지 않습니다. 제출 직전에 새 브라우저 세션으로 전체 경로를 재검증해야 합니다.

현재 저장된 제품 캡처가 있다면 그 출처 SHA와 `local synthetic E2E` 표기를 유지해야 하며, 원격 배포 화면과 동일하다고 말하지 않습니다.

## AI 역할의 정확한 범위

구조화 초안 API에는 설정 시 Gemini structured output을 쓰는 경로와 결정적 local fallback이 있습니다. 공개 데모 E2E는 외부 키 없이 fallback으로 수행합니다. 공개 원격 서비스에서 실제 생성 모델 호출이 실행되는지는 확인하지 않았습니다. 모델이 예산 배분을 직접 결정한다는 설명은 하지 않습니다.

## 심사 관점 질문과 답변 근거

공식 심사 항목은 문제정의·해결능력, AI 기술 구현·결과물 완성도, 사회문제 해결 기여, AI 기술의 창의적 응용이다. 공고에 없는 배점이나 가중치는 만들지 않았다.

| 질문 | 제출 자료에서 답할 내용 | 증거와 한계 |
|---|---|---|
| 1. 왜 중요한가? | 기록량이 적은 마을을 필요가 없는 곳으로 오판하면 계획에서 빠질 수 있다. | `VillageCoverage_성과보고서_20261023.pptx` 2장. 실제 주민 미충족 규모는 측정하지 않았다. |
| 2. 기존 방식의 한계는? | 관측 요청량만으로 접근성 격차와 미기록 필요를 충분히 알기 어렵다. | 보고서 2장 및 `docs/MODEL_CARD_DEMAND.md`; 해당 위험 가설은 현장자료로 정량 검증 전이다. |
| 3. AI는 어디에 쓰이나? | 비정형 주민 의견·현장 메모의 검토용 구조화 초안 경로다. | `backend/demand.py::structure_demand`; Gemini 설정 시 structured output, 미설정 시 결정적 fallback. 실제 공개 서비스의 모델 호출은 미검증이다. |
| 4. 최적화와 AI는 어떻게 다른가? | AI는 근거 정리 보조이고, OR-Tools CP-SAT은 명시된 목적·제약 아래 공급 계획을 계산한다. | `backend/optimization.py`, `docs/OPTIMIZER_CARD.md`; AI가 예산·정책을 직접 결정하지 않는다. |
| 5. 실제 구현은 무엇인가? | 불확실성 표시, 네 정책 비교, 불참 재계획, Decision Memo/PDF·CSV 경로. | `CLAIM_VERIFICATION.md`, `frontend/e2e/public-sector-workflow.spec.ts` 로컬 E2E 1건. 법적 결재·실제 제공자 운영은 아니다. |
| 6. 재현 방법은? | `artifacts/experiment_results.json` 조건/seed와 테스트 명령으로 확인할 수 있다. | artifact SHA는 claim ledger에 기록. 로컬 E2E는 격리 DB/합성 fixture다. |
| 7. 실제 자료와 합성자료의 차이는? | 공개 집계·고정 도로행렬은 입력자료이고 수요·관측·공급·가격은 합성 가정이다. | experiment JSON의 `experiment_scope`; 실제 주민/서비스 효과 없음. |
| 8. 정책 차이는 어디서 생기나? | 네 프리셋의 목적함수/제약 선택이 다르다. 통제 실험은 요청량 기준안과 균형안 두 개만 비교했다. | 시연 캡처와 `experiment_1_request_count_vs_balanced`를 분리해 제시한다. |
| 9. 불참하면 무엇이 달라지나? | 합성 불참 회차를 제외해 새 계획 버전을 계산하고 변경 이유를 확인한다. | Playwright E2E가 API로 불참을 입력해 v2를 확인했다. 화면 버튼을 직접 클릭하는 경로는 촬영 전 별도 확인이 필요하다. |
| 10. 공공기관이 참고할 이유는? | 비용·미배정·근거·제약을 같은 틀에서 비교해 담당자 설명과 검토를 도울 수 있다. | 기대 활용 가치이며 공공기관 운영 적합성이나 편익이 입증됐다는 뜻은 아니다. |
| 11. 수요 자료가 부족하면? | 필요를 0으로 보정하지 않고 UNKNOWN/추가 조사로 표시한다. | `backend/evidence_policy.py`, 관련 테스트; 현장 오분류율/정확도는 측정 전이다. |
| 12. 현재 검증 범위는? | 소스의 특정 로컬 E2E 1건과 합성 artifact 재대조; 원격 웹 흐름·실주민 데이터·생성형 모델 호출은 미검증. | `FINAL_PACKAGE_STATUS.md`, 공개 URL의 2026-10-13 재조회 오류 기록. |
| 13. 현장 적용 전에 무엇이 필요한가? | 주민·지자체 파일럿, 가중치/가격 합의, 제공자 검증, 보안·조달 검토, 효과 평가. | 성과보고서 4장과 `FINAL_PACKAGE_STATUS.md`; 현재 완료된 실증 성과가 아니다. |
