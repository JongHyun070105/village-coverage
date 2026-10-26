# VillageCoverage Product Quality Review — 2026-10-26

## Release v2.0 product acceptance — 2026-10-26

This current remote acceptance updates the earlier local/pre-deployment table below; those earlier results remain historical.

Latest recheck (2026-10-26 11:17 UTC): API is live at docs-only SHA `1fb24d14380bebb09260a7f0b69a9d33e20e6d71` (`dep-dbfjav5g1s2s73adt580`); Web remains at `27d5142de233011e35fff24ba8870d5de4205c23` (`dep-dbfgp1cs728c73dhbtm0`). API runtime code is unchanged from `5d51954a`. The full 4M/5M browser journeys and screenshots remain evidence from `27d5142`; request-correlation diagnostic remains evidence from `5d51954a`. After the docs-only redeploy, API health GET returned 200; the Web root GET timed out once at 20s and a bounded retry returned 200. The first timeout cause is unknown; no solver journey was repeated.

### 실행 확인

- 4,000,000원 public Render journey **16/16**: Dashboard 데이터/출처 고지, 홍성군 장곡면 선택, 정책 4장, 최소보장 분석, 계획 상세·재조회, 공급자 데모 불참, 재계획 v2, Decision Memo, CSV/PDF, 별도 세션 B의 계획/회차 접근 차단까지 통과했다.
- 5,000,000원 Scenario Compare **4/4**: 네 정책 카드와 최소보장 분석 endpoint가 실제 Render API 응답을 받아 표시됐다.
- A/B 세션 격리: B 세션이 A plan과 provider round를 읽지 못했고 예상 404를 받았다. 4M 여정 중 5xx는 없었다.
- Responsive read-only checks: 390×844, 768×1024, 1280×800, 1440×900에서 핵심 제목·지역·예산·버튼이 보이고 document/body overflow가 없었다. 이 검사는 viewport와 GET 중심이며 원격 키보드/스크린리더 전체 감사를 뜻하지 않는다.
- 배포 후 logger 진단: 브라우저 422 응답과 `X-Request-ID` echo가 일치하고 같은 ID의 Render API 완료 로그를 확인했다. ID·cookie·body 값은 산출물에 저장하지 않았다.

캡처 및 SHA-256 manifest: `artifacts/qa/render_public_demo_journey_20261026_v2_0/`. 주요 4M/5M 화면은 deploy SHA `27d5142`에서 촬영했다. API `5d51954` logger 코드는 UI/solver를 바꾸지 않았고, 후속 `1fb24d1` 배포도 docs-only다. Logger 검증은 `5d51954`에서 비계산 422 요청 한 건으로 수행했다.

### 공개 데모 품질 판단

표시되는 데이터는 합성 운영값과 공개 지역자료가 섞인 시제품이다. 실제 필요·공급자 가용성·가격·현장 성과를 검증한 자료로 소개하지 않는다. CP-SAT은 명시된 계획 제약을 계산하고, Gemini 실호출은 검증되지 않았다. Decision Memo는 담당자 검토 초안이며 법적 승인/결재가 아니다.

정책 계산 중 Render Free API CPU가 분 평균 `0.14835 / 0.15 vCPU`까지 올라가 동시 요청 여유가 좁다. 계산은 네 정책 순차 실행으로 성공했다. 모바일 캡처에서 fixed bottom navigation이 full-page 이미지 하단에 겹쳐 보일 수 있으나 본문 하단 padding은 58px이며 viewport overflow는 관찰되지 않았다. 실제 저사양 단말의 키보드/스크린리더 시험은 추가 검수가 필요하다.

### Gate update

| 영역 | 2026-10-26 상태 | 근거/제한 |
|---|---|---|
| Scenario Compare / 4M | `EXEC PASS` | 네 schedule, analysis, 화면 카드 모두 성공 |
| Scenario Compare / 5M | `EXEC PASS` | 네 실제 정책 결과; 최소비용 값은 `NOT_PROVEN` |
| plans/replan/memo/export | `EXEC PASS` | public browser 16/16 journey |
| A/B isolation | `EXEC PASS` | A 자료의 B 접근 404 |
| Responsive | `EXEC PASS` | 4 viewport, overflow 없음; 전체 접근성 audit는 아님 |
| Request correlation | `EXEC PASS` | 실제 Uvicorn stderr regression + 배포 후 브라우저/API log match |
| High-load capacity | `NOT_VERIFIABLE` | API Free CPU가 98.9% 분 평균까지 관측, 동시 부하시험은 하지 않음 |
| Root cause of historical 520 | `NOT_VERIFIABLE` | 새 계측은 검증됐지만 예전 request ID가 없어 원 요청 연결 불가 |
| Real Gemini / field use | `NOT_VERIFIABLE` | 모델 호출과 현장 실증 미검증 |


## Scope

The sections below preserve the earlier local/pre-deployment review and implementation record; the release v2.0 acceptance above is the current remote state.

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
