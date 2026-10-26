# VillageCoverage Product Quality Review — 2026-10-26

## Scope

이번 변경은 Scenario Compare의 4정책 실행, 최소보장 분석, 장시간 POST 복구를 대상으로 했다. 정책 목적함수, 공급 제약, 공개 데모 세션 정책, 다른 화면의 정보 구조는 변경하지 않았다.

## 사용자 흐름 변경

- 각 정책의 schedule POST가 끝나면 결과 카드를 즉시 보존한다. 권역별 explanations GET 실패는 그 카드에만 안내하고 다음 정책 계산을 계속한다.
- `POST /api/minimum-coverage/analysis`에 기존 `minimum_coverage` schedule ID, 지역, 예산, 정책을 보낸다. API는 브라우저 세션 소유권과 요청 조건을 확인하고 그 계획을 재사용한다. ID가 없던 기존 API 호출은 기존 생성 경로를 유지한다.
- 분석이 실패해도 만들어진 4개 카드와 상세 링크를 보존하고 비교 전체를 다시 실행해 중복 계획을 만들지 않도록 막는다.
- schedule POST의 5xx, timeout, 연결 오류, 성공 상태의 응답 형식 오류처럼 저장 여부가 모호한 결과에서는 재실행을 차단하고 계획 목록 확인을 안내한다. 확정적인 4xx는 원래 오류 코드를 유지한다.
- POST는 자동 재시도하지 않는다. 401/403/404/409/422/429/503 등의 응답 상태를 200으로 바꾸지 않는다.

## 정확성 및 보안

- 재사용되는 계획은 현재 세션 소유권, `minimum_coverage` policy key, 예산, 지역, 정규화된 정책이 모두 맞아야 한다. 소유하지 않거나 조건이 다르면 분석을 시작하지 않고 404/409를 반환한다.
- 최소보장 분석 경로는 필요한 aggregate estimate만 계산한다. 정상 합성 fixture에서 전체 4정책 결과와 필요 예산이 일치하고 estimate 경로의 CP-SAT solve는 1회였다.
- 공개 데모 rate limit와 Solver Capacity Gate는 유지했다. 캐시를 도입하지 않아 방문자 간 결과 공유나 cache invalidation 경로는 추가되지 않았다.
- `X-Request-ID`는 UUID만 수용하며 로그에 query, cookie, body, 개인 데이터를 남기지 않는다. 상관관계 ID는 인증/소유권 토큰으로 사용하지 않는다.
- 공개 데모는 합성 시연이다. 실제 지자체 운영이나 실증 수준의 검증을 뜻하지 않는다.

## 검증

| 검사 | 결과 |
|---|---|
| Backend | `EXEC PASS` — 596 passed, 1 기존 skipped |
| Ruff / compileall | `EXEC PASS` |
| R1–R13 mapped acceptance | `EXEC PASS` — 112 passed |
| Frontend lint / typecheck / build | `EXEC PASS` |
| npm ci / production npm audit | `EXEC PASS` — 0 vulnerabilities |
| Python production dependency audit | `EXEC PASS` — no known vulnerabilities |
| Standard frontend E2E | `EXEC PASS` — 14 passed, 1 기존 remote-only skipped |
| Public Demo E2E | `EXEC PASS` — 6 passed |
| Responsive production UI | `EXEC PASS` — 5 passed, 390×844 / 768×1024 / 1280×800 / 1440×900 |
| Ambiguous 504 write / explanation GET recovery | `EXEC PASS` |
| Request ID Next.js rewrite echo | `EXEC PASS` |
| Remote Render product run | `NOT_VERIFIABLE` — 이번 변경을 배포하지 않음 |

테스트 실행 시 TestClient DB, route cache, Playwright output, Python/npm cache, Python 환경은 작업별 private 임시 경로에 두었다. 본 checkout의 기존 수정 파일은 건드리지 않았다.

## 남은 제품 위험

- HTTP 520의 최초 upstream 실패 지점은 아직 확인되지 않았다. ASGI response send 기록은 proxy 전달 또는 브라우저 수신을 증명하지 않는다.
- 한 조건에 한 번 측정했으므로 p50/p95 신뢰도는 확보하지 못했다. Render Free의 0.15 vCPU에서 신규 버전 계산시간을 다시 측정하지 않았다.
- POST 결과가 모호할 때 안전을 우선해 페이지 비교 재실행을 차단한다. 사용자가 저장된 계획을 직접 확인해야 하며, 서버측 idempotency key를 도입한 것은 아니다.
- Provider decline / replan의 성능시간과 원격 세션 격리는 이번 신규 코드의 별도 원격 profile이 아니다.
