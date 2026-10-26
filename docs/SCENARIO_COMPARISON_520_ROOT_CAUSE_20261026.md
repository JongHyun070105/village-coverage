# Scenario Comparison HTTP 520 Root Cause

**조사 시각:** 2026-10-26 14:37 KST
**상태:** `PARTIAL` — browser-facing 520은 확인했으나 서버 측 root cause는 `UNKNOWN`
**기준 배포 SHA:** `420a3b78b3e7f5b52100e6f20f2de14aa31a3a81`
**수정·검증 코드 SHA:** `ad2a4d1eba8932e810f9acb94da7817caf9a9fce`

## 확인된 실패

저장된 Playwright trace의 테스트 `scenario comparison renders four computed policy results in production`에서 첫 시나리오 요청만 실패했다.

- 브라우저 요청: `POST /api/schedules`
- 시작: `2026-10-25T22:19:14.404Z`
- 경과: `40,951 ms`
- 응답: `520`, `text/html; charset=UTF-8`
- 응답 헤더: `server: cloudflare`, `cf-ray: a5049a0728a8264d-NRT`, `retry-after: 60`
- 요청 입력: `pilot:홍성군 장곡면`, 예산 `4,000,000원`, `efficiency`
- 같은 브라우저 trace에서 schedule POST는 이 요청 1회뿐이었다. 이후 정책 POST, explanations GET, minimum-coverage POST는 시작하지 않았다.
- 기대 결과는 4개 카드였으나 브라우저에는 0개가 표시됐다. Playwright는 카드 4개를 최대 210초 기다려 실제 API 오류보다 늦게 테스트를 실패시켰다.

저장 trace: `/tmp/villagecoverage-ui-regression-run-20261026/ui-regression-scenario-com-4bc1c-olicy-results-in-production/trace.zip`.

## API 로그와의 상관관계

Render FastAPI 로그에 `POST /api/schedules` `201 Created`가 **2026-10-25 22:19:31 UTC**에 기록돼 있다. 이 시각은 브라우저 요청 시간 창 안에 들어오지만, 로그에서 같은 request ID, schedule ID, Cloudflare Ray ID를 확인하지 못했다. 따라서 이 201이 실패 trace의 요청과 같은 요청인지 `UNKNOWN`으로 둔다.

Next.js의 `/api/minimum-coverage/analysis` `ECONNRESET`/`socket hang up` 로그는 `22:17:33 UTC`로 더 이르며, path도 다르다. 해당 오류를 실패한 schedule POST의 직접 원인으로 연결하지 않는다.

## 원인 가설 판정

| 가설 | 현재 근거 | 판정 |
|---|---|---|
| CP-SAT 계산이 Free에서 30초 이상 소요 | 기존 원격 성공 flow에서 schedule POST가 17.7–28.7초, 별도 minimum analysis가 30.151초였다. 로컬 500만원 POST는 3.95–7.44초였다. Render 제한 환경에서 더 느릴 수 있다. | `POSSIBLE`, 특정 실패 요청은 미확인 |
| Next.js rewrite 제한시간 | 사용 중인 Next 16.4.3 proxy 구현의 기본 timeout은 30초이며 프로젝트는 별도 `experimental.proxyTimeout`을 설정하지 않는다. trace 응답은 40.95초 뒤였다. | `POSSIBLE`, 해당 연결의 timeout 발생 증거 없음 |
| Cloudflare edge가 520 응답 생성 | 브라우저가 받은 응답은 Cloudflare 헤더와 HTML 오류 응답이었다. | edge 응답 확인, 최초 upstream 실패 지점은 `UNKNOWN` |
| FastAPI가 요청 처리 후 응답 전달 실패 | 시간 창에 201 로그가 존재하나 같은 요청이라는 공통 식별자가 없다. | `NOT_VERIFIABLE` |
| 세션/요금제 제한, UI 렌더 오류 | 저장 trace의 status는 HTML 520이며 요청은 첫 POST에서 끝났다. 제한·React 예외 근거는 trace에서 확인되지 않았다. | `NOT_VERIFIABLE`; 직접 증거 없음 |
| 입력 조건 불일치 | trace의 예산은 사용자가 요구한 5,000,000원이 아니라 4,000,000원이었다. | 확인됨. 원격 실패 원인은 아님 |

Render 지표의 이전 관측값은 CPU peak 약 `0.133/0.15 vCPU`, memory 약 `302/512 MiB`, 강제 종료 이벤트 없음이다. 이는 resource pressure의 가능성만 보여주며 원인을 증명하지 않는다.

## 조치와 남은 확인

코드 수정은 520 이후 중복 계획 생성을 막고, 이미 응답받은 계획 및 부분 결과를 보존하며, 실패 단계와 계획 수를 표시한다. 테스트에서 520 응답을 주입해 이 복구 동작을 확인했다. CP-SAT 목적함수, proxy timeout, backend API 계약은 변경하지 않았다.

현재 Render workspace를 고르는 사용자 확인이 없어 Render MCP 로그/metrics를 재조회하지 않았고, 공개 데모에 새 요청을 보내지 않았다. 그러므로 `ROOT_CAUSE_CONFIRMED`, `DEPLOYED_VERIFIED`, `REMOTE_SCENARIO_4_OF_4_PASS`는 충족되지 않았다. 이 commit은 원격 성능 복구를 입증한 배포가 아니다.

## 2026-10-26 재확인 및 상관관계 계측

**확인 시각:** 2026-10-26 07:14 UTC · **코드:** `12494aaa947e14263980c35aa4ce2e0879f8aa98` · **배포:** 기존 Live SHA 유지

- Render CLI는 설치되지 않아 `render whoami`/`render login`을 실행할 수 없었다. Render MCP에서 workspace 목록을 조회했고, `My Workspace` ID `tea-db3ogj49v7es73dspep0`가 확인됐다.
- API `srv-db3oh84s728c73fl4vlg`와 Web `srv-db3oh84s728c73fl0`는 모두 Free, `submission/public-demo-deploy` 브랜치, auto deploy 활성 상태다. 양쪽 Live SHA는 `420a3b78b3e7f5b52100e6f20f2de14aa31a3a81`로 기존 배포와 같고, 새 배포·재시작은 실행하지 않았다.
- 문제 시간대 API 로그에 `2026-10-25T22:19:31.693143213Z POST /api/schedules 201 Created`가 있었다. 브라우저 POST 시작은 `22:19:14.404Z`, Cloudflare 520 수신은 약 `22:19:55Z`다. 로그의 201은 요청 ID가 없던 기록이므로 브라우저 요청과의 관계는 계속 `UNKNOWN`이다.
- 당시 API CPU는 분당 표본 기준 약 `0.056–0.133 / 0.15 vCPU`, 메모리는 `291–302 / 537 MB`였다. Web CPU는 약 `0.009–0.038 / 0.15 vCPU`, 메모리는 `129–138 / 537 MB`였다. 요청별 지연/상태 지표는 비어 있었고, 분당 표본으로 순간 peak나 전송 문제를 배제할 수 없다.
- 로컬 Next.js 16.4.3 proxy 구현은 별도 설정이 없을 때 30초 timeout을 사용한다. 40.951초 trace와 맞닿은 가설이지만, 그 timeout이 이 요청에서 발동했다는 로그는 없어 root cause로 확정하지 않는다.

이 버전은 `/api/schedules`와 `/api/minimum-coverage/analysis` POST에 UUID `X-Request-ID`를 보낸다. FastAPI는 올바른 UUID를 검증해 기록하고 응답에 돌려준다. 로그에는 ID, method, path, status, duration만 남기며 query, cookie, request body는 남기지 않는다. 브라우저 production E2E에서 ID가 Next.js rewrite를 지나 응답 헤더로 돌아오는 것을 확인했다.

계측 이벤트 `api_asgi_response_complete`는 ASGI 서버의 response body send 완료를 뜻한다. 이는 Cloudflare/Render proxy 전달이나 브라우저 수신 완료의 증거가 아니다. send 오류는 별도 `api_asgi_send_error` 이벤트로 기록한다. 따라서 ID가 새 로그와 브라우저 trace 양쪽에서 확인되더라도 최초 실패 지점 분석에는 Web/edge 로그가 필요하다. `ROOT_CAUSE_CONFIRMED`는 여전히 `NOT_VERIFIABLE`이다.
