# VillageCoverage v27.1 — PR 통합 마무리·Keep-Alive 운영 전환·최종 릴리스 게이트 Handoff (`V27_1_INTEGRATION_HANDOFF.md`)

- **작성 시각**: `2026-11-09 16:53 KST` (`2026-11-09T07:53:00Z`)
- **기준 저장소**: `https://github.com/JongHyun070105/village-coverage`
- **본 문서의 역할**: 기존 `V25_PRODUCTION_READINESS_AND_FULL_QA_REPORT.md`, `V26_FINAL_RELEASE_GATE_REPORT.md`, `V27_INTEGRATION_HANDOFF.md`를 재작성하지 않고, **v27 이후 발생한 델타(PR #21 병합 완료, 새 `main` CI, PR #22 base=`main` 전환 및 최신 CI, PR #24 CI 완료, 새 통합 RC `6e90a67`, GitHub `schedule` 실측, Cloudflare Workers Logs 관측성 보강, SQLite 정책 A/B 코드 대조)** 만 감사 가능하게 기록한다.

---

## 1. PR #21 병합 완료 확인 (`EXEC PASS`)

| 항목 | 실측값 |
|---|---|
| PR 번호 / 링크 | [PR #21 (`fix/v24-keepalive-schedule-delay-20261103`)](https://github.com/JongHyun070105/village-coverage/pull/21) |
| 상태 (`state`) | `MERGED` |
| 병합 시각 (`mergedAt`) | `2026-11-09T06:56:10Z` (`2026-11-09 15:56:10 KST`) |
| PR HEAD SHA (`headRefOid`) | `819fcce9807002423a937fc6abf8123e23fd689d` |
| 병합 커밋 SHA (`mergeCommit` / `origin/main` HEAD) | `90bd6c87df0278d72228b154ee45ca7b6de45a2f` (`90bd6c87df0278d72228b154ee45ca7b6de45a2f^{tree}` = `3f14959c0396aa395ef03d61e2602927462d476c`) |
| 병합 부모 커밋 | `db4810946b47a2433463eb988ea2eefa3079c6fd` (`main` 이전 HEAD) + `819fcce9807002423a937fc6abf8123e23fd689d` (PR #21 HEAD) |
| 만료 승인 ID 재실행 여부 | `a86ad333f79c476f`, `c4fb0747341c4607`, `d771e9553b5e441b` 모두 `EXPIRED` 확인 및 재실행 없음 |

---

## 2. 새 `main` (`90bd6c8`) CI `42576124307` 최종 결론 (`EXEC PASS`)

| 항목 | 실측값 |
|---|---|
| 워크플로 실행 ID / 링크 | [`42576124307`](https://github.com/JongHyun070105/village-coverage/actions/runs/42576124307) (`CI`, `event: push`, `branch: main`) |
| 대상 커밋 (`headSha`) | `90bd6c87df0278d72228b154ee45ca7b6de45a2f` |
| 최종 상태 / 결론 | `status: completed` / **`conclusion: success`** (`2026-11-09T06:56:12Z` ~ `2026-11-09T07:09:46Z`) |
| `backend` 잡 (`129024123758`) | **`success`** (`06:56:14Z` ~ `07:05:25Z`, 9m 11s) — `uv sync --locked --dev`, `pip-audit`, `ruff check`, `compileall`, `pytest -q`, `proposal_acceptance_check.py` (R1–R13) 전부 통과 |
| `frontend` 잡 (`129024124034`) | **`success`** (`06:56:15Z` ~ `07:09:45Z`, 13m 30s) — `npm ci`, `npm audit --omit=dev --audit-level=high`, `lint`, `test:unit`, `typecheck`, `build`, `test:e2e`, `test:e2e:public-demo`, `ui_responsive_check.py` 전부 통과 |
| 실패/스킵된 잡 | 없음 (`0 failed`, `0 skipped`) |

---

## 3. PR #22 Base `main` 정리 및 최신 CI 상태 (`EXEC PASS`)

| 항목 | 실측값 |
|---|---|
| PR 번호 / 링크 | [PR #22 (`fix/v24.2-coldstart-retry-20261104`)](https://github.com/JongHyun070105/village-coverage/pull/22) |
| HEAD SHA (`headRefOid`) | `7979253eac579db9e084fd6d6222b099adb12396` |
| Base 브랜치 변경 | `fix/v24-keepalive-schedule-delay-20261103` → **`main`** (`gh pr edit 22 --base main` 실행 완료) |
| `git merge-base origin/main 7979253` | `819fcce9807002423a937fc6abf8123e23fd689d` (PR #21 HEAD — 중복 커밋 0개) |
| `origin/main..7979253` 고유 커밋 (4개) | `a45ee56`, `cc7693a`, `430ff22`, `7979253` |
| 변경 파일 / 라인 수 (`origin/main...7979253`) | **8 files changed, `+1171` / `-60`** (`.github/scripts/render_keepalive.py`, `V24.2_KEEPALIVE_COLD_START_REPORT.md`, `docs/RENDER_FREE_KEEPALIVE.md`, `poc/cloudflare-workers-keepalive/README.md`, `poc/cloudflare-workers-keepalive/src/index.mjs`, `poc/cloudflare-workers-keepalive/test/worker.test.mjs`, `poc/cloudflare-workers-keepalive/wrangler.toml`, `tests/test_render_keepalive.py`) |
| GitHub 병합 가능 상태 | `state: OPEN`, `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN` |
| 최신 CI 실행 (`7979253`) | [`42580300058`](https://github.com/JongHyun070105/village-coverage/actions/runs/42580300058) (`CI`, `headSha: 7979253eac579db9e084fd6d6222b099adb12396`, `status: completed`, **`conclusion: success`**, `07:35:29Z` ~ `07:48:21Z`) — `backend` (`129037157299`: `success`), `frontend` (`129037157714`: `success`) |
| 기존 `pull_request` CI 실행 (`7979253`) | [`42565558639`](https://github.com/JongHyun070105/village-coverage/actions/runs/42565558639) (`status: completed`, **`conclusion: success`**) |

---

## 4. PR #23 Stacked 구조 점검 (`EXEC PASS`)

| 항목 | 실측값 |
|---|---|
| PR 번호 / 링크 | [PR #23 (`docs/v25-production-readiness-report-20261108`)](https://github.com/JongHyun070105/village-coverage/pull/23) |
| HEAD SHA (`headRefOid`) | `15b87a80d3fb8890b2ccb21008fcdda49f9ee217` |
| 현재 Base 브랜치 | `fix/v24.2-coldstart-retry-20261104` (PR #22 병합 전이므로 stacked base 유지 — 조기 변경 시 PR #22의 8파일 diff가 섞이므로 변경하지 않음) |
| `git merge-base 7979253 15b87a8` | `7979253eac579db9e084fd6d6222b099adb12396` (PR #22 HEAD) |
| PR #23 고유 커밋 (2개) / 변경 파일 (2개) | `55aa4cb`, `15b87a8` / `tests/test_render_keepalive.py` (`+141`), `V25_PRODUCTION_READINESS_AND_FULL_QA_REPORT.md` (`+171`) — 총 **`+312 / -0`** |
| GitHub 병합 가능 상태 / CI | `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN` / CI [`42569948191`](https://github.com/JongHyun070105/village-coverage/actions/runs/42569948191) **`conclusion: success`** (`backend` `129004966432`: `success`, `frontend` `129004966418`: `success`) |
| PR #22 병합 직후 절차 | PR #22가 `main`에 병합된 뒤 `gh pr edit 23 --base main` 실행 → diff가 2개 파일(`+312/-0`)인지 확인 후 병합 |

---

## 5. PR #24 (`4e00aa3`) CI `42576144570` 및 검증 결론 (`EXEC PASS`)

| 항목 | 실측값 |
|---|---|
| PR 번호 / 링크 | [PR #24 (`fix/v27-gemini-timeout-20261109`)](https://github.com/JongHyun070105/village-coverage/pull/24) |
| HEAD SHA / Base | `4e00aa3c30a4f72350f799a61833dbb9e3915abb` / `baseRefName: main` |
| 변경 파일 / 라인 수 | `backend/demand.py` (`+5`), `tests/test_demand.py` (`+155`) — **2 files changed, `+160 / -0`** |
| GitHub 병합 가능 상태 | `state: OPEN`, `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN` |
| 최신 CI 실행 (`42576144570`) | [`42576144570`](https://github.com/JongHyun070105/village-coverage/actions/runs/42576144570) (`CI`, `event: pull_request`, `headSha: 4e00aa3c30a4f72350f799a61833dbb9e3915abb`, `status: completed`, **`conclusion: success`**, `06:56:25Z` ~ `07:09:13Z`) — `backend` (`129024187563`: `success`), `frontend` (`129024187815`: `success`) |
| 핵심 검증 포인트 | 1) `GEMINI_REQUEST_TIMEOUT_MS = 10_000` (10초, `google-genai==1.73.1` `types.HttpOptions(timeout=10_000)` 밀리초 단위 계약 충족)<br>2) `types.GenerateContentConfig(..., http_options=...)` 전달 및 `_call_gemini_generate_content()` 구버전 SDK TypeError 호환성 폴백 유지<br>3) 타임아웃·네트워크 예외 시 결정론적 규칙 기반 폴백(`rule_based_fallback`) 즉시 전환<br>4) 자유 텍스트 원문 로그 미노출 및 `PUBLIC_DEMO_MODE` 차단(`HTTP 404 DEMO_MODE_RESTRICTED`) 유지 |

---

## 6. 새 통합 Release Candidate (`integration/v27.1-rc-20261109`) 구성 (`EXEC PASS`)

Primary checkout (`/Users/jonghyun/Projects/village-coverage`, `fix/demand-negation-20261029` @ `ce3bc40`, dirty/untracked 65개)을 전혀 건드리지 않고 격리 워크트리 `/Users/jonghyun/Projects/village-coverage/.worktrees/v27-rc-20261109`에서 새 `origin/main` (`90bd6c87df0278d72228b154ee45ca7b6de45a2f`) 기반 통합 RC를 구성하였다.

| 구분 | 커밋 SHA | Tree SHA | 설명 |
|---|---|---|---|
| Base (`origin/main`) | `90bd6c87df0278d72228b154ee45ca7b6de45a2f` | `3f14959c0396aa395ef03d61e2602927462d476c` | PR #21 병합 완료된 현재 `main` |
| Step 1 (PR #22 + #23 병합) | `4780316503121b606134fc3b0e28c0fb928be6ab` | `9713cb55762e65301f5b8bc67883fa2faab8acfb` | `origin/main` + `15b87a8` 무충돌 병합 (9 files, `+1483/-60`) |
| Step 2 (PR #21~#24 순수 통합 RC) | `460dcbd0b968a40d27b500bc9242f1fd4e0ef42c` | `c92da39fa920b8b0d375b419bd5afe4205223aaf` | `4780316` + PR #24 (`4e00aa3`) 무충돌 병합 (11 files, `+1643/-60`). **이전 v27 RC (`40a3d09`)와 Tree SHA가 바이트 단위로 100% 동일(`0 diff`)** |
| Step 3 (Cloudflare POC 관측성 보강 포함 최종 RC) | **`6e90a67ca07ca9cc76354faa3445462596e587d1`** | **`0710e7859e1201a66f1ca71e54e2ef6fb797ab90`** | `460dcbd` + `poc/cloudflare-workers-keepalive` Workers Logs 관측성·테스트·문서 보강 (15 files vs `origin/main`, `+1831/-60`) |

---

## 7. 통합 RC (`6e90a67`) 실행 테스트 결과 (`EXEC PASS`)

| 검증 영역 | 실행 명령 | 결과 |
|---|---|---|
| Python 린트 | `uv run --no-sync ruff check backend scripts tests` | **PASS** (`All checks passed!`) |
| Python 바이트코드 컴파일 | `uv run --no-sync python -m compileall -q backend scripts tests` | **PASS** (exit 0) |
| 제안서 수용 기준 (R1–R13) | `uv run --no-sync python scripts/proposal_acceptance_check.py` | **PASS (`113 passed, 0 failed`, 18.56s, R1–R13 전 항목 PASS)** |
| 핵심 타겟 Pytest (Keep-Alive + Demand + Public Demo) | `uv run --no-sync pytest -q tests/test_render_keepalive.py tests/test_demand.py tests/test_public_demo.py` | **PASS (`161 passed, 33 subtests passed`, 17.06s)** |
| 보안·세션·동시성·거버넌스·최적화·API Pytest | `uv run --no-sync pytest -q tests/test_security_headers.py tests/test_request_limits.py tests/test_public_demo_sessions.py tests/test_public_demo_concurrency.py tests/test_governance.py tests/test_optimization.py tests/test_scheduling.py tests/test_api.py` | **PASS (`150 passed, 0 failed`, 168.98s)** |
| Python 의존성 취약점 감사 | `uv export --frozen --no-dev` + `pip-audit==2.10.1 --disable-pip -r ...` | **PASS (`No known vulnerabilities found`)** |
| Frontend 의존성 취약점 감사 | `npm audit --omit=dev --audit-level=high` | **PASS (`found 0 vulnerabilities`)** |
| Frontend 린트 / 타입체크 | `npm run lint` / `npm run typecheck` | **PASS** (exit 0) |
| Frontend 유닛 테스트 (Vitest) | `npm run test:unit` | **PASS (`19 passed, 0 failed`, 704ms)** |
| Frontend 프로덕션 빌드 (`PUBLIC_DEMO=true`) | `NEXT_PUBLIC_PUBLIC_DEMO_MODE=true NEXT_PUBLIC_API_URL=http://127.0.0.1:8010 npm run build` | **PASS** (Next.js 16.4.3, 정적/동적 17개 라우트 생성 성공) |
| Frontend Public Demo Playwright E2E | `npx playwright test --config=playwright.public-demo.config.ts` | **PASS (`16 passed`, 2.4m)** — `/plans` stale region 자동 교정, cold-start wake retry, 4-viewport 반응형, 세션 격리 전수 통과 |
| Cloudflare Workers POC 유닛 테스트 | `node --test poc/cloudflare-workers-keepalive/test/worker.test.mjs` | **PASS (`13 passed, 0 failed`, 179ms)** |
| Cloudflare Wrangler 번들 검증 | `npx wrangler deploy --dry-run` (`wrangler 4.158.0`) | **PASS** (`Total Upload: 16.56 KiB / gzip: 4.24 KiB`) |
| 독립 교차 검증 (`orch-parallel` `gemini-high`) | `orch-collect --batch parallel-261109-164046-8b5779` (`w-164048-c6af93e5`) | **PASS** (기계적 재실행 `pytest` 162 passed, 4개 핵심 주장 `HIGH` 신뢰도 검증 완료) |

---

## 8. GitHub Actions `schedule` 핑 관측 결과 (`.github/workflows/render-free-keepalive.yml`)

PR #21이 `2026-11-09T06:56:10Z` (`15:56:10 KST`)에 `main` (`90bd6c8`)으로 병합된 이후 주간 운영 창 마감(`18:00 KST`)까지 **12번의 10분 주기 크론 슬롯(`16:05~17:45 KST`)** 이 경과했으나, GitHub Actions `Render Free keep-alive` (`.github/workflows/render-free-keepalive.yml`) 워크플로의 신규 `schedule` 실행은 **0건**이다.

- 가장 최근 `schedule` 실행: [`42570675754`](https://github.com/JongHyun070105/village-coverage/actions/runs/42570675754) (`2026-11-09T06:02:24Z` / `15:02:24 KST`, PR #21 병합 전 구 `main` `db48109` 대상).
  - **중요 정정 (Workflow `SUCCESS` ≠ HTTP 200)**: 해당 실행(`42570675754`)은 GitHub Actions 워크플로 결론만 `conclusion: success`(`exit 0`)였을 뿐, 실제 job 로그에서는 아래와 같이 **HTTP GET 요청을 단 1건도 보내지 않고 코드상 SKIP(`skipped_late_schedule`)** 처리되었다:
    ```text
    outcome=schedule_delay delay_seconds=450
    outcome=skipped_late_schedule delay_seconds=450
    ```
  - 따라서 `42570675754`에서는 Web/API HTTP GET 전송이나 HTTP 200 응답이 전혀 발생하지 않았다.
- `.github/workflows/render-free-keepalive.yml` 누적 실행 정밀 구분 집계 (`2026-11-03 15:26Z` ~ `2026-11-09 09:25Z`):

| 구분 항목 | 실측값 | 판정 및 비고 |
|---|---|---|
| GitHub `schedule` 실행 생성 | **24회** (전체 25회 중 `workflow_dispatch` 1회 제외) | 기대 슬롯 대비 ~7.5%만 생성 (`15:56:10 KST` PR #21 병합 후 `0회`) |
| GitHub Actions job `SUCCESS` | **22회** | 모두 스크립트 `exit 0` 종료일 뿐 HTTP 핑 성공이 아님 |
| Keep-Alive 코드상 `SKIP` (`skipped_late_schedule`) | **22회** (`42570675754` `delay_seconds=450` 포함) | **실제 HTTP GET 0건** (구 `main` `db48109`의 `delay > 120s` 조기 스킵 결함) |
| 예약 실행 중 실제 HTTP `GET` 전송 | **2회** (`41980788277`, `42344214454`) | 각 9회(`web`×3, `api`×3, `integrated-health`×3) 총 18회 GET 전송 → 구 `main` 3회 시도 한도로 인해 **전수 HTTP 503 (`conclusion: failure`)** |
| 예약 실행의 Render `HTTP 200` (Web / API / 통합) | **`0건 / 0건 / 0건`** | **예약 실행을 통한 HTTP 200 성공은 0건 (`FAIL`)** |
| 직접 수행한 수동 health probe | 수동 `curl` / 로컬 `wrangler dev --local` 프로브 | Cold Start(약 92.6~102.5초) 복구 후 Web/API `HTTP 200` 확인됐으나, 이는 **수동 프로브 증거**이며 GitHub 예약 실행의 성공 증거가 아님 |

**3대 구분 판정**:
1. **코드의 스케줄 지연 처리 (`EXEC PASS` - 로컬/단위 테스트)**: PR #21(`90bd6c8`) 반영으로 GitHub cron 전달이 지연되더라도 KST `08:55~17:59` 운영 창 내부이면 스킵하지 않고 핑을 수행하며, `18:00 KST` 이후 도착분만 `skipped_window`로 안전 차단한다. (단, 병합 후 실제 `schedule` 이벤트가 0건이어서 운영 예약 실행으로는 미관측).
2. **HTTP 콜드스타트 복구 (`EXEC PASS` - 로컬/단위 테스트)**: PR #22/#23(`7979253`/`15b87a8`, 통합 RC `6e90a67`)에서 엔드포인트당 최대 16회(`240s`), 전체 `480s`, `18:00 KST` 하드 컷오프 예산으로 Render Free 콜드스타트(50~120초)를 복구한다. *(현재 `origin/main` `90bd6c8`에는 PR #22가 아직 미병합 상태이므로 PR #22 병합 전까지 `main`의 시도 예산은 3회/38초임).*
3. **GitHub의 스케줄 실행 주기 및 예약 HTTP 200 (`FAIL`)**: GitHub Actions 호스티드 러너의 `schedule` 이벤트 디스패치 자체가 2~6시간 이상 누락(PR #21 병합 후 주간 창 마감까지 0회 실행, 누적 예약 HTTP 200 `0건`)되어, Render Free의 15분 비활성 슬립을 GitHub Actions `schedule`만으로는 예방할 수 없다.

---

## 9. Cloudflare Workers Keep-Alive POC 관측성 보강 및 전환 계획 (`EXEC PASS` 로컬 / 운영 `NOT_VERIFIABLE`)

통합 RC 커밋 `6e90a67ca07ca9cc76354faa3445462596e587d1`에서 `poc/cloudflare-workers-keepalive/`를 다음과 같이 보강하였다:

1. **로그 수집 설정 활성화 (`wrangler.toml`, 영구 보존 아님)**:
   - `[observability]` 블록 추가 (`enabled = true`, `head_sampling_rate = 1`) — Cloudflare에 배포될 경우 `wrangler tail` 실시간 세션 없이도 Cloudflare 대시보드 **Workers Logs**로 구조화 JSON 로그 수집이 활성화되는 **설정**이다.
   - **중요 구분**: 현재는 로컬 설정만 추가된 상태이며 **실제 Cloudflare 운영 배포 전이므로 수집된 운영 로그는 0건(`NOT_VERIFIABLE`)** 이다. 또한 Workers Logs는 **영구 보존 로그가 아니며**, 무료 플랜에서는 **3일(72시간)만 보존**된 뒤 자동 삭제되고 외부 영구 저장소(Logpush 등)는 무료 플랜에서 지원되지 않는다.
2. **8대 필수 텔레메트리 필드 완비 (`src/index.mjs`)**:
   - `scheduled_start`, `endpoint_attempt`, `endpoint_complete`, `scheduled_complete` 이벤트에 아래 8개 필드를 모두 구조화 JSON으로 기록:
     1) `scheduled_at` (cron scheduled time ISO-8601)
     2) `started_at` (실제 실행 시작 시각 ISO-8601)
     3) `request_sent` (`true`/`false`) 및 `method` (`"GET"`)
     4) `status` (마지막 HTTP 상태 코드 또는 `null`)
     5) `attempts` / `retries` (총 시도 횟수 및 재시도 횟수)
     6) `elapsed_ms` (엔드포인트별 및 전체 소요 시간 ms)
     7) `outcome` (`"ok"` | `"skipped_window"` | `"partial"` | `"failed"`)
     8) `failure` (`null` 또는 실패 원인 코드)
   - **개인정보/응답 본문/URL 쿼리 비노출**: 고정된 3개 허용 URL(쿼리 문자열 없음)만 호출하며, 응답 바디는 최대 4,096바이트까지만 메모리에서 읽어 상태(`status=="ok"`, HTML 마커)만 대조 후 즉시 폐기하고 로그에는 절대 출력하지 않음.
3. **Cloudflare Free 플랜 한도 및 보존 기간 구분**:
   - Workers 요청 한도: 일 100,000건 대비 일 54건(0.054%), CPU 10ms/invocation 대비 <2ms(네트워크 I/O 대기는 CPU 시간에 미포함).
   - Subrequest 한도: 무료 50 subrequests/invocation 대비 `redirect: "manual"`(리디렉션 추가 요청 0건), 합성 루프 상한 최대 48건(3 엔드포인트 × 16회), 실제 wall-clock(4분/엔드포인트, 8분/실행, 5s/10s/20s 백오프) 상한 **최대 30건**(14 + 14 + 2)으로 50건 미만 보장.
   - **Workers Logs 보존 기간**: 무료 플랜 **일 200,000 로그 이벤트, 보존 기간 3일(72시간)** (영구 보존 아님; 장기 보존 필요 시 3일 이내 주기적 조회/내보내기 필요).
   - **Cron Events 대시보드**: **최근 100회 실행 이력**만 표시(하루 54회 기준 약 1.85일 분량).
4. **이중 스케줄러 중복을 제거한 단일 스케줄러 전환(Zero-Overlap Cutover) 및 롤백 절차**:
   - **위험 제거 원칙**: `wrangler.toml`에 `[triggers] crons = [...]`가 선언된 상태로 GitHub `schedule` 비활성화 전에 `wrangler deploy`를 실행하면 두 스케줄러가 동시에 Keep-Alive 요청을 보내게 되므로, **병행 카나리 배포를 금지**하고 반드시 아래 순서를 따른다.
   - **Step 1 (계정·무료 한도·로컬 검증)**: Cloudflare 인증(`npx wrangler whoami`) → Workers Free 플랜 및 과금 수단 미등록 확인 → 계정 내 기존 Cron Trigger 수 확인(최대 5개 중 여유 ≥3개 필수) → 로컬 `node --test` 및 `npx wrangler dev --local` + `/cdn-cgi/local/scheduled` 수동 호출 검증(또는 `crons = []` 빈 배열로 트리거 없이 코드만 선배포).
   - **Step 2 (GitHub `schedule` 선행 비활성화 및 잔여 잡 종료 확인)**: `.github/workflows/render-free-keepalive.yml`에서 `schedule:` 블록만 제거(`workflow_dispatch:`는 수동 복구용으로 유지)하여 `main` 반영 후, `gh run list --workflow render-free-keepalive.yml --event schedule --status in_progress` 및 `--status queued`가 모두 `0건`임을 확인한다.
   - **Step 3 (Cloudflare Cron Trigger 단독 활성화 및 전파 대기)**: GitHub 예약 실행이 완전히 멈춘 상태에서 `wrangler.toml`의 3개 Cron Trigger(`55 23 * * *`, `5,15,25,35,45,55 0-7 * * *`, `5,15,25,35,45 8 * * *`)로 `npx wrangler deploy`를 실행한다(전파에 최대 15분 소요 가능; 전환 구간의 짧은 핑 공백은 허용하되 이중 실행은 절대 금지).
   - **Step 4 (운영 관측 및 비상 롤백)**: Cron Events 및 Workers Logs(3일 보존)에서 `scheduled_complete`(`outcome: "ok"`, Web/API HTTP 200, 10분 간격)를 확인한다. 실패 시 먼저 Cloudflare Cron Trigger를 비활성화(`crons = []` 재배포 또는 `wrangler delete`)하고 진행 중인 Worker 실행 종료를 확인한 뒤에만 `.github/workflows/render-free-keepalive.yml`의 `schedule:`을 복구한다.

---

## 10. SQLite 데이터 영속성 정책 옵션 A vs B 코드 대조 (`STATIC` 분석 / 사용자 선택 대기)

| 비교 항목 | 옵션 A: 휘발성 체험형 데모 공식화 (**권장**) | 옵션 B: 영속 DB 전환 (Render Disk 또는 외부 Postgres) |
|---|---|---|
| 현재 프론트엔드 UI/배너 정합성 | **완전 부합 (코드 수정 0줄)**. `frontend/app/layout.tsx:20-31` 전역 배너에 이미 *"계획·불참·승인 상태는 브라우저 세션별로 격리되며 30분 동안 활동이 없으면 만료됩니다. 무료 데모 서버의 재시작·재배포 시 임시 계획이 초기화될 수 있습니다."* 가 명시되어 있음. 또한 `frontend/app/page.tsx:726-735` 및 `public-demo-route-guard.tsx`에서 시연용 합성 데이터임을 안내함. | UI 배너 문구 수정 필요(재시작 시 초기화 안내 제거 또는 영속 보관 기간 안내로 변경). |
| 현재 백엔드 아키텍처 정합성 | **완전 부합 (코드 수정 0줄)**. `backend/public_demo.py:42-85`가 주민 설문·자유텍스트·피드백·CSV 업로드를 원천 차단(`HTTP 404 DEMO_MODE_RESTRICTED`)하고, 합성 데이터 기반 세션별 임시 계획만 30분 idle TTL(`PUBLIC_DEMO_SESSION_IDLE_SECONDS = 1800`)로 관리함. 서버 재시작 시 `backend/main.py:130-156` lifespan에서 기본 시드 DB를 `/tmp/villagecoverage-public-demo.sqlite`로 자동 복원함. | **코드 및 인프라 변경 필수**:<br>1) `backend/database.py:672-681`이 `PUBLIC_DEMO_MODE`에서 `tempfile.gettempdir()`(`/tmp`) 외부 경로를 보안 예외(`RuntimeError`)로 거부하므로 영속 디스크 마운트 경로 허용 패치 필요.<br>2) **Render Persistent Disk 선택 시**: Render Web Service를 Free → **Starter 유료 플랜($7/월+) + Disk 비용**으로 승격해야 하며 `render.yaml`에 `disk:` 블록 추가 필요(무중단 배포 비활성화).<br>3) **외부 Postgres 선택 시**: `backend/database.py`(3,585줄)가 `sqlite3` 전용 문법(`PRAGMA user_version`, `executescript`, `BEGIN IMMEDIATE`, 파일 크기 가드)에 직접 결합되어 있어 DB 계층 전면 재작성 필요. |
| 비용 / 운영 리스크 | **$0 (무료 유지)**, 배포 즉시 적용 가능, 디스크 포화 리스크 없음(64MB 상한 + 재시작 시 클린 시드 복원). | 유료 인프라 비용 발생(승인 정책상 비용 발생 작업은 별도 승인 필수) 또는 대규모 DB 엔진 재작성 리스크 발생. |

> **프로덕션 DB 실측 한계 고지**: Render 프로덕션 컨테이너 내부 `/tmp/villagecoverage-public-demo.sqlite`에 현재 어떤 임시 세션 행이 남아 있는지는 Render SSH/Shell 권한 없이 외부 HTTP API만으로는 조회 불가능(`NOT_VERIFIABLE`)하다. 따라서 사용자께서 **옵션 A(휘발성 체험형 데모 유지·공식화)** 와 **옵션 B(영속 DB 전환)** 중 하나를 최종 선택하셔야 `SQLITE_POLICY_RESOLVED` 게이트가 닫힌다.

---

## 11. Render LIVE (`36319c6`) 대비 통합 RC (`6e90a67`) 변경점 요약

- **현재 Render LIVE 배포 커밋**: `36319c6551b5c80d3f8c4e1aaa43bc7bbf8fe6e3` (`submission/public-demo-deploy` 브랜치 HEAD)
- **통합 RC (`6e90a67`)까지 전체 차이**: 53 files changed, `+5068 / -105` (`backend/` + `frontend/` 런타임/테스트 코드는 26 files changed, `+1271 / -92`)
- **무변경(Byte-identical) 핵심 인프라 파일**:
  - `render.yaml`: **0 diff**
  - `pyproject.toml`, `uv.lock`, `frontend/package.json`, `frontend/package-lock.json`: **0 diff**
  - SQLite `SCHEMA_VERSION` (`27`): **0 diff** (DDL 마이그레이션 불필요)
- **LIVE에 반영될 4대 런타임·운영 개선 사항**:
  1. **보안 헤더 미들웨어 (`backend/security_headers.py`) 및 요청 크기/세션 가드**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` 전 응답 적용.
  2. **Gemini SDK 10초 하드 타임아웃 (`backend/demand.py`, PR #24)**: `HttpOptions(timeout=10_000)` 적용으로 LLM 지연 시 워커 블로킹 없이 10초 내 결정론적 규칙 기반 폴백 전환.
  3. **Public Demo 콜드스타트 복구 및 `/plans` Stale Region 레이스 차단 (`frontend/lib/cold-start.ts`, `frontend/lib/api.ts`, `frontend/app/page.tsx`, `frontend/app/plans/page.tsx`, PR #22)**: Render Free 콜드스타트 시 최대 90초(`13회`)까지 헬스 검증 대기 후 자동 로드하며, `/plans` 진입 시 이전 세션의 유효하지 않은 `selectedRegionId`로 인해 `HTTP 404 Region not found`가 발생하던 초기 레이스를 제거.
  4. **Keep-Alive 스케줄 지연 허용·콜드스타트 재시도 확장·Cloudflare Workers POC (`.github/scripts/render_keepalive.py`, `poc/cloudflare-workers-keepalive/`, PR #21/#22/#23 + v27.1)**: KST `09:00~17:59` 운영 창 판정, 16회/240s 콜드스타트 재시도 예산, Cloudflare Workers Cron + Workers Logs 관측성 구비.

---

## 12. Phase L 검증 판정 요약표 (15개 항목)

| # | 검증 항목 | 판정 | 근거 요약 |
|---|---|---|---|
| 1 | PR #21 병합 상태 | **`EXEC PASS`** | `2026-11-09T06:56:10Z` 병합 완료 (`headRefOid: 819fcce`, `mergeCommit: 90bd6c87df0278d72228b154ee45ca7b6de45a2f`) |
| 2 | 새 `main` CI `42576124307` | **`EXEC PASS`** | [`42576124307`](https://github.com/JongHyun070105/village-coverage/actions/runs/42576124307) `completed / success` (`backend` `129024123758` PASS, `frontend` `129024124034` PASS) |
| 3 | PR #22 base `main` 정리 및 CI | **`EXEC PASS`** | `baseRefName: main` 전환 완료 (8 files `+1171/-60`, `MERGEABLE/CLEAN`), 최신 CI [`42580300058`](https://github.com/JongHyun070105/village-coverage/actions/runs/42580300058) `completed / success` |
| 4 | PR #23 stacked 상태 및 CI | **`EXEC PASS`** | `baseRefName: fix/v24.2-coldstart-retry-20261104` 유지 (2 files `+312/-0`, `MERGEABLE/CLEAN`), CI [`42569948191`](https://github.com/JongHyun070105/village-coverage/actions/runs/42569948191) `completed / success` |
| 5 | PR #24 Gemini timeout CI `42576144570` | **`EXEC PASS`** | [`42576144570`](https://github.com/JongHyun070105/village-coverage/actions/runs/42576144570) `completed / success` (`backend` `129024187563` PASS, `frontend` `129024187815` PASS, `MERGEABLE/CLEAN`) |
| 6 | 새 `origin/main` 기반 통합 RC | **`EXEC PASS`** | `.worktrees/v27-rc-20261109` (`integration/v27.1-rc-20261109`) — 순수 PR 통합 `460dcbd` (tree `c92da39`, v27 RC와 `0 diff`) 및 Cloudflare 관측성 보강 포함 `6e90a67` (tree `0710e78`) |
| 7 | Backend/R1-R13/보안/Demand/Keep-Alive 테스트 | **`EXEC PASS`** | R1–R13 `113 passed`, 타겟 pytest `161 passed (33 subtests)`, 확장 보안/세션/동시성/API pytest `150 passed`, `pip-audit` 0건 |
| 8 | Frontend unit/typecheck/lint/build/E2E | **`EXEC PASS`** | `lint` PASS, `typecheck` PASS, `test:unit` `19 passed`, `npm audit` 0건, `build` PASS (17 pages), Playwright Public Demo E2E `16 passed` |
| 9 | GitHub `schedule` 코드 처리 | **`EXEC PASS`** | `.github/scripts/render_keepalive.py` + `tests/test_render_keepalive.py` (`30 passed`)로 KST `09:00~17:59` 운영 창 및 `18:00` 하드 컷오프 검증 완료 |
| 10 | GitHub `schedule` 실제 실행 주기 및 예약 HTTP 200 | **`FAIL`** | PR #21 병합(`15:56:10 KST`) 후 주간 창 마감(`18:00 KST`)까지 12개 크론 슬롯 동안 `schedule` 실행 **0건**. 병합 전 최신 실행 [`42570675754`](https://github.com/JongHyun070105/village-coverage/actions/runs/42570675754)(`15:02:24 KST`, `db48109`)도 job 결론만 `success`일 뿐 로그상 `outcome=skipped_late_schedule delay_seconds=450`으로 **HTTP GET 0건(SKIP)** 이며, 누적 24회 예약 실행 중 **Web/API HTTP 200은 0건** |
| 11 | Cloudflare Workers POC 로컬 검증 | **`EXEC PASS`** | `[observability] enabled = true` 설정(무료 플랜 3일 보존, 영구 보존 아님) + 8대 텔레메트리 필드 검증, `node --test` **`13 passed, 0 failed`**, `wrangler deploy --dry-run` **PASS** (`16.56 KiB`) |
| 12 | Cloudflare Workers 실제 배포·로그 수집·크론 관측 | **`NOT_VERIFIABLE` / `SKIP`** | 사용자 배포 승인 및 Cloudflare 계정 인증 전이므로 미배포·미수집(실제 운영 로그 수집 0건, 무료 플랜/기존 Cron 슬롯 수 `NOT_VERIFIABLE`) |
| 13 | SQLite 정책 기술 대조 | **`STATIC`** | 옵션 A(코드 수정 0줄, 현행 UI 배너·30분 세션 TTL과 부합) vs 옵션 B(`database.py:674` 경로 제한 해제 + 유료 Disk 또는 DB 계층 재작성) 코드 대조 완료; 프로덕션 `/tmp` 내부 데이터는 `NOT_VERIFIABLE` |
| 14 | Render 재배포 준비도 | **`EXEC PASS`** | LIVE(`36319c6`) 대비 `render.yaml`/락파일/DB 스키마(`v27`) 변경 0건, 통합 RC 전수 테스트 통과 |
| 15 | Primary checkout 보존 | **`EXEC PASS`** | `/Users/jonghyun/Projects/village-coverage` (`fix/demand-negation-20261029` @ `ce3bc40`) dirty/untracked **65개 그대로 보존** |

---

## 13. 남은 사용자 승인 목록 및 다음 실행 단계

### A. 브로커 승인 요청(`orch-approval request`) 대상 (즉시 실행 가능 작업)
1. **PR #22 (`fix/v24.2-coldstart-retry-20261104`, HEAD `7979253eac579db9e084fd6d6222b099adb12396`) → `main` 병합**:
   - 명령: `gh pr merge 22 --merge --match-head-commit 7979253eac579db9e084fd6d6222b099adb12396`
   - 선결 조건: 새 `main` CI `42576124307` `SUCCESS`, PR #22 base=`main` 전환 완료, 최신 CI `42580300058` `SUCCESS`, `MERGEABLE/CLEAN` 모두 충족.
2. **PR #24 (`fix/v27-gemini-timeout-20261109`, HEAD `4e00aa3c30a4f72350f799a61833dbb9e3915abb`) → `main` 병합**:
   - 명령: `gh pr merge 24 --merge --match-head-commit 4e00aa3c30a4f72350f799a61833dbb9e3915abb`
   - 선결 조건: 최신 CI `42576144570` `SUCCESS`, `MERGEABLE/CLEAN`, PR #22/#23와 파일 충돌 0건(`460dcbd`에서 검증 완료).
3. **`docs/v26-release-gate-20261109` 브랜치(`V27_1_INTEGRATION_HANDOFF.md` 포함) 원격 푸시**:
   - 명령: `git -C /Users/jonghyun/Projects/village-coverage/.worktrees/v26-report-20261109 push origin docs/v26-release-gate-20261109`

### B. 순차 후속 단계 (위 병합 및 사용자 의사결정 이후)
1. **PR #23 base 전환 및 병합**: PR #22 병합 직후 `gh pr edit 23 --base main` 실행 → diff 2파일(`+312/-0`) 및 `MERGEABLE` 확인 → 별도 승인 후 `gh pr merge 23 --merge --match-head-commit 15b87a80d3fb8890b2ccb21008fcdda49f9ee217`.
2. **SQLite 정책 최종 결정 (`SQLITE_POLICY_RESOLVED`)**: 옵션 A(권장, 휘발성 체험형 데모 공식화) 또는 옵션 B(영속 DB 전환) 중 사용자 선택.
3. **Cloudflare Workers Keep-Alive 단일 스케줄러 전환 (이중 실행 금지)**: Cloudflare 계정/Free 한도 확인 → `.github/workflows/render-free-keepalive.yml`에서 `schedule:` 선행 제거(`workflow_dispatch:` 유지) 및 진행 중 잡 0건 확인 → Cloudflare Cron Trigger(`npx wrangler deploy`) 활성화 및 전파(최대 15분) 후 관측.
4. **Render 프로덕션 배포 (`submission/public-demo-deploy`)**: PR #22/#23/#24가 통합된 `main`을 `submission/public-demo-deploy`에 반영하기 위한 별도 승인 후 푸시 및 LIVE 스모크 체크.
