# Scenario Comparison Performance Report

## Remote Render Free acceptance — 2026-10-26

Earlier pre-deployment profiles below remain unchanged and are historical; this section adds the deployed 4M/5M browser measurements.

Current deployment recheck at 2026-10-26 11:17 UTC: API is live at docs-only SHA `1fb24d14380bebb09260a7f0b69a9d33e20e6d71` (`dep-dbfjav5g1s2s73adt580`); Web remains at `27d5142de233011e35fff24ba8870d5de4205c23` (`dep-dbfgp1cs728c73dhbtm0`). Runtime code is unchanged from API `5d51954a`. The 4M/5M solver timings below were measured before this docs-only deploy; no solver POST was repeated afterward. Post-deploy idle samples and bounded GET smoke are recorded in `docs/FINAL_REMOTE_SCENARIO_ACCEPTANCE.md`.

측정은 홍성군 장곡면의 public/synthetic demo fixture로 순차 실행했다. 한 번씩의 브라우저 실행이며 p50/p95를 추정하지 않는다.

| 예산 | 정책 | POST 상태 | POST 경과 | 결과 |
|---:|---|---:|---:|---|
| 4,000,000원 | efficiency | 201 | 17.615초 | 4M 전체 사용자 journey의 첫 정책 |
| 4,000,000원 | balanced | 201 | 16.578초 | 순차 실행 |
| 4,000,000원 | minimum_coverage | 201 | 27.771초 | 순차 실행 |
| 4,000,000원 | underserved_first | 201 | 28.879초 | 네 정책 화면 단계 92.787초 |
| 5,000,000원 | efficiency | 201 | 17.869초 | FEASIBLE, 21/162 units, 3/16 권역, 미충족 13, 조사 필요 1/8, ₩4,977,171, 이동 10분 |
| 5,000,000원 | balanced | 201 | 15.363초 | FEASIBLE, 18/162 units, 16/16 권역, 미충족 0, 조사 필요 8/8, ₩4,894,282, 이동 137분 |
| 5,000,000원 | minimum_coverage | 201 | 24.211초 | FEASIBLE, 18/162 units, 16/16 권역, 미충족 0, 조사 필요 8/8, ₩4,851,716, 이동 115분 |
| 5,000,000원 | underserved_first | 201 | 27.241초 | FEASIBLE, 18/162 units, 16/16 권역, 미충족 0, 조사 필요 8/8, ₩4,890,306, 이동 122분 |

4M Scenario Compare 화면 단계 합계는 92.787초였다. 5M 화면 단계는 87.716초였다. 추가 최소보장 분석 POST는 4M에서 0.678초, 5M에서 0.627초였고 두 응답 모두 HTTP 201 및 기존 최소보장 계획 재사용을 확인했다. 5M 응답의 이론적·일정기반 최소비용 값은 `null / NOT_PROVEN`; 추가 예산액도 `null`이다. 이 endpoint 성공을 확정 최소비용 증명으로 표현하지 않는다.

### 로컬 CP-SAT profile과 해석

동일 합성 fixture의 한 표본에서 5M 전체 API 흐름은 `27.634초 → 21.394초`(약 22.6% 단축)였다. minimum analysis는 `5.751초 / 14 solves → 0.054초 / 1 solve`였고 전체 solve 수는 `32 → 19`였다. 정책 목적함수와 core solver는 변경하지 않았고 FEASIBLE/OPTIMAL/TIME_LIMIT 원래 상태를 유지했다. 표본이 각 1건이므로 통계적 p50/p95로 일반화하지 않는다.

Render Free remote compare 시간은 정책당 약 15.4–28.9초로 여전히 길다. 4M/5M 시연 중 API CPU 분 평균 peak는 `0.14835 / 0.15 vCPU`(약 98.9%), memory peak는 `201.9 / 512 MiB`였다. Web peak는 `0.02116 / 0.15 vCPU`, memory 약 `79.2 / 512 MiB`였다. request count/latency metrics는 비어 있었고 CPU는 분 단위 표본이다. 순차 4정책 흐름은 실제로 완료됐지만, 동시 부하 여유가 충분하다고 말할 수는 없다.

API-only logger 배포 뒤 빈 입력 422 진단은 201ms에 끝났다. 해당 시각 API CPU 표본은 최대 `0.0607 / 0.15 vCPU`, memory 최대 약 `110.2 / 512 MiB`였다. 이 작은 요청은 solver 성능 측정으로 쓰지 않는다.

원시 수치: `artifacts/performance/scenario_optimization_before_after_20261026.json`, `artifacts/qa/remote_scenario_acceptance_20261026.json`. Browser 캡처는 `artifacts/qa/render_public_demo_journey_20261026_v2_0/`에 보존했다.


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


## Render Free resource observation for the historical failure window

Render MCP historical metrics for 2026-10-25 22:18–22:26 UTC returned nine one-minute samples per resource. API CPU limit was 0.15 vCPU; samples were 0.0013–0.1325 vCPU. At the browser POST start minute the API average was 0.0560 vCPU, and the following minute was 0.0727 vCPU. The maximum sample (0.1325, 88.4% of limit) was at 22:18, before the browser POST began. API memory was 277–288 MiB of 512 MiB. Web CPU was 0.0005–0.0379 vCPU of 0.15, and memory was 123–131 MiB of 512 MiB.

These are minute-level resource samples, not request-level CPU profiles. Render request logs and HTTP request-count/latency metrics returned no data for this interval. They cannot establish solver CPU time, proxy upstream duration, status distribution, or exclude short spikes. The current code was not deployed during this historical window, so these metrics do not verify the optimization on Render Free.
