# VillageCoverage 제출 주장 검증표

## 2026-10-26 release evidence update

Earlier evidence tables below are preserved as dated snapshots; this table records the current public release.

| Claim | Current status | Source and safe wording |
|---|---|---|
| Public Render can display four computed policy cards for a 4M input | `EXEC PASS` | 4M synthetic/public demo journey, 16/16; cite `docs/FINAL_REMOTE_SCENARIO_ACCEPTANCE.md` |
| Four policies also completed for 5M | `EXEC PASS` | Separate remote compare-only run; one sample, 87.716s |
| A numeric minimum required budget is proven | `NOT_VERIFIABLE` | Remote minimum-analysis endpoint returned 201 but both minimum values were null/`NOT_PROVEN` |
| Provider decline → replan → memo and exports work in the guided demo | `EXEC PASS` | 4M public browser journey; decline state is synthetic |
| Session A's plan data are isolated from session B | `EXEC PASS` | Browser B received expected 404 for A's plan and provider round |
| Historical HTTP 520 cause is known | `NOT_VERIFIABLE` | Browser trace showed Cloudflare 520; overlapping FastAPI 201 has no shared ID |
| Request correlation works in the current runtime code | `EXEC PASS` | Diagnostic ran after logger code deploy `5d51954`; current API `1fb24d1` is docs-only over that runtime code. Browser 422 response ID matched one Render API completion log; no payload/cookie saved |
| Render Free has ample concurrent solver capacity | `NOT_VERIFIABLE` | API CPU minute-average reached 98.9% of 0.15 vCPU during sequential runs |
| Live Gemini inference or field outcomes were verified | `NOT_VERIFIABLE` | No live model call or field pilot was performed |

Use synthetic/public-data labels, show actual solver status, and describe Decision Memo as a staff-review draft. Screenshots with SHA-256 manifest: `artifacts/qa/render_public_demo_journey_20261026_v2_0/`.


## 2026-10-24 20시 재개 검증

동결 실행 소스 `9a8c4bed60bca57cce2941a028945b2f002c6f01` 및 CI 40073124556 결과는 당시 RC의 역사적 기록이다. 원격 미배포와 PARTIAL 판정도 위 release v2.0 표로 대체됐다. Office 렌더, 영상, Gemini 실호출, 현장 효과는 현재도 별도 미검증 항목이다.


## 2026-10-24 검증 범위 갱신

최종 통합 실행 코드 SHA: `9a8c4bed60bca57cce2941a028945b2f002c6f01`. 원본 실험 JSON SHA-256 `4d984db66fc9b90624dbbb1a26245b6e7f52b3b89e77e44a381c05dfb2cf24eb`는 유지했다. 원본 수치·합성 데이터 고지·보고서 바이너리는 변경하지 않았다.

| 주장 | 증거 수준 | 이번 실행 결과와 한계 |
|---|---|---|
| 최신 Next/React 보안 수정이 RC에 있다 | EXEC PASS / STATIC | 16.4.3/19.2.9 설치, 전체·Production audit 0, 두 vendored RSC 서버 파일을 공식 수정과 SHA-256 비교. 원격 패치 완료 주장은 아님 |
| UI 불참·재계획·내보내기와 브라우저 격리 | EXEC PASS, local synthetic | 실제 로컬 Chromium 화면 버튼과 3개 세션 테스트 통과. 원격 최신 RC 검증은 SKIP |
| 최종 공개 Render 버전을 검증했다 | NOT_VERIFIABLE | 현재 이미지 SHA·rollback 확인 도구가 없고 신규 배포를 하지 않음 |
| 실제 Gemini 추론을 실행했다 | NOT_VERIFIABLE | REAL_MODEL_NOT_VERIFIED 유지. 외부 모델 호출·비밀키 조회 없음 |
| 공식 Office 레이아웃이 최종 검증됐다 | NOT_VERIFIABLE | 원본 바이너리 해시·PPT 4장 STATIC 확인. Office 네이티브 렌더 없음 |
| 참가신청·영상까지 제출 완료 | USER_CONFIRMATION_REQUIRED / SKIP | 개인 정보·동의·서명·IP·가점 미확인, VIDEO_NOT_RENDERED, 메일 미발송 |

아래 표는 원본 제출 패키지의 주장·출처 기록이다. 과거 검증 SHA는 그대로 보존하며 현재 결과는 위 갱신 및 최종 감사 JSON을 우선한다.

검토 기준 브랜치: `submission/official-package-20261013`<br>
검토 기준 소스 SHA: `b6ff52adb2fa8b4287e6c62250802d8c07196907`<br>
범위: 현재 저장소 코드·테스트·실험 결과. 공식 공고와 사용자 제공 제안 취지는 별도 출처로 구분한다.

| CLAIM | EVIDENCE_FILE | SOURCE_SHA | DATA_TYPE | ASSUMPTIONS | LIMITATION | SUBMISSION_SAFE |
|---|---|---|---|---|---|---|
| 관측이 없거나 적다는 이유만으로 실제 필요를 0으로 단정하지 않고, 근거가 불충분·충돌하면 조사 필요 또는 예측 불가로 남긴다. | `backend/evidence_policy.py`, `backend/demand_model_v4.py`, `docs/MODEL_CARD_DEMAND.md`, `tests/test_demand_model_v4.py` | `b6ff52a…` | 구현 코드·합성 테스트 | 근거 상태와 날짜는 제공된 입력을 반영한다. | 실제 현장 관측·정확도 보정은 없다. | YES - 기능 설계로만 서술 |
| 비정형 조사 메모를 검토 가능한 구조화 초안으로 만드는 코드 경로가 있다. Gemini 구조화 출력은 설정된 경우 사용하며, 미설정 시 결정적 규칙 fallback을 쓴다. 담당자 검토 전에는 승인 근거로 사용하지 않는다. | `backend/demand.py::structure_demand`, `backend/main.py`의 demand draft API, `tests/test_demand.py`, `tests/test_api.py` | `b6ff52a…` | 구현 코드·합성 테스트 | 생성 모델 호출은 API 설정에 좌우된다. | 이번 로컬 공개 데모 E2E는 Gemini 키를 비운 fallback 설정이다. 원격 공개 데모의 실제 모델 호출과 예측 정확도는 확인하지 않았다. | YES - "구조화 초안 지원" 및 설정 조건을 같이 표기 |
| OR-Tools CP-SAT이 예산·용량·권역·이동/일정 제약 아래 공급안을 계산한다. | `backend/optimization.py`, `backend/scheduling.py`, `docs/OPTIMIZATION_MODEL.md`, `docs/OPTIMIZER_CARD.md` | `b6ff52a…` | 구현 코드·모델 출력 | 공급량·가격·가용성 등 운영값은 데모에서 합성값이다. | `FEASIBLE`, `TIME_LIMIT`, `UNKNOWN`은 최적성 증명이 아니다. | YES - solver 상태와 입력 가정을 병기 |
| 제품은 효율 중심, 균형, 소외 최소화, 최소보장 4개 정책을 같은 화면에서 비교하도록 구현되어 있다. | `backend/optimization.py::compare_policies`, `frontend/app/scenarios/page.tsx`, `tests/test_optimization.py` | `b6ff52a…` | 구현 코드·합성 실행 | 비교 조건이 같을 때 정책 목적 차이를 보여준다. | 정책 가중치는 시제품 선택이며 현장 검증·사회적 우열은 확정되지 않았다. | YES - 정책 목적 비교로만 서술 |
| 격리 로컬 브라우저 E2E에서 네 정책 비교, 합성 제공자 불참 후 새 계획, PDF·CSV 다운로드가 통과했다. | `frontend/e2e/public-sector-workflow.spec.ts`; `evidence/source/scenario-comparison.png`, `evidence/source/plan-replanned.png`; `CAPTURE_MANIFEST.md` | 실행 대상 소스 SHA `b6ff52adb2fa8b4287e6c62250802d8c07196907` | 로컬 Playwright E2E 1건·합성 fixture | 이 실행은 외부 모델 키 없이 task worktree의 격리 DB로 수행했다. | 불참은 테스트에서 API로 입력했으며 공개 Render 브라우저는 데이터 재조회 실패. 원격 운영 흐름·실제 제공자 상태를 입증하지 않는다. | YES - 로컬 합성 E2E라고 명시 |
| 요청 건수 기준안과 균형안은 통제된 합성 실험에서 각각 19개 단위를 배정했다. | `artifacts/experiment_results.json#experiment_1_request_count_vs_balanced`; 보조 `docs/VERIFIED_METRICS.md` | `b6ff52a…`; JSON SHA-256 `4d984db66fc9b90624dbbb1a26245b6e7f52b3b89e77e44a381c05dfb2cf24eb` | SIMULATED FOR PRE-R&D; 홍성군 장곡면 공개 집계·고정 도로행렬 + 합성 관측/수요/공급/가격 | 16개 권역, 월 예산 5,000,000원, 조사 필요는 합성 관측 4건 미만. | 실제 주민 서비스나 효과가 아니다. 이 두 정책 실험을 4개 정책 전체 성능 비교로 일반화하지 않는다. | YES - 조건·합성 한계를 같은 화면에 표시 |
| 같은 실험에서 배정 권역은 요청량 기준 3/16, 균형 12/16; 미배정 13 대 4; 조사 필요 권역 배정 0/8 대 7/8이다. | `artifacts/experiment_results.json#experiment_1_request_count_vs_balanced` | `b6ff52a…`; JSON SHA-256 `4d984db66fc9b90624dbbb1a26245b6e7f52b3b89e77e44a381c05dfb2cf24eb` | SIMULATED FOR PRE-R&D | 동일 실험·동일 예산·각 19개 단위 결과의 비교다. | 실제 마을 수요·제공·효과를 나타내지 않는다. | YES - "SIMULATED FOR PRE-R&D"를 숫자 바로 옆에 표기 |
| 모델상 거점 왕복 이동비는 요청량 기준 612,525원, 균형 432,899원이다. | 위 JSON의 `travel_cost_won` | `b6ff52a…`; JSON SHA-256 `4d984db66fc9b90624dbbb1a26245b6e7f52b3b89e77e44a381c05dfb2cf24eb` | 합성 입력 기반 모델 추정치 | 권역별 거점 왕복 캐시 거리와 모델 단가를 쓴다. | 실제 지자체 집행액이나 다중 경유 경로가 아니다. 본문에서는 보조 수치로만 쓴다. | YES - "모델 이동비" 명칭과 가정을 동반 |
| 합성 시연에서 제공자 불참 상태를 반영해 다른 계획 버전을 만들 수 있다. | `backend/main.py`의 participation/replan 경로, `backend/provider_fallback.py`, `frontend/e2e/public-sector-workflow.spec.ts`, `frontend/e2e/pilot-loop.spec.ts` | `b6ff52a…` | 구현 코드·로컬 합성 E2E | 제공자 거절은 직접 조작한 demo 입력이다. | 실제 제공자 참여·수락·서비스 완료를 뜻하지 않는다. 원격 서비스의 현재 E2E는 별도 상태다. | YES - 합성 시연·재계획으로 표현 |
| Decision Memo는 정책·비용·미배정 근거를 담는 검토 초안이다. | `backend/decision_memo.py`, `frontend/app/plans/page.tsx`, `tests/test_decision_memo.py` | `b6ff52a…` | 구현 코드·합성 데이터 | 입력 계획과 근거 상태를 반영한다. | 법적 결재, 기관 인증, 실제 승인 기록이 아니다. | YES - "검토 메모 초안"으로 표기 |
| 과거 자동 테스트 수치는 해당 당시 실행 SHA의 소프트웨어 검증이다. | `docs/VERIFIED_METRICS.md`, `artifacts/v5_2_rc1_visual_qa/manifest.json` | 과거 source SHA `fe2c10486b5f05559619e0cdbdb6b71ac1deb7e3` | 자동 회귀/E2E | 과거 해당 트리와 synthetic fixture 실행에 한정한다. | 현재 브랜치의 새 실행이나 현장 효과가 아니다. 보고서의 성과 숫자로 사용하지 않는다. | NO - 성과보고서 숫자에서 제외 |
| 10월 12일 사전질의 답변은 사용자가 이전 질문에 대해 직접 작성한 답변이다. | 현재 사용자 제공 지시(저장소에 원문 파일 없음) | `USER_PROVIDED_CONTEXT`; 파일 SHA 없음 | 사용자 진술에 따른 제안 취지 | 이 자료는 제안 방향 설명용이다. | KEIT가 개별 구현·가중치·가격을 승인했다는 뜻이 아니다. | YES - 사용자 제안 취지로만 귀속하고 공식 승인 근거로 쓰지 않음 |
| VillageCoverage가 과거 후보작 목록에 실렸다. | `submission/forms/original/2026_AI_Life_Idea_Candidate_List.pdf` | PDF SHA-256 `43fe8cb931a8548eb657b6521ab4f408b8b32a3b63f3944ad2534ffa21817e94` | KEIT 공식 후보작 목록 | 목록은 제목대로 수상 후보작 목록이다. | 후보 등재만으로 입상, 아이디어 번호, 5점 가점 자격이 확정되지 않는다. | YES - 후보 등재 사실로만 표현 |

## 금지된 제출 표현

- 실제 주민에게 서비스가 제공되었다, 9개 마을을 실제로 추가 지원했다.
- AI가 예산 배분을 직접 결정하거나 농촌 수요를 정확히 예측한다.
- 제공자 가격·가용량·참여가 확인되었다.
- 모델 이동비를 실제 집행비·절감액으로 표현한다.
- 네 정책 모두가 `experiment_1_request_count_vs_balanced`에서 비교되었다.
- 후보작 등재를 수상 확정 또는 자동 5점 가점으로 표현한다.
- 사용자 측 사전질의 답변을 KEIT의 개별 기술 승인으로 표현한다.
