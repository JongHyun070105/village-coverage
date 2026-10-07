# 제출 주장과 근거 경로

수치를 제출할 때는 아래 근거를 원본 artifact와 다시 대조한다. 성과보고서 본문에서 가장 강하게 보여줄 수치는 `SIMULATED` 실험 하나로 제한한다. 자동 테스트 숫자는 제품 가치가 아니라 보조 신뢰 근거다.

| Claim | Public wording | Evidence file | Synthetic / Real | Safe to submit? | Notes |
|---|---|---|---|---|---|
| 낮은 요청만으로 마을 수요를 0으로 만들지 않고 근거가 부족하면 조사를 표시한다. | “관측이 적거나 충돌하는 경우 수요를 단정하지 않고 조사 필요로 남긴다.” | `backend/evidence_policy.py`, `backend/demand_model.py`, `docs/MODEL_CARD_DEMAND.md`, `artifacts/proposal_acceptance_rc1.json` | 기능 구현; 실제 현장 적용 자료 없음 | YES, prototype 기능으로만 | 이 기능이 실제 제외 마을을 줄였다고 쓰지 않는다. |
| 공개 지역자료를 사용했다. | “행정구역·인구·가구·시설 집계 자료를 출처·기준일과 연결했다.” | `docs/DATA_PROVENANCE.md`, `data/demo.json`, `artifacts/data_quality_report.json`, `artifacts/public_schema_manifest.json` | REAL PUBLIC DATA (집계/범위 제한) | YES, 출처·기준일 병기 | 재사용 범위와 일부 영역의 자료 차이를 문서 기준으로 표현. |
| 공식 디렉터리 데이터를 연결했다. | “자활기업·마을기업 디렉터리의 등재정보를 공급 후보 참고로 사용했다.” | `docs/DATA_PROVENANCE.md`, `artifacts/provider_source_audit.json`, `data/provider_snapshots/` | REAL DIRECTORY | YES, 실제 공급 확정이 아니라고 병기 | 등재는 가용성·가격·참여를 뜻하지 않는다. |
| KREI 근거를 사용했다. | “KREI 자료를 외부 경험적 사전정보로 분리해 기록했다.” | `docs/MODEL_CARD_DEMAND.md`, `backend/empirical_priors.py`, `artifacts/empirical_prior_snapshot.json` | EXTERNAL PRIOR | YES, 지역 관측으로 표현하지 않을 때 | 마을 단위 방문량으로 환산하지 않는다. |
| HomeDoctor 데이터로 방법을 검토했다. | “외부 운영자료를 별도 데이터 영역의 forecast backtest에 사용했다.” | `docs/MODEL_CARD_DEMAND.md`, `artifacts/home_doctor_snapshot.json`, `artifacts/forecast_backtest.json` | EXTERNAL OPERATIONAL REFERENCE | 제한적으로 YES | 농촌 수요나 성능 정확도 증거로 쓰지 않는다. |
| 주민의견/설문 입력을 다룰 수 있다. | “제품에 설문·주민 의견 입력과 근거 검토 흐름을 구현했다.” | `docs/RESIDENT_FEEDBACK_WORKFLOW.md`, `frontend/e2e/pilot-loop.spec.ts`, `artifacts/v5_2_rc1_visual_qa/manifest.json` | 기능 시연은 synthetic/demo | YES, “현재 주민자료 수집”이라고 하지 않을 때 | 실제 주민 설문·의견을 확보했다는 근거는 없음. |
| AI가 비정형 기록을 구조화하고 근거 부족 시 추정을 억제한다. | “AI는 확인 가능한 구조화 초안을 보조하고, 불충분한 입력은 조사 필요로 남긴다.” | `docs/MODEL_CARD_DEMAND.md`, `backend/demand_model.py`, `backend/evidence_policy.py`, `docs/PROPOSAL_REQUIREMENTS_TRACEABILITY.md` | implemented prototype; local accuracy unverified | YES, 범위·검토자 명시 | AI가 정답·공급배정을 결정한다고 하지 않는다. |
| 최적화 엔진이 실제 제약 계산을 수행한다. | “별도 CP-SAT 엔진이 예산·용량·권역·경로/일정 조건의 계획안을 계산한다.” | `docs/OPTIMIZATION_MODEL.md`, `docs/OPTIMIZER_CARD.md`, `backend/scheduling.py` | algorithm run on synthetic inputs | YES, 모델·입력 가정 설명 | 제한시간 초과를 최적성 완료로 세지 않는다. |
| 두 정책의 미배정 권역 차이 | “홍성군 장곡면 통제 합성 실험에서 500만원, 19개 서비스 단위 조건의 미배정 권역은 요청 기준안 13곳, 균형안 4곳이었다.” | `artifacts/experiment_results.json` → `experiment_1_request_count_vs_balanced`; `docs/VERIFIED_METRICS.md` | SIMULATED FOR PRE-R&D | YES, 이 문구와 조건을 같이 표시 | 두 안 모두 16곳 대상, 19개 단위. 조사 필요 권역 배정은 0/8 대 7/8. 실제 서비스·효과가 아니다. |
| 4개 정책을 비교한다. | “효율·균형·소외 최소화·최소보장 정책을 비교하도록 구현했다.” | `docs/OPTIMIZATION_MODEL.md`, `backend/governance.py`, `docs/PUBLIC_SECTOR_WORKFLOW.md` | implementation + synthetic runs | YES, 정책 의미로만 | 같은 입력/실험의 4개 결과를 모두 보인다고 하지 않는다. |
| 공급자 거절 후 재계획을 실행한다. | “합성 시연 흐름에서 공급자 거절 입력 후 새 계획 버전을 만들 수 있다.” | `artifacts/pilot_rehearsal_rc1.json`, `docs/PROVIDER_FALLBACK_POLICY.md`, `frontend/e2e/pilot-loop.spec.ts` | SYNTHETIC REHEARSAL | YES, 시뮬레이션으로 표시 | 실제 공급자 응답이나 공급 성공이 아님. |
| Decision Memo가 검토 자료로 연결된다. | “계획 가정·비용·미배정 근거를 검토 메모로 확인할 수 있다.” | `backend/decision_memo.py`, `docs/DECISION_MEMO_GUIDE.md`, `artifacts/v5_2_rc1_visual_qa/` | prototype UI; synthetic/demo content | YES, 초안/데모 고지 | 법적 결재나 실제 행정 승인으로 표현하지 않는다. |
| backend 자동 테스트 수 | “RC 코드 검증에서 backend 562 passed, 1 skipped를 기록했다.” | `docs/VERIFIED_METRICS.md` | automated test | YES, 코드 검증으로 한정 | 테스트 수행 source SHA `fe2c10486b5f05559619e0cdbdb6b71ac1deb7e3`; 이 문서 수정 branch에서 다시 실행한 숫자가 아님. |
| Browser E2E | “RC 브라우저 자동화 12개 시나리오를 통과했다.” | `docs/VERIFIED_METRICS.md`, `artifacts/v5_2_rc1_visual_qa/manifest.json` | automated synthetic E2E | YES, prototype 동선 검증으로 한정 | source SHA `fe2c10486b5f05559619e0cdbdb6b71ac1deb7e3`. |
| 제안 수용성 R1–R13 | “요구 수용성 112 테스트가 통과했다.” | `artifacts/proposal_acceptance_rc1.json`, `docs/VERIFIED_METRICS.md` | software acceptance | YES, 현장 성과와 구분 | source SHA는 위와 같음. |
| pilot lifecycle 전체 흐름 | “합성 same-context rehearsal에서 import부터 재계획·승인·실적 연결까지 시연했다.” | `artifacts/pilot_rehearsal_rc1.json`, `artifacts/pilot_rehearsal_v5_2_completion.json`, `docs/V5_2_FIELD_PILOT_READINESS_AUDIT.md` | SYNTHETIC REHEARSAL | YES, NOT FIELD RESULTS를 표시할 때 | 계획·실행 기록은 모두 시뮬레이션이다. |
| solver invariants | “30·50·100·200 권역 smoke에서 invariant 위반은 0이었다.” | `artifacts/v5_2_solver_smoke_rc1.json`, `docs/VERIFIED_METRICS.md` | synthetic solver smoke | 제한적으로 YES | 30/100/200은 `TIME_LIMIT`; 50만 `OPTIMAL`. 이를 전 규모 최적해나 속도 보장으로 쓰지 않는다. |
| 현장 성과·효과 | “실제 지역에서 소외 마을이 줄었다.” | 없음 | no field validation | **NO** | Field validation `NOT_STARTED`. |
| 농촌 수요 예측 정확도 | “AI가 농촌 수요를 정확히 예측한다.” | 로컬 검증 자료 없음 | no local calibration | **NO** | 현장 데이터와 지역 보정 프로파일이 없다. |
| 실제 공급자 가격·참여 | “지역 제공자의 가용량·가격·참여가 확인됐다.” | 없음 | no field confirmation | **NO** | public directory와 synthetic capacity/price는 구분한다. |
| production readiness | “공공기관 운영에 바로 쓸 수 있다.” | 없음; production auth/authorization 부재 | not production | **NO** | field-pilot-ready prototype으로만 설명한다. |

## 수치 복사 규칙

- 500만원·19개 단위·16개 권역·미배정 13→4·조사 필요 권역 0/8→7/8은 위 `experiment_1_request_count_vs_balanced`만 근거로 사용한다.
- 4개 정책의 존재는 구현 사실로 설명할 수 있지만, 별도 `pilot_rehearsal_rc1.json` 숫자와 이 실험 숫자를 하나의 동일 실험처럼 결합하지 않는다.
- 자동 테스트 결과는 전체 RC application source SHA `fe2c10486b5f05559619e0cdbdb6b71ac1deb7e3` 기준 evidence다. branch HEAD `c49a3a62c7b47094ab33c7d5807f23a0653824f0`와 같은 검증 커밋이라고 말하지 않는다.
