# VillageCoverage V5.2 RC1

## Problem

농촌 생활서비스의 요청 기록이 적은 마을을 무수요로 단정하지 않고, 공공 담당자가 근거와 공급 조건을 검토할 수 있도록 돕는 field-pilot용 의사결정 지원 prototype입니다. 새 생활서비스 전달 사업을 배포하는 제품이 아닙니다.

## Major capabilities

- 출처·신선도·품질 상태를 연결한 지역 자료, resident feedback, survey와 demand evidence workflow.
- 효율 우선, 균형, 소외 최소화, 최소 서비스 보장 4개 시나리오 비교.
- 공급자·비용·용량·거리·일정 조건과 replan, Decision Memo, review/approval flow.
- Pilot context의 명시적 CSV preview/confirm, provenance, fail-closed missing inputs, execution feedback.
- 결과의 `UNKNOWN`, `SIMULATED`, `TIME_LIMIT` 및 최적성 범위 표시.
- 지도 권역 이름을 HTML로 해석하지 않고 텍스트로 표시하도록 렌더링 경계를 보강.

## Data sources

공개 지역 데이터는 source date와 scope를 유지합니다. 자활기업과 마을기업 공식 directory snapshot을 확인된 재사용 범위에서 ingest했습니다. 사회적기업 자료는 원본 파일을 확인할 수 없어 아직 수집하지 않았고, 협동조합 자료는 재사용 조건 확인 전까지 차단합니다. Provider directory listing은 운영·가용성·가격·참여 확정이 아닙니다.

## Solver

V5.2 pilot workflow는 `BASELINE_DECOMPOSED`를 사용합니다. Geographic/rolling-horizon 코드는 회귀·벤치마크 범위에서 유지하지만 `EXPERIMENTAL`이며 기본 경로가 아닙니다. `OPTIMAL`, `FEASIBLE`, `TIME_LIMIT`, `UNKNOWN`은 구분합니다.

## Pilot workflow

같은 context에서 import, promotion, 4개 scenario, provider decline/replan, changes requested, approval, execution log, plan-vs-actual과 calibration readiness를 연결하는 synthetic rehearsal evidence가 있습니다. 이 rehearsal은 현장 결과가 아닙니다. Pilot Mode는 Demo 데이터로 대체하지 않으며, 실제 입력 누락 시 계획을 중단합니다.

## Validation

RC branch에서 실행한 test/build/proposal/failure-matrix/solver/pilot/browser/secret-audit 결과는 [VERIFIED_METRICS.md](VERIFIED_METRICS.md)와 [SUBMISSION_EVIDENCE_INDEX.md](SUBMISSION_EVIDENCE_INDEX.md)에 고정합니다. 실제 수치와 기준 SHA는 validation 완료 뒤 기록합니다.

## Known limitations and field status

- Field validation: `NOT_STARTED`.
- No verified current provider availability, actual service prices, local demand calibration, or actual execution outcomes.
- Local authentication/authorization, electronic signatures, full anonymization and retention/deletion policy are absent.
- Live external API smoke and manual screen-reader validation are outside the offline RC regression run.
- Complete directed road cache is local and not included in the repository; missing routes fail closed.
- Solver time limits, unresolved `UNKNOWN`, and unproven global route optimality remain explicit.

## Release scope

This release candidate contains documentation and demo-start cleanup plus current-tree evidence. It does not introduce a new service, model, provider source, or production feature.
