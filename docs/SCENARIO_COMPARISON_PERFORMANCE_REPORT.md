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
