# Scenario Comparison HTTP 520 Root Cause

## Release v2.0 evidence update — 2026-10-26 11:17 UTC

Earlier dated sections below are preserved as historical records; this section gives the latest Render and correlation evidence.

**현재 판정:** 과거 HTTP 520의 최초 실패 경계는 여전히 `UNKNOWN`이다. 요청 상관관계 로그가 운영에서 빠진 원인은 확인하고 수정했다.

- latest main/deploy-branch SHA: `1fb24d14380bebb09260a7f0b69a9d33e20e6d71`; exact-main CI `40311552879` passed. PR #7 was a docs-only release evidence update.
- API live: `dep-dbfjav5g1s2s73adt580`, SHA `1fb24d14380bebb09260a7f0b69a9d33e20e6d71`. This deployment adds documentation; runtime code remains the code tested at `5d51954a`.
- Web live: `dep-dbfgp1cs728c73dhbtm0`, SHA `27d5142de233011e35fff24ba8870d5de4205c23`. Web code는 이번 로그 수정에서 바뀌지 않았다.
- Render MCP 인증 및 workspace `My Workspace` / `tea-db3ogj49v7es73dspep0`를 확인했다. 두 서비스는 Free, `submission/public-demo-deploy`, Auto Deploy 활성 상태다.
- API auto build/deploy는 `11:12:26.847314Z` / `11:13:10.217486Z`에 성공했다. API `/health` GET은 200이었다. Web root GET은 한 번 20초 후 응답 없이 timeout됐고, 제한된 재요청은 200이었다. 첫 timeout의 원인은 `UNKNOWN`이다. 이 docs-only 배포 뒤에는 solver POST를 실행하지 않았다.

### 로그 누락의 원인과 검증

Uvicorn 기본 로깅 설정은 console handler를 `uvicorn` logger 아래에 둔다. root logger에는 handler가 없다. `backend.request`에 INFO를 설정하는 것만으로는 로그가 Uvicorn console handler에 도달하지 않았다. 새 코드는 전용 logger를 `uvicorn.error.backend.request` 아래에 두고 INFO 수준을 명시한다. 회귀 테스트는 실제 Uvicorn logging config를 먼저 구성하고 ASGI `POST /api/schedules`를 보내 stderr에 완료 이벤트가 남는지 확인한다.

배포 SHA `5d51954a`에서 브라우저가 `/api/health`를 연 뒤 빈 schedule body를 한 번 보냈다. 응답은 예상된 HTTP 422였고 `X-Request-ID`가 브라우저 요청과 일치했다. 같은 ID로 Render API 앱 로그에서 `api_asgi_response_complete`, `path=/api/schedules`, `status_code=422`, `duration_ms`를 확인했다. request ID 값은 이 문서에 저장하지 않았다. 이 요청은 CP-SAT이나 Schedule 생성까지 진행하지 않았다. 후속 `1fb24d1` 배포는 docs-only라 이 검증된 runtime logging 코드는 바뀌지 않았지만, 422 diagnostic 자체는 `5d51954a`에서 실행됐다.

이 확인은 새 계측이 프록시를 지나 API 로그까지 상관관계를 제공함을 검증한다. 과거 520 trace에는 request ID가 없으므로 당시의 201 로그와 연결할 수 없다. 완료 이벤트는 FastAPI/ASGI 서버가 response body send를 마친 시점이며 Cloudflare 전달 성공을 뜻하지 않는다. 따라서 `ROOT_CAUSE_CONFIRMED`는 계속 `NOT_VERIFIABLE`이다.

### 원격 흐름과 지표 요약

- 4,000,000원 public browser journey: 16/16 단계 통과. 네 정책 POST는 각각 201, 이후 최소보장 분석·계획 상세·공급자 불참·재계획·Decision Memo·CSV/PDF·세션 B 격리가 통과했다.
- 5,000,000원 Scenario Compare: 4/4 정책 POST와 최소보장 분석 endpoint가 201로 완료됐다. 계산된 최소비용 값은 `NOT_PROVEN`으로 남아 있다.
- 정책 계산 중 API CPU 분 평균 peak `0.14835 / 0.15 vCPU`(약 98.9%), API memory peak 약 `201.9 / 512 MiB`였다. 분 단위 계측이며 짧은 순간 spike는 배제하지 못한다.
- 새 logger 배포 후 단일 422 진단 시 API CPU 표본은 `0.0607`, 이후 `0.0015–0.0019 / 0.15 vCPU`; `10:27:30–10:31:30 UTC`의 memory 분 표본은 `88.6–110.2 / 512 MiB`였다. 브라우저 경과시간은 201ms, API 완료 로그의 `duration_ms`는 9.2ms다. 이 값은 solver 부하 profile이 아니다.
- Render request metrics는 해당 시간대에 값이 없었다. 520 당시의 API 201은 계속 `UNKNOWN` 상관관계로 보존한다.
- 현재 docs-only API 배포 직후 idle 관측(11:11–11:17 UTC)에서 API CPU 분 표본은 최대 `0.0262 / 0.15 vCPU`, 메모리는 최대 약 `120.7 / 512 MiB`; Web CPU는 최대 `0.0011 / 0.15 vCPU`, 메모리는 최대 약 `102.8 / 512 MiB`였다. HTTP request/latency metrics 및 API request logs는 반환되지 않았다. 이 idle 구간은 solver 부하 profile이 아니다.
- 4M/5M 실행 구간 `08:20–08:26:59 UTC`의 API 앱 로그는 160건이었다: HTTP 200 145건, 201 11건, 404 2건, 상태코드를 파싱하지 못한 로그 2건. 이 로그 조회에서 5xx나 error-level 로그는 없었다. API CPU 분 평균은 `0.0017–0.1484 / 0.15 vCPU`, memory는 `110.3–201.9 / 512 MiB`; Web CPU는 최대 `0.0212 / 0.15 vCPU`, memory는 최대 `79.2 / 512 MiB`였다. 이는 두 acceptance 실행을 포함한 앱 로그·분 단위 표본이며 요청별 상관 증거는 아니다.
- Render 이벤트 이력 조회에서 과거 520 시간대 `22:18–22:26 UTC`에는 API와 Web 모두 `server_failed`, `server_restarted`, `server_hardware_failure`, `deploy_ended`, `build_ended` 일치 항목이 반환되지 않았다. 현재 API docs-only 배포는 build와 deploy가 각각 `11:12:26.847314Z`, `11:13:10.217486Z`에 성공했고 조회 구간에 실패·재시작 이벤트는 반환되지 않았다. Web에는 새 배포 이벤트가 없었다. 이벤트가 반환되지 않았다는 사실은 짧은 순간의 장애가 없었다는 증거가 아니다.

새 원격 화면 캡처와 해시 manifest는 `artifacts/qa/render_public_demo_journey_20261026_v2_0/`에 있다. 핵심 4M/5M 캡처는 Web/API SHA `27d5142`에서 촬영했고, 이후 API-only logger 수정은 UI/solver 동작을 바꾸지 않았다.


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


## 2026-10-26 최신 Render 로그·지표 재확인 (07:51 UTC)

Workspace `My Workspace` / `tea-db3ogj49v7es73dspep0`를 다시 목록에서 확인한 뒤, API와 Web 서비스 및 2026-10-25 22:18–22:26 UTC 자료를 Render MCP로 읽었다. Render CLI는 설치되지 않았으며, Render MCP 인증은 유효하다. Web ID는 서비스 목록에서 `srv-db3oh84s728c73fl4vl0`로 확인했다. 작업 지시의 ID `srv-db3oh84s728c73fl0`는 목록에 없었다.

- trace 원본에서 브라우저는 Web same-origin `POST /api/schedules`를 `22:19:14.404Z`에 시작했고, `40,951 ms` 뒤 `520`, `text/html; charset=UTF-8`, `server: cloudflare`를 받았다. 요청 헤더에 `X-Request-ID`는 없었다.
- API 앱 로그에는 `22:19:31.693Z POST /api/schedules 201 Created`가 있다. 이는 브라우저 요청 시작 17.289초 뒤이며 520 응답 전이다. 시간상 같은 요청일 가능성을 배제할 수 없지만, request ID/schedule ID/Ray ID가 API 로그에 없으므로 관계는 계속 `UNKNOWN`이다.
- Web 앱의 `ECONNRESET`/`socket hang up`은 `22:17:33.309Z`의 `/api/minimum-coverage/analysis` 요청으로, 실패한 schedule POST 시작 101초 전이다. 이 두 사건을 같은 요청 또는 직접 원인으로 연결하지 않는다.
- 두 서비스의 Render `request` 로그 조회는 해당 구간에서 기록을 반환하지 않았다. HTTP request-count/latency metric도 데이터가 없었다. 확인 가능한 자료는 앱 로그와 분당 resource metric이다.
- API CPU limit은 0.15 vCPU였다. 22:19 분 평균 0.056 vCPU, 22:20 분 평균 0.073 vCPU였으며 요청 구간 22:18–22:26의 최대 표본 0.133 vCPU(88.4%)는 22:18 분에 관측됐다. API memory는 약 277–288 MiB / 512 MiB였다.
- Web CPU는 약 0.001–0.038 / 0.15 vCPU, memory는 약 123–131 MiB / 512 MiB였다. 동일 instance label이 지표 표본에 유지됐지만, 분 단위 표본은 짧은 CPU spike나 재시작을 배제하기에 충분하지 않다.

관측된 분 평균은 schedule 요청 구간에 지속적인 CPU 포화가 있었다는 증거를 제공하지 않는다. 하지만 순간 peak와 solver별 CPU 구간을 보이지 않고, API 201과 브라우저 520의 상관관계도 입증하지 못한다. 따라서 최초 실패 경계와 원인은 `UNKNOWN`이며 `ROOT_CAUSE_CONFIRMED`는 충족되지 않았다. 신규 correlation middleware는 후속 배포에서만 관측 가능하다.
