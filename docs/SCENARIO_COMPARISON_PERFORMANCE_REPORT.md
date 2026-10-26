# Scenario Comparison Performance Report

**측정 시각:** 2026-10-26 14:37 KST
**측정 commit:** `ad2a4d1eba8932e810f9acb94da7817caf9a9fce`
**환경:** Python 3.12.15, OR-Tools 9.15.6755, Node 22.12.0, Next.js 16.4.3, local production standalone + FastAPI 1 worker
**데이터:** Hongseong Janggok 16-area public-demo synthetic fixture, cached synthetic routes, 5,000,000원, default balanced policy

## 로컬 API profile

실제 앱의 FastAPI TestClient 경로로 네 정책을 순차 실행하고, 각 schedule의 explanations와 minimum-coverage 분석을 호출했다. 모든 schedule 응답은 201이었고 각 explanations에는 16개 권역이 있었다.

| 단계 | HTTP 결과 | 경과시간 | CP-SAT 실행 | 요약 |
|---|---:|---:|---:|---|
| efficiency schedule | 201 | 3.946초 | 3회, 합 3.874초 | FEASIBLE, 21 units, 4,848,375원 |
| efficiency explanations | 200 | 5.44ms | 0회 | 16 areas |
| balanced schedule | 201 | 5.168초 | 3회, 합 5.096초 | OPTIMAL, 18 units, 4,924,687원 |
| balanced explanations | 200 | 6.05ms | 0회 | 16 areas |
| minimum_coverage schedule | 201 | 5.330초 | 6회, 합 5.256초 | TIME_LIMIT, feasible incumbent 18 units, 4,777,176원 |
| minimum_coverage explanations | 200 | 5.20ms | 0회 | 16 areas |
| underserved_first schedule | 201 | 7.439초 | 6회, 합 7.364초 | TIME_LIMIT, feasible incumbent 18 units, 4,841,570원 |
| underserved_first explanations | 200 | 5.81ms | 0회 | 16 areas |
| minimum-coverage analysis | 201 | 5.751초 | 14회, 합 5.643초 | `_scenario_data` 487ms, DB save 3.63ms |

로컬 HTTP POST 경과시간 합계는 약 27.63초(네 schedule 약 21.88초 + 분석 5.75초)이며 설명 GET은 각각 5–6ms다. 이 값은 한 번의 로컬 합성 측정이며 Render Free 성능을 대변하지 않는다.

## 계산 비용 해석

- API 응답시간 대부분을 CP-SAT 호출이 차지했다. fixture/area 준비와 SQLite save는 이 profile에서 millisecond 수준이었다.
- 한 schedule 요청 안에 정책 schedule solve 외에도 required-budget/capacity 진단 solver가 실행된다. 5백만원 조건에서 정책별 CP-SAT 호출은 3–6회였다. 이 중복 계산은 최적화 후보지만, 진단 출력 변경에 따른 결과 동등성 실험을 아직 마치지 않아 이번 PR에서 변경하지 않았다.
- `TIME_LIMIT` 상태인 두 정책에도 solver가 반환한 실제 feasible incumbent가 있다. 상태를 OPTIMAL로 바꾸거나 계산 결과를 생성하지 않았다.
- minimum-coverage analysis는 별도 요청이다. 로컬에서는 14회 CP-SAT 호출과 schedule 저장을 포함해 5.75초였고, 기존 원격 브라우저 기록에서는 같은 endpoint가 30.151초에 HTTP 500을 반환한 사례가 있다.
- 이전 Render journey에서 4개 schedule POST는 각각 17.692, 16.663, 27.414, 28.678초였다. 합계 약 90.4초이며 전체 compare 단계는 121.647초였다. 이 기록에서 minimum analysis는 실패했다.

## 전후 비교 및 제한

backend 최적화를 적용하지 않았으므로 성능 전후 비교는 `NOT_RUN`이다. 코드 수정은 UI 오류 경로와 부분 결과 보존만 다룬다. 로컬 시나리오 전체와 minimum analysis는 통과했지만 특정 Render 520은 `NOT_REPRODUCED`다. Render CPU 0.15 vCPU 제한에서의 동일 입력 profile, proxy upstream duration 및 520 상관관계는 Render 로그 확인 후에만 판정할 수 있다.

## 2026-10-26 계측 및 최소보장 중복 solve 제거

**테스트 코드:** `12494aa` · **기준 코드:** 기존 PR head `56cf8f4` · **배포:** `420a3b78b3e7f5b52100e6f20f2de14aa31a3a81`

합성 Hongseong Janggok 16-area fixture, 캐시된 합성 경로, 실제 FastAPI `TestClient` endpoint를 사용했다. `/api/schedules` 4개, 각 plans의 explanations GET 4개, 이후 minimum analysis를 순서대로 호출했다. `CpSolver.solve`를 계측해 endpoint별 CP-SAT 호출과 시간을 셌다. 같은 요청 조건에서 400만원과 500만원을 각각 한 번 실행했고, 가중치를 바꾼 balanced 일정도 1회 측정했다.

### 500만원 기본 정책

| 작업 | POST 시간 | CP-SAT 호출 / solver 시간 | 반환 상태 요약 |
|---|---:|---:|---|
| efficiency | 3.917초 | 3 / 3.831초 | FEASIBLE, 21 units, 4,900,803원, 미배정 14 |
| balanced | 5.319초 | 3 / 5.223초 | OPTIMAL, 18 units, 4,995,855원, 미배정 0 |
| minimum_coverage | 4.459초 | 6 / 4.361초 | FEASIBLE, 18 units, 4,777,794원, 미배정 0 |
| underserved_first | 7.628초 | 6 / 7.532초 | FEASIBLE, 18 units, 4,862,706원, 미배정 0 |
| minimum-coverage analysis | 0.054초 | 1 / 0.003초 | 201, 기존 minimum plan ID 재사용 |

4개 계획 생성 + explanations 조회 + 분석을 포함한 전체 API 흐름은 `21.394초`였다. 기존 동일 fixture 500만원 측정은 `27.634초`(네 일정 21.883초 + 별도 분석 5.751초)였으므로 이번 한 표본에서 `6.240초`, `22.6%` 짧았다.

최소보장 분석은 이전 `_scenario_data → evaluate_scenarios → _run_schedule_plan` 경로에서 전체 4정책 진단과 새 계획 저장을 수행했다. 이 경로는 14회 solve, 5.751초였다. 새 UI 요청은 이미 생성된 `minimum_coverage` plan을 소유권·예산·지역·정책까지 확인해 재사용하고, aggregate minimum estimate만 계산한다. 분석 경로는 1회 solve, 0.054초로 `5.697초 (99.1%)` 줄었으며, 전체 flow는 과거 32회에서 19회 CP-SAT 호출로 `13회 (40.6%)` 줄었다.

### 400만원 및 가중치 변경

- 400만원: efficiency `3.717초/3회`, balanced `5.242초/3회`, minimum coverage `5.449초/6회`, underserved first `5.123초/6회`, 분석 `0.055초/1회`; 전체 API 흐름 `19.604초`, 분석 응답 schedule ID는 기존 계획과 같았다.
- 500만원, balanced 가중치 `elderly=800`, `single_elderly=700`, `survey_required=900`: `5.350초`, 3회 solve, 201 응답.
- `FEASIBLE`과 `OPTIMAL`은 각각 solver 원래 상태로 유지했다. 최적화 코드는 정책 목적함수와 배정 solver를 변경하지 않는다. 기존 feasible 결과와 새 feasible 결과 JSON은 solver 실행 차이로 다를 수 있으므로 완전 일치 기준으로 비교하지 않았다.

### 통계·환경 제한

- 각 조건은 현재 1회 표본이므로 p50/p95를 신뢰 가능한 통계로 제시하지 않는다. 이전 profile도 단일 표본이다. 공급자 불참 후 재계획의 별도 지연시간 및 프로세스 CPU/RSS는 이번 계측에서 측정하지 않았다.
- 로컬 TestClient는 Render Free `0.15 vCPU` 환경, Next.js/Render proxy 전달, Cloudflare edge 동작을 재현하지 않는다. 따라서 Render Free 4정책 시간 개선은 `NOT_VERIFIABLE`이며, CPU·메모리 peak 초과 여부도 이번 실행으로 판정하지 않는다.
- 현재 측정 JSON: `artifacts/performance/scenario_optimization_before_after_20261026.json`.
