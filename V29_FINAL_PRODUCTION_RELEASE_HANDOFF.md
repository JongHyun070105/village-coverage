# VillageCoverage v29.1 — 최종 운영 배포·Cloudflare Cron 전환·전체 기능 검증 Handoff (`V29_FINAL_PRODUCTION_RELEASE_HANDOFF.md`)

- **작성/업데이트 시각**: `2026-11-12 15:02 KST` (`2026-11-12T06:02:00Z`)
- **기준 저장소**: `https://github.com/JongHyun070105/village-coverage`
- **Public Web**: `https://villagecoverage-public-demo-web.onrender.com`
- **Public API**: `https://villagecoverage-public-demo-api.onrender.com`
- **목적**: PR #25(`a8a1e86`) CI(`43048635235` Attempt 3) `SUCCESS`, SQLite 옵션 A 확정 및 Render 배포(`b70074cb2c3744e0`, `0b3acf3` → `submission/public-demo-deploy`) LIVE 완료(`RENDER_DEPLOYED = EXEC PASS`), GitHub `schedule:` 제거 PR #26(`67647dc4303c4490`) 병합(`ef99ecf`) 및 `main` CI(`43163875212`) `SUCCESS`(`GITHUB_SCHEDULE_REMOVED = EXEC PASS`), 실제 운영 사이트 전체 브라우저 QA(`PRODUCTION_E2E_PASS = EXEC PASS`) 완료 및 남은 승인 게이트 정리.

---

## 1. 최종 `main` SHA 및 커밋 계보

| 구분 | 커밋 SHA / Tree SHA | 상태 및 검증 내역 |
|---|---|---|
| 현재 원격 `origin/main` (PR #26 병합 완료) | Commit: `ef99ecf732559d4daca933d1b39c9c1ea6be5632`<br>Tree: `c9630eb431bc2818873ec0bd76cf4ffddbb11b08` | PR #21(`90bd6c8`), PR #22(`63e8d57`), PR #23(`8ccabea`), PR #24(`0b3acf3`), **PR #26(`ef99ecf`, `schedule:` 제거·`workflow_dispatch:` 보존)** 병합 완료. CI [`43163875212`](https://github.com/JongHyun070105/village-coverage/actions/runs/43163875212) `backend`·`frontend` 전수 **`SUCCESS`**. |
| 현재 Render 운영 배포 브랜치 (`origin/submission/public-demo-deploy`) | Commit: `0b3acf383351b16d2a33c336f1f3c9eed7be12a3`<br>Tree: `c92da39fa920b8b0d375b419bd5afe4205223aaf` | 브로커 승인 `b70074cb2c3744e0` 실행으로 `36319c6..0b3acf3` fast-forward 푸시 및 Render Web/API 실제 빌드·LIVE 전환 완료 (`2026-11-12 14:51 KST`). `ef99ecf` 및 PR #25(`a8a1e86`)와 런타임 코드(`backend/`, `frontend/`, `render.yaml`, `data/`) **100% 동일(`0 diff`)**. |
| [PR #25](https://github.com/JongHyun070105/village-coverage/pull/25) HEAD | Commit: `a8a1e8653282625e0ae2022779f5d5bbc62c2aaa`<br>Tree: `6617263dbd381509bf61b0e620a9b1abf18a7e62` | Base: `main`(`ef99ecf`), `MERGEABLE` / `CLEAN`. `poc/cloudflare-workers-keepalive/` 하위 5개 파일만 변경(`+282/-18`). |
| Primary Checkout 보존 | Branch: `fix/demand-negation-20261029`<br>HEAD: `ce3bc40a1815b59f507a7b9cf2a95d32e1567d02` | 미커밋·미추적 파일 **65건 전수 보존(`EXEC PASS`)**. |

### 1.1 PHASE 3 릴리스 후보 12대 항목 정밀 대조 (`0b3acf3` + PR #25 `a8a1e86`)

| # | 점검 항목 | 코드 / 설정 근거 (`0b3acf3` 및 `a8a1e86`) | 판정 |
|---|---|---|---|
| 1 | Gemini 10초 timeout | `backend/demand.py:844, 888` (`GEMINI_REQUEST_TIMEOUT_MS = 10_000`, `http_options={"timeout": GEMINI_REQUEST_TIMEOUT_MS}`) 및 `tests/test_demand.py` 실제 SDK 레이어 타임아웃 테스트 통과 | **`EXEC PASS`** |
| 2 | Deterministic fallback | `backend/demand.py:143, 603, 744, 860-910` (`deterministic_structure()`, 무키·오류·타임아웃·스키마 불일치 시 즉시 결정론적 폴백 반환) | **`EXEC PASS`** |
| 3 | Cold Start 재시도 | `.github/scripts/render_keepalive.py:23, 184-264` 및 `poc/cloudflare-workers-keepalive/src/index.mjs:10-16, 218-347` (`MAX_ATTEMPTS = 16`, 엔드포인트당 `240s`, 전체 `480s` 예산, `5s → 10s → 20s` 백오프, `Retry-After` `180s` 상한) | **`EXEC PASS`** |
| 4 | `/plans` stale region 복구 | `frontend/app/plans/page.tsx:89-95, 142-160, 216-242` (`regions.some()` 검증으로 유효하지 않은 저장 지역을 `default_region_id`로 교정하고 선택된 계획의 `region_id`와 동기화) | **`EXEC PASS`** |
| 5 | 보안 헤더 | `backend/security_headers.py` 및 `frontend/next.config.ts` (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`) | **`EXEC PASS`** |
| 6 | 기존 API 계약 | `backend/main.py` 및 `backend/public_demo.py:42-98` (공개 데모 읽기·안전 계산·임시 계획 생성/승인/내보내기 계약 보존, R1–R13 `113 passed`) | **`EXEC PASS`** |
| 7 | Cloudflare 관측성 | `poc/cloudflare-workers-keepalive/wrangler.toml:7-9` (`[observability] enabled = true, head_sampling_rate = 1`) 및 `src/index.mjs:378-399, 495-516` 구조화 JSON 이벤트 | **`EXEC PASS`** |
| 8 | `wrangler.nocron.toml` | `poc/cloudflare-workers-keepalive/wrangler.nocron.toml:13-14` (`[triggers] crons = []` 명시로 기존 트리거 완전 제거 보장) | **`EXEC PASS`** |
| 9 | GitHub workflow | `.github/workflows/ci.yml` 및 `.github/workflows/render-free-keepalive.yml` (`permissions: contents: read`, UTC 크론 및 `--scheduled-cron` 전달) | **`EXEC PASS`** |
| 10 | DB schema | `backend/database.py` (`SCHEMA_VERSION = 27`, LIVE `36319c6` 대비 스키마 변경 `0건`) | **`EXEC PASS`** |
| 11 | 의존성 | `pyproject.toml`, `uv.lock`, `frontend/package.json`, `frontend/package-lock.json` (LIVE `36319c6` 대비 변경 `0건`, 취약점 `0건`) | **`EXEC PASS`** |
| 12 | Render 설정 | `render.yaml` (LIVE `36319c6` 대비 변경 `0건`, Web/API Free 플랜 및 헬스체크 경로 일치) | **`EXEC PASS`** |

---

## 2. PR #25 병합 전 검증 및 병합 상태

- **대상 PR**: [PR #25](https://github.com/JongHyun070105/village-coverage/pull/25) (`feat/v27.1-cloudflare-observability-20261109` → `main`, HEAD `a8a1e8653282625e0ae2022779f5d5bbc62c2aaa`)
- **병합 전 10대 조건 점검**:
  1. Base `main`: `gh pr view 25` 기준 `baseRefName: "main"` 확인 (`EXEC PASS`).
  2. `MERGEABLE` / `CLEAN`: `mergeable: "MERGEABLE"`, `mergeStateStatus: "CLEAN"` 확인 (`EXEC PASS`).
  3. 정확한 변경 파일 5개: `poc/cloudflare-workers-keepalive/README.md`(`+9/-3`), `src/index.mjs`(`+135/-15`), `test/worker.test.mjs`(`+120/-0`), `wrangler.nocron.toml`(`+14/-0`), `wrangler.toml`(`+4/-0`) (`EXEC PASS`).
  4. Cloudflare POC 외 불필요한 변경 없음: `git diff --numstat origin/main...a8a1e86` 결과 5개 파일 외 변경 `0건` (`EXEC PASS`).
  5. Wrangler 일반 설정 유효: `wrangler deploy --config wrangler.toml --dry-run` 통과 (`16.56 KiB / gzip 4.24 KiB`) (`EXEC PASS`).
  6. Wrangler 무크론 설정 유효: `wrangler deploy --config wrangler.nocron.toml --dry-run` 통과 (`16.56 KiB / gzip 4.24 KiB`, `[triggers] crons = []` 포함) (`EXEC PASS`).
  7. 관측성 로그 개인정보 비노출: `src/index.mjs`에서 응답 본문·쿼리스트링·쿠키·PII를 일절 기록하지 않으며 유닛 테스트로 검증됨 (`EXEC PASS`).
  8. Subrequest 사용량 제한: `redirect: "manual"`, 8분 전체 예산(`MAX_RUN_MS`) 내 지속 503 시 최대 `30회`, 시계 정지 합성 상한 `48회` (< Free 한도 50회) (`EXEC PASS`).
  9. 자동 배포 CI 미포함: `.github/workflows/ci.yml` 및 `.github/workflows/render-free-keepalive.yml`에 Wrangler/Cloudflare 배포 스텝 없음 (`EXEC PASS`).
  10. GitHub Actions CI: `a8a1e8653282625e0ae2022779f5d5bbc62c2aaa`에 대해 [`43048635235`](https://github.com/JongHyun070105/village-coverage/actions/runs/43048635235) Attempt 3 실행 결과 `backend`(`130972427305`) 및 `frontend`(`130972425216`) 전수 **`SUCCESS`** (`EXEC PASS`).
- **병합 승인 요청**:
  - 브로커 승인 ID: **`a3c60e9e49a841f9`** (`PENDING` — TUI 승인 대기)
  - 정확한 명령: `gh pr merge 25 --merge --match-head-commit a8a1e8653282625e0ae2022779f5d5bbc62c2aaa`

---

## 3. GitHub CI 검증 결과 (PHASE 1 완료)

### 3.1 PR #25 CI(`43048635235`) 장애 원인 규명 및 해결 (PHASE 1)
- **원인 분석 (7대 항목)**:
  1. **Ubuntu DNS 해석 실패**: Attempt 2(`130626993625`)의 Step 14(`Install Playwright Chromium`)에서 `npx playwright install --with-deps chromium`이 호출한 `apt-get`이 `/etc/apt/apt-mirrors.txt`(`http://azure.archive.ubuntu.com/ubuntu`) 미러를 조회하는 중 `Temporary failure resolving 'azure.archive.ubuntu.com'` 일시적 DNS 장애 발생(`2026-11-11T15:46:02Z ~ 15:52:21Z`).
  2. **APT 패키지 다운로드 실패**: 폰트 패키지 9개(`fonts-ipafont-gothic`, `fonts-freefont-ttf`, `fonts-tlwg-loma-otf`, `fonts-unifont`, `fonts-wqy-zenhei`, `xfonts-encodings`, `xfonts-utils`, `xfonts-cyrillic`, `xfonts-scalable`) 아카이브 다운로드가 DNS 실패로 중단(`exit code 100`).
  3. **Playwright 설치 설정**: `.github/workflows/ci.yml:74` `npx playwright install --with-deps chromium` — 기존 성공 실행과 동일.
  4. **GitHub Actions 러너 이미지**: `ubuntu-24.04` (`Version: 20261101.360.1`, Provisioner `20261028.624`).
  5. **Chromium 버전**: `Chrome for Testing 153.0.8010.12 (playwright chromium v1243)`.
  6. **기존 성공 CI(`42761296270`)와의 차이**: 러너 이미지·Playwright 버전·워크플로 설정 차이 `0건`; 순수 Azure Ubuntu APT 미러의 일시적 외부 DNS 장애.
  7. **실제 코드 변경과의 관련성**: PR #25는 `poc/cloudflare-workers-keepalive/` 하위 5개 파일만 수정하며 `frontend/`, `backend/`, `.github/workflows/` 변경 `0건`. 로컬 `node --test poc/cloudflare-workers-keepalive/test/worker.test.mjs` 역시 `16/16 pass` 확인.
- **해결 결과**: `gh run rerun 43048635235 --failed` 1회 제한 재시도(Attempt 3)로 `Install Playwright Chromium`, `Run standard and Public Demo browser tests`, `Run responsive UI regression at four viewports`까지 전 단계 **`SUCCESS`** 달성.

| 대상 | 브랜치 / SHA | 워크플로 Run ID | 결과 |
|---|---|---|---|
| PR #24 병합 `main` | `main` @ `0b3acf383351b16d2a33c336f1f3c9eed7be12a3` | [`42761296270`](https://github.com/JongHyun070105/village-coverage/actions/runs/42761296270) | `completed / success` (`backend` `129647334504` PASS, `frontend` `129647334039` PASS) — **`EXEC PASS`** |
| PR #25 HEAD | `feat/v27.1-cloudflare-observability-20261109` @ `a8a1e8653282625e0ae2022779f5d5bbc62c2aaa` | [`43048635235`](https://github.com/JongHyun070105/village-coverage/actions/runs/43048635235) (Attempt 3) | `completed / success` (`backend` `130972427305` `SUCCESS`, `frontend` `130972425216` `SUCCESS`, Playwright E2E 및 4개 뷰포트 반응형 회귀 전수 통과) — **`EXEC PASS`** |
| PR #26 HEAD (`schedule:` 제거) | `chore/v29-keepalive-manual-only-20261112` @ `a755e5c9a1e229bc18d7625320a1cc2f87d3c529` | [`43155786470`](https://github.com/JongHyun070105/village-coverage/actions/runs/43155786470) | `completed / success` (`backend` `130975268599` `SUCCESS`, `frontend` `130975268234` `SUCCESS`) — **`EXEC PASS`** |
| **현재 최신 `main` (PR #26 병합)** | `main` @ `ef99ecf732559d4daca933d1b39c9c1ea6be5632` | [`43163875212`](https://github.com/JongHyun070105/village-coverage/actions/runs/43163875212) | `completed / success` (`backend` `131001088799` `SUCCESS`, `frontend` `131001088538` `SUCCESS`) — **`EXEC PASS`** |

---

## 4. Render Web/API 배포 완료 및 무료 한도·비용 위험 감사 (Phases 4 & 5)

- **Render 배포 실행 완료 (`RENDER_DEPLOYED = EXEC PASS`)**:
  - 승인 ID **`b70074cb2c3744e0`** 실행 (`orch-approval run b70074cb2c3744e0`, `2026-11-12 14:48:45 KST`):
    ```text
    To https://github.com/JongHyun070105/village-coverage.git
       36319c6..0b3acf3  0b3acf383351b16d2a33c336f1f3c9eed7be12a3 -> submission/public-demo-deploy
    ```
  - **API 서비스 (`villagecoverage-public-demo-api.onrender.com`) LIVE 전환 확인**: 푸시 약 1분 47초 뒤(`2026-11-12 14:50:32 KST`, `rndr-id: c8a6b323-9e08-40c2`) `/health` 및 `/api/health`에서 `HTTP 200`과 함께 `0b3acf3` 신규 보안 헤더(`Permissions-Policy: camera=(), geolocation=(), microphone=(), payment=(), usb=()`, `Strict-Transport-Security: max-age=31536000`) 반영 확인.
  - **Web 서비스 (`villagecoverage-public-demo-web.onrender.com`) LIVE 전환 확인**: 푸시 약 2분 42초 뒤(`2026-11-12 14:51:27 KST`, `rndr-id: bca092cd-ddff-47ed`) Next.js 빌드 완료 후 신규 ETag(`W/"zknrx97stzfc6"`), `Permissions-Policy: camera=(), geolocation=(), microphone=(), payment=(), usb=()`, `Strict-Transport-Security: max-age=31536000`, `/plans` stale region 자동 교정 번들 반영 확인.
  - **런타임 SHA 일치성**: `origin/submission/public-demo-deploy`(`0b3acf383351b16d2a33c336f1f3c9eed7be12a3`)는 `origin/main`(`ef99ecf732559d4daca933d1b39c9c1ea6be5632`) 및 PR #25(`a8a1e86`)와 런타임 디렉터리(`backend/`, `frontend/`, `render.yaml`, `data/`)가 **100% 동일(`0 diff`)** 하며, PHASE 7 지시에 따라 워크플로 전용 커밋(`ef99ecf`)으로 인한 불필요한 Render 재배포를 유발하지 않음.
- **`render.yaml` 설정 검증 (`EXEC PASS` / `STATIC`)**:
  - `villagecoverage-public-demo-api` (Python 3.12.10, `plan: free`, `region: singapore`, `/health`)
  - `villagecoverage-public-demo-web` (Node 22.18.0, `plan: free`, `region: singapore`, `/`)
  - `36319c6` 대비 `render.yaml`, `pyproject.toml`, `uv.lock`, `frontend/package.json`, `frontend/package-lock.json`, DB `SCHEMA_VERSION`(`27`) 변경 **0건**.
- **Render Free 인스턴스 시간 산정**:
  - Render Free 한도: 워크스페이스당 월 **750 무료 인스턴스 시간**.
  - 24시간 상시 가동 시 2개 서비스 × 720~744h = 월 1,440~1,488시간으로 한도 초과 → **24시간 Keep-Alive 엄격 금지**.
  - 설계된 주간 운영 시간(`08:55~18:00 KST`, 일 9시간 5분 = `9.083h`) 동안만 2개 서비스를 유지할 경우: 30일 기준 약 **545시간**(31일 기준 약 **563.2시간**)으로 750시간 한도 대비 약 **187~205시간(25~27%) 여유**.
- **계정 실시간 사용량 확인 한계 (`NOT_VERIFIABLE`)**:
  - 로컬 환경에 `RENDER_API_KEY` 및 Render CLI 세션이 존재하지 않아 워크스페이스 내 타 Free 서비스 유무, 당월 누적 사용 시간, 잔여 무료 시간, 대역폭(100 GB/월), 빌드 파이프라인 사용량은 API로 직접 조회할 수 없음.

---

## 5. SQLite 데이터 보존 정책 및 사용자 승인 게이트 (Phase 5)

- **데모 DB 경로**: `/tmp/villagecoverage-public-demo.sqlite` (`backend/database.py:674-681`, 최대 64 MiB 상한 `PUBLIC_DEMO_MAX_DATABASE_BYTES`).
- **코드 기준 6대 필수 확인 결과 (`EXEC PASS`)**:
  1. **보존 대상 기록 존재 여부**: 공개 데모에서 생성되는 공급계획·회차·불참·데모 승인 기록은 브라우저 세션 쿠키(`vc_demo_session` SHA-256 해시)별로 격리되며 **30분 비활동 시 자동 만료·삭제(`PUBLIC_DEMO_SESSION_IDLE_SECONDS = 1800`)** 됨.
  2. **개인식별정보(PII) 포함 가능성**: `backend/public_demo.py:42-98` allowlist가 설문 등록, 자유텍스트 수요 입력(`/api/demand*`), CSV 업로드(`/api/imports*`), 피드백, 중복 판정 API를 전수 `HTTP 404 DEMO_MODE_RESTRICTED`로 차단하므로 **운영 DB에 주민 개인정보가 저장될 경로가 없음(`0건`)**.
  3. **재시작 후 기존 세션 동작**: 재시작 후 읽기(`GET`) 요청은 기본 시드 데이터를 즉시 반환하며, 초기화된 이전 세션 쿠키로 쓰기 요청 시 `HTTP 410 DEMO_SESSION_EXPIRED`와 새로고침 안내(`frontend/components/api-error.tsx`)를 표시함.
  4. **초기 시드 복원**: 컨테이너 시작 시 `initialize_public_demo_storage()`(`backend/main.py:304`)가 `data/demo.json`에서 54개 지역 및 2,916개 경로 시드를 자동 복원함 (`road_routes_cached=2916, road_route_origins=54` 실측 확인).
  5. **계획 소실 시 사용자 안내**: `/plans`에서 계획 미존재 시 시나리오 생성 안내를 표시하며, 삭제된 `schedule_id` 조회 시 `ApiErrorNotice` 및 다시 불러오기 버튼을 제공함.
  6. **현재 UI와의 일치성**: `frontend/app/layout.tsx:24` 전역 상단 배너에 *"계획·불참·승인 상태는 브라우저 세션별로 격리되며 30분 동안 활동이 없으면 만료됩니다. 무료 데모 서버의 재시작·재배포 시 임시 계획이 초기화될 수 있습니다."* 가 이미 명시되어 있음.
- **사용자 결정 및 실행 완료 (`SQLITE_POLICY_A = EXEC PASS`, `RENDER_DEPLOYED = EXEC PASS`)**:
  - **옵션 A 명시적 승인 및 반영 완료**: 순수 임시·합성 데이터 공개 데모 유지, 기존 SQLite(`/tmp/villagecoverage-public-demo.sqlite`) 및 30분 세션 TTL 유지, 주민 개인정보 입력 제한 유지, 재시작 시 기본 시드 자동 복원 및 UI 임시 기록 안내 유지.

---

## 6. Cloudflare 계정·무료 한도·사전 배포 검증 (Phases 6 & 7)

Cloudflare REST API 및 Wrangler(`4.158.0`) OAuth 세션을 통해 실제 계정 상태를 조회한 결과(이메일·토큰 원문 비노출):

| 점검 항목 | 실측 결과 | 판정 |
|---|---|---|
| 로그인 상태 및 Account ID | OAuth 세션 유효, Account ID: `6c9308b544b9f81b63327ba4c2ff5315` (`type: standard`, `workers.dev` 서브도메인: `how-about-this-api`) | **`EXEC PASS`** |
| 기존 Worker 스크립트 수 | 계정 내 기존 Worker **2개** (`reviewai-api-proxy`, `take-your-medicine-api-proxy-production`) — Free 한도(100개) 이내 | **`EXEC PASS`** |
| **기존 Cron Trigger 수** | `/accounts/.../workers/scripts/*/schedules` 전수 조회 결과 두 기존 Worker 모두 `cron_count=0` → **계정 전체 기존 Cron Trigger = `0개`** (신규 3개 추가 시 `0 + 3 = 3개` ≤ Free 상한 5개) | **`EXEC PASS`** |
| `villagecoverage-keepalive-poc` 배포 여부 / 이름 충돌 | 미배포 (`code: 10007 This Worker does not exist on your account`), 기존 2개 Worker와 이름 충돌 없음 | **`EXEC PASS`** |
| 권한 범위 | `account (read)`, `workers (write)`, `workers_scripts (write)`, `workers_tail (read)` 보유 | **`EXEC PASS`** |
| 요금제 / 결제 정보 API | `/accounts/.../subscriptions` 및 `/billing/profile`은 OAuth 토큰에 billing read 스코프가 없어 `HTTP 403` (`default_usage_model: standard`만 확인). Workers Free 여부 및 결제수단 미등록은 대시보드 확인 필요 | `NOT_VERIFIABLE` |
| 무크론 사전 배포 (Phase 7) | `--config wrangler.nocron.toml --dry-run` `PASS` (`crons = []` 확인). 실제 사전 배포는 브로커 승인 **`4769a671fc034536`** 대기 | `STATIC` (승인 대기) |

---

## 7. GitHub Actions 예약 실행 실측 집계 및 Cloudflare 전환 준비 (Phases 9 & 10)

### 7.1 집계 기간 및 `main` SHA 분리 기록 (과거 `0건` 누적값과 현행 통합 코드 분리)

| 기간 / `main` SHA 구분 | 실행 건수 (주간 / 야간) | 실제 HTTP GET 전송 | Web `HTTP 200` | API `HTTP 200` | 통합 `/api/health` `HTTP 200` | 요약 및 증거 |
|---|---|---|---|---|---|---|
| **구 `main` (`db48109`, PR #21~#24 병합 전)**<br>`2026-11-03` ~ `2026-11-09 15:02 KST` | 총 24회 (주간 12 / 야간 12) | 2회 (`41980788277`, `42344214454`) | `0건` (3회 시도 후 503 실패) | `0건` (3회 시도 후 503 실패) | `0건` | 초기 3회 재시도 한도 및 지연 도착 조기 `SKIP`(`skipped_late_schedule` 22회)으로 복구 미달. |
| **PR #21 병합 직후 (`90bd6c8`)**<br>`2026-11-10 01:03 ~ 03:28 KST` | 야간 2회 (`42650923138`, `42674363508`) | `0건` (창 밖 `skipped_window` 1회, GitHub runner 미할당 1회) | 해당 없음 (야간 창 밖) | 해당 없음 (야간 창 밖) | 해당 없음 | 야간 창 밖 요청 차단 정상 동작. |
| **신규 통합 코드 (`8ccabea` 및 최종 `main` `0b3acf3`)**<br>`2026-11-10 13:49 KST` ~ `2026-11-12 13:23 KST` | 총 **9회** (**주간 5회** / 야간 4회) | **주간 5회 전수 GET 전송** (야간 4회는 `skipped_window`로 GET 0건) | **`5건 / 5건 (100% 성공)`** | **`5건 / 5건 (100% 성공)`** | **`5건 / 5건 (100% 성공)`** | **주간 예약 실행 5건 모두 Cold Start(503)에서 HTTP 200으로 약 93.4~113.9초 만에 완벽 복구 (`EXEC PASS`)** |

#### 신규 통합 코드(`8ccabea` / `0b3acf3`) 예약 실행 9건 개별 상세 로그

1. [`42758258688`](https://github.com/JongHyun070105/village-coverage/actions/runs/42758258688) (`2026-11-10 13:49:24 KST`, `8ccabea`): Web 1~3차 `503` → **4차 `200` (`36,150ms`)**, API 1~4차 `503` → **5차 `200` (`56,731ms`)**, 통합 1차 **`200` (`459ms`)**, `outcome=complete elapsed_ms=93397` (**`EXEC PASS`**).
2. [`42772744405`](https://github.com/JongHyun070105/village-coverage/actions/runs/42772744405) (`2026-11-10 16:04:29 KST`, `0b3acf3`): Web 1~3차 `503` → **4차 `200` (`36,283ms`)**, API 1~4차 `503` → **5차 `200` (`56,570ms`)**, 통합 1차 **`200` (`516ms`)**, `outcome=complete elapsed_ms=93410` (**`EXEC PASS`**).
3. [`42845223790`](https://github.com/JongHyun070105/village-coverage/actions/runs/42845223790) (`2026-11-11 00:31:29 KST`, `0b3acf3`): `outcome=skipped_window kst=2026-11-11T00:31+09:00` (창 밖 GET 0건, **`EXEC PASS`**).
4. [`42852313908`](https://github.com/JongHyun070105/village-coverage/actions/runs/42852313908) (`2026-11-11 01:13:12 KST`, `0b3acf3`): `outcome=skipped_window kst=2026-11-11T01:13+09:00` (창 밖 GET 0건, **`EXEC PASS`**).
5. [`42950968214`](https://github.com/JongHyun070105/village-coverage/actions/runs/42950968214) (`2026-11-11 12:10:31 KST`, `0b3acf3`): Web 1~3차 `503` → **4차 `200` (`36,518ms`)**, API 1~4차 `503` → **5차 `200` (`57,459ms`)**, 통합 1차 **`200` (`600ms`)**, `outcome=complete elapsed_ms=94618` (**`EXEC PASS`**).
6. [`42969038373`](https://github.com/JongHyun070105/village-coverage/actions/runs/42969038373) (`2026-11-11 14:56:53 KST`, `0b3acf3`): Web 1~3차 `503` → **4차 `200` (`36,292ms`)**, API 1~4차 `503` → **5차 `200` (`56,616ms`)**, 통합 1차 **`200` (`591ms`)**, `outcome=complete elapsed_ms=93556` (**`EXEC PASS`**).
7. [`43034781606`](https://github.com/JongHyun070105/village-coverage/actions/runs/43034781606) (`2026-11-11 23:03:19 KST`, `0b3acf3`): `outcome=skipped_window kst=2026-11-11T23:03+09:00` (창 밖 GET 0건, **`EXEC PASS`**).
8. [`43053223540`](https://github.com/JongHyun070105/village-coverage/actions/runs/43053223540) (`2026-11-12 00:55:50 KST`, `0b3acf3`): `outcome=skipped_window kst=2026-11-12T00:55+09:00` (창 밖 GET 0건, **`EXEC PASS`**).
9. [`43154503940`](https://github.com/JongHyun070105/village-coverage/actions/runs/43154503940) (`2026-11-12 13:23:40 KST`, `0b3acf3`): Web 1~4차 `503` → **5차 `200` (`56,708ms`)**, API 1~4차 `503` → **5차 `200` (`56,641ms`)**, 통합 1차 **`200` (`459ms`)**, `outcome=complete elapsed_ms=113863` (**`EXEC PASS`**).

- **결론**: Keep-Alive 스크립트의 Cold Start 복구 로직 자체는 5연속 실환경 주간 예약 실행에서 100% 성공(`EXEC PASS`)했으나, GitHub Actions `schedule` 트리거가 하루 54개 주간 슬롯 중 1~2회만 실행되어 15분 spin-down을 방지하지 못함(`SCHEDULE_INTERVAL_VERIFIED = FAIL`). 따라서 Cloudflare Cron 전환이 필수적임.

### 7.2 스케줄러 전환 실행 및 수동 실행 보존 완료 (PHASE 7)

- **GitHub `schedule:` 블록만 제거하고 `workflow_dispatch:` 보존 (PR #26 병합 완료 — `GITHUB_SCHEDULE_REMOVED = EXEC PASS`, `GITHUB_MANUAL_DISPATCH_PRESERVED = EXEC PASS`)**:
  - 기존 승인 요청 `8ecf2e1fe9fd4190`(`gh workflow disable render-free-keepalive.yml`)은 수동 실행(`workflow_dispatch`)까지 비활성화하므로 **사용하지 않고 보류**.
  - [PR #26](https://github.com/JongHyun070105/village-coverage/pull/26)(`chore/v29-keepalive-manual-only-20261112`, HEAD `a755e5c9a1e229bc18d7625320a1cc2f87d3c529`)에 대해 브로커 승인 **`67647dc4303c4490`**(`orch-approval run 67647dc4303c4490`, `EXIT_CODE=0`)을 실행하여 `2026-11-12T05:48:56Z`에 `origin/main`으로 병합 완료 (병합 커밋: `ef99ecf732559d4daca933d1b39c9c1ea6be5632`).
  - 병합 후 `origin/main`(`ef99ecf`)에 대한 GitHub Actions CI [`43163875212`](https://github.com/JongHyun070105/village-coverage/actions/runs/43163875212) 실행 결과 `backend`(`131001088799`) 및 `frontend`(`131001088538`) 전수 **`SUCCESS`**.
  - 현재 `origin/main:.github/workflows/render-free-keepalive.yml`은 `on: workflow_dispatch:`만 유지하며, 실행 중(`in_progress`/`queued`)인 GitHub Keep-Alive 작업은 **`0건`**임을 확인.
- **Cloudflare Cron 활성화 대기**:
  - 무크론 사전 배포 승인 요청: **`4769a671fc034536`** (`wrangler.nocron.toml`, `crons = []`) — `PENDING`
  - Cron Trigger 3개 활성화 배포 승인 요청: **`5db08b1853704ad8`** (`wrangler.toml`) — `PENDING`

---

## 8. 운영 브라우저 QA 및 보안·개인정보 최종 점검 (Phases 10 & 11)

### 8.1 실제 운영 URL 브라우저 QA (`PRODUCTION_E2E_PASS = EXEC PASS`)

신규 배포 완료된 운영 URL(`https://villagecoverage-public-demo-web.onrender.com` 및 `https://villagecoverage-public-demo-api.onrender.com`, 배포 SHA `0b3acf383351b16d2a33c336f1f3c9eed7be12a3`)을 대상으로 Playwright Chromium을 실행하여 전 기능을 실측 검증함:

1. **공개 데모 15단계 종단간 방문자 여정 및 세션 격리 (`frontend/e2e/public-demo-live.spec.ts` — `1 passed (2.2m)`, `2026-11-12T05:57:32Z`)**:
   - Step 1: `/` 대시보드 진입 (`HTTP 200`, `/api/health` `196ms`, `/api/regions` `301ms`, `/api/overview` `4,386ms`), `vc_demo_session` 쿠키(`HttpOnly; Secure; SameSite=Lax; Path=/api`) 및 공개 데모 안내 배너 확인 (`01-dashboard.png`).
   - Step 2–3: `/scenarios`에서 `홍성군 장곡면` 선택 후 **4안 비교 실행** (`POST /api/schedules` 4건 `HTTP 201`, `/api/schedules/:id/explanations` 4건 `HTTP 200`, `POST /api/minimum-coverage/analysis` `HTTP 201`) 및 4개 정책 카드 렌더링 확인 (`02-scenario-compare.png`).
   - Step 4–5: `/plans`로 이동해 **계획 v1** 상세 조회 및 새로고침 후 동일 세션 계획 유지 확인 (`03-plan-v1.png`).
   - Step 6–7: `/providers/:id` 거점 화면에서 참여 가능 회차 확인 후 **데모 불참**(`POST /api/providers/:id/rounds/:id/participation` `HTTP 200`) 및 `이번 회차 불참` 상태 반영 확인 (`04-provider-decline.png`).
   - Step 8–9: `/plans`에서 `불참 1건 반영해 새 버전` 클릭(`POST /api/schedules/:id/replan` `HTTP 201`, `17,647ms`)으로 **계획 v2** 생성 후 v1↔v2 버전 전환 비교 및 새로고침 유지 확인 (`05-plan-v2.png`).
   - Step 10–13: 신규 계획 v2에 대한 Decision Memo(`GET /api/schedules/:id/decision-memo` `HTTP 200`), **회차 CSV 다운로드**(`GET /api/schedules/:id/export.csv` `HTTP 200`, `text/csv`), **검토보고서 PDF 다운로드**(`GET /api/schedules/:id/decision-memo.pdf` `HTTP 200`, `application/pdf`, `842ms`), 내보내기 후 계획 재조회 확인.
   - Step 14–15: 독립된 브라우저 컨텍스트(방문자 B)에서 별도 `vc_demo_session` 쿠키 발급 확인(`06-visitor-b-session.png`), 방문자 A의 거점 불참 상태 비노출 및 방문자 A의 계획 ID 조회 시 `HTTP 404 NOT_FOUND`(`요청한 자료를 찾을 수 없습니다.`)·빈 계획 목록(`저장된 계획이 없습니다.`) 격리 확인 (`07-visitor-b-isolation.png`).
2. **운영 `/plans` stale region 자동 복구 실측 (`EXEC PASS`)**:
   - `localStorage.setItem("villagecoverage.selectedRegionId", "pilot:removed-stale-region")` 주입 후 `https://villagecoverage-public-demo-web.onrender.com/plans` 진입 시 `/api/schedules?region_id=pilot:홍성군 장곡면`으로 즉시 교정 요청(`HTTP 200`)하고 `localStorage` 값을 `"pilot:홍성군 장곡면"`으로 갱신함을 실측 확인.
3. **운영 대시보드 지역 전환·지도 SVG·오류 복구 실측 (`EXEC PASS`)**:
   - `/`에서 `.map-canvas` 지도 SVG 렌더링 확인 후 `부여군 부여읍` 선택 시 `ROUTE_UNAVAILABLE` 안내(`도로 경로 정보가 준비되지 않아 이 지역의 계획을 계산하지 못했습니다.`) 표시 및 이전 지역 지표 숨김(`metrics_hidden_on_unavailable: true`), 다시 `홍성군 장곡면` 선택 시 `.metrics-grid` 즉시 복원(`metrics_restored_on_hongseong: true`) 확인.
4. **4개 뷰포트 × 16개 라우트 전수 반응형·레이아웃·접근성 매트릭스 (`56/56 정적 조합 + 2개 동적 라우트 전수 PASS`)**:
   - 뷰포트: `Desktop (1440×900)`, `Tablet (820×1180)`, `Mobile (390×844)`, `Small Mobile (360×780)`.
   - 공개 라우트 9개(`/`, `/region-comparison`, `/scenarios`, `/plans`, `/providers`, `/calendar`, `/data-quality`, `/evidence`, `/methodology`), 제한 라우트 5개(`/demand`, `/feedback`, `/imports`, `/pilot-imports`, `/pilot-setup` — `공개 데모 경로 제한` 배너 및 `form` 0개 확인), 동적 라우트 2개(`/villages/area-hs-janggok-doosan2`, `/providers/[id]`) 모두 `HTTP 200`, 가로 스크롤 없음(`scrollWidth <= clientWidth`), 반응형 사이드바 여백(`232px` / `68px` / `0px`), `pageerror` `0건` 확인.

| # | 라우트 경로 (`frontend/app/**/page.tsx`) | 핵심 기능 및 공개 데모 동작 계약 | 운영 LIVE(`0b3acf3`) 검증 |
|---|---|---|---|
| 1 | `/` (`page.tsx`) | 메인 대시보드, 지역 전환, 지도 SVG, Cold Start/경로 미준비 안내·복구 | **`EXEC PASS`** |
| 2 | `/region-comparison` (`region-comparison/page.tsx`) | 지역별 현황 및 비교 차트·지표 (`/api/regions/comparison`) | **`EXEC PASS`** |
| 3 | `/demand` (`demand/page.tsx`) | 공개 데모 경로 제한 안내 (`공개 데모 경로 제한`, 폼 0개) | **`EXEC PASS`** |
| 4 | `/providers` (`providers/page.tsx`) | 서비스 거점 현황 및 공급자 목록·필터 (`/api/providers`) | **`EXEC PASS`** |
| 5 | `/providers/[id]` (`providers/[id]/page.tsx`) | 개별 거점 상세·배지·회차 참여/불참 (`04-provider-decline.png`) | **`EXEC PASS`** |
| 6 | `/villages/[id]` (`villages/[id]/page.tsx`) | 마을 상세 현황 및 수요 v4 지표 (`/villages/area-hs-janggok-doosan2`) | **`EXEC PASS`** |
| 7 | `/scenarios` (`scenarios/page.tsx`) | 4가지 정책 시나리오 비교·최소보장 분석 (`02-scenario-compare.png`) | **`EXEC PASS`** |
| 8 | `/plans` (`plans/page.tsx`) | 계획 v1/v2, 불참 재계획, AI/결정론적 설명, CSV/PDF 다운로드, stale region 복구 | **`EXEC PASS`** |
| 9 | `/calendar` (`calendar/page.tsx`) | 회차별 일정 캘린더 및 실행 계획 조회 | **`EXEC PASS`** |
| 10 | `/data-quality` (`data-quality/page.tsx`) | 데이터 품질·사전(`/api/data-dictionary`)·시드 무결성 (`/api/data-quality`) | **`EXEC PASS`** |
| 11 | `/evidence` (`evidence/page.tsx`) | 정책 근거·KOSIS·농촌집수리·백테스트 지표 (`/api/evidence/*`) | **`EXEC PASS`** |
| 12 | `/methodology` (`methodology/page.tsx`) | 수리 최적화 모형 및 공정성 산식·예측 자료 부족 안내 | **`EXEC PASS`** |
| 13 | `/imports` (`imports/page.tsx`) | 공개 데모 업로드 제한 안내 (`공개 데모 경로 제한`, 폼 0개) | **`EXEC PASS`** |
| 14 | `/pilot-imports` (`pilot-imports/page.tsx`) | 파일럿 업로드 제한 안내 (`공개 데모 경로 제한`, 폼 0개) | **`EXEC PASS`** |
| 15 | `/pilot-setup` (`pilot-setup/page.tsx`) | 파일럿 설정 제한 안내 (`공개 데모 경로 제한`, 폼 0개) | **`EXEC PASS`** |
| 16 | `/feedback` (`feedback/page.tsx`) | 주민 피드백 개인정보 입력 차단 안내 (`공개 데모 경로 제한`, 폼 0개) | **`EXEC PASS`** |

### 8.2 보안 및 개인정보 14대 항목 점검 (`SECURITY_PASS = EXEC PASS`)
1. 공개 저장소 API 키 비노출: `.env` 미추적, 코드 내 하드코딩된 API 키 `0건` (`EXEC PASS`).
2. Cloudflare 토큰 비노출: 저장소·보고서 내 OAuth 토큰 및 계정 이메일 원문 미기록 (`EXEC PASS`).
3. Render 환경변수 값 비노출: `render.yaml`에 공개 설정값만 존재하며 비밀값 미포함 (`EXEC PASS`).
4. Gemini API 키 비노출: `GEMINI_API_KEY`는 런타임 환경변수로만 주입되며 코드/로그에 노출 없음 (`EXEC PASS`).
5. 개인정보 로그 비노출: `poc/cloudflare-workers-keepalive/src/index.mjs` 및 백엔드 로거에서 응답 본문·PII 미기록 (`EXEC PASS`).
6. 공개 데모 주민 입력 차단: 운영 API에서 `/api/demand/structure`, `/api/feedback/private-id/contact`, `/api/pilot-imports/provider_capacity/preview` 모두 `HTTP 404 DEMO_MODE_RESTRICTED` 반환 실측 (`EXEC PASS`).
7. CORS: 허용 Origin(`https://villagecoverage-public-demo-web.onrender.com`)에만 `access-control-allow-origin` 반환, 비허용 Origin(`https://evil.example.com`)에는 미반환 실측 (`EXEC PASS`).
8. CSRF / 쿠키 격리: `vc_demo_session` 쿠키에 `HttpOnly; Secure; SameSite=Lax; Path=/api` 적용 실측 (`EXEC PASS`).
9. 보안 헤더: 운영 Web 및 API 모두 `x-content-type-options: nosniff`, `x-frame-options: DENY`, `referrer-policy: strict-origin-when-cross-origin`, `permissions-policy: camera=(), geolocation=(), microphone=(), payment=(), usb=()`, `content-security-policy: frame-ancestors 'none'`, `strict-transport-security: max-age=31536000` 반환 실측 (`EXEC PASS`).
10. 요청 크기 및 속도 제한: `backend/request_limits.py`(`HTTP 413`) 및 세션별 레이트 리밋(`DEMO_RATE_LIMITED` `HTTP 429`) 적용 (`EXEC PASS`).
11. 민감한 에러 메시지 차단: 내부 스택트레이스 대신 구조화된 에러 코드 반환 및 `/openapi.json` `HTTP 404` 차단 실측 (`EXEC PASS`).
12. CSV Injection 방지: `backend/exports.py:26-38` `csv_safe_text()`가 `=`, `+`, `-`, `@` 선행 셀에 `'` 접두사를 부여해 수식 실행을 무력화 (`EXEC PASS`).
13. 의존성 취약점: `pip-audit` 및 `npm audit --omit=dev` 취약점 `0건` (`EXEC PASS`).
14. GitHub Actions 최소 권한: `.github/workflows/ci.yml:10` 및 `.github/workflows/render-free-keepalive.yml:8` 모두 `permissions: contents: read` 설정 (`EXEC PASS`).

---

## 9. 브로커 승인 요청 실행 이력 및 대기 목록 (PHASE 13)

| 순서 | 승인 ID | 상태 | 작업 요약 및 실행 결과 / 고정 명령 (`--plan`) |
|---|---|---|---|
| 1 | **`b70074cb2c3744e0`** | **`EXECUTED (EXIT 0)`** | **Render 운영 배포 브랜치 fast-forward 푸시 완료 (PHASE 5)**:<br>`36319c6..0b3acf3  0b3acf383351b16d2a33c336f1f3c9eed7be12a3 -> submission/public-demo-deploy` |
| 2 | **`67647dc4303c4490`** | **`EXECUTED (EXIT 0)`** | **GitHub `schedule:` 블록만 제거하는 PR #26 병합 완료 (PHASE 7)**:<br>PR #26(`a755e5c`) → `main`(`ef99ecf732559d4daca933d1b39c9c1ea6be5632`) 병합 및 CI `43163875212` `SUCCESS` |
| 3 | **`a555dc055802433f`** | **`EXECUTED (EXIT 1)`** | 이전 보고서 푸시 시도 시 루트 작업 디렉터리의 `HEAD`(`ce3bc40`)가 참조되어 `! [rejected] HEAD -> docs/v26-release-gate-20261109 (non-fast-forward)`로 안전 거절됨 (`-C .worktrees/v26-report-20261109` 및 명시적 커밋 SHA로 신규 승인 요청 등록) |
| 4 | **`a3c60e9e49a841f9`** | `PENDING` | **PR #25 병합 (PHASE 2)**:<br>`gh pr merge 25 --merge --match-head-commit a8a1e8653282625e0ae2022779f5d5bbc62c2aaa` |
| 5 | **`4769a671fc034536`** | `PENDING` | **Cloudflare Worker 무크론 사전 배포 (PHASE 6)**:<br>`/Users/jonghyun/Library/Caches/ai-orchestrator/de1ed531efc22953dbc193f2/tools/wrangler-v26/node_modules/.bin/wrangler deploy --cwd /Users/jonghyun/Projects/village-coverage/.worktrees/v27-1-cf-observability/poc/cloudflare-workers-keepalive --config wrangler.nocron.toml` |
| 6 | **`5db08b1853704ad8`** | `PENDING` | **Cloudflare Worker Cron Trigger 3개 활성화 배포 (PHASE 8)**:<br>`/Users/jonghyun/Library/Caches/ai-orchestrator/de1ed531efc22953dbc193f2/tools/wrangler-v26/node_modules/.bin/wrangler deploy --cwd /Users/jonghyun/Projects/village-coverage/.worktrees/v27-1-cf-observability/poc/cloudflare-workers-keepalive --config wrangler.toml` |
| — | `8ecf2e1fe9fd4190` | 미사용 보류 | `gh workflow disable render-free-keepalive.yml` (PR #26 병합 완료로 대체됨) |

---

## 10. 운영 롤백 계획

1. **Render 배포 롤백**:
   - 배포 후 헬스체크 또는 핵심 기능 장애 발생 시 Render Dashboard에서 직전 검증 커밋(`36319c6551b5c80d3f8c4e1aaa43bc7bbf8fe6e3`) 빌드로 즉시 Rollback하거나, 승인 하에 revert 커밋을 `submission/public-demo-deploy`에 forward push(force push 금지).
   - **주의**: Rollback 역시 컨테이너 재기동을 수반하므로 `/tmp/villagecoverage-public-demo.sqlite`의 임시 방문자 기록은 초기화되고 기본 시드 데이터만 복원됨.
2. **Cloudflare Cron 전환 롤백**:
   - ① `wrangler deploy --config wrangler.nocron.toml` 실행으로 배포된 Cron Trigger 3개를 즉시 제거(`crons = []`).
   - ② 설정 전파(최대 15분) 및 진행 중인 Worker 실행 종료, Cron Trigger `0개` 상태를 API로 재확인.
   - ③ `schedule:` 블록 복원 PR을 통해 GitHub 스케줄러 재활성화 후 HTTP 응답 검증.
   - 롤백 과정에서도 두 스케줄러가 동시에 활성화되지 않도록 순서를 엄격히 유지함.

---

## 11. 최종 완료 판정표 (PHASE 14 — 16개 필수 항목)

| 항목 | 등급 | 근거 요약 |
|---|---|---|
| `PR25_CI_PASS` | **`EXEC PASS`** | PR #25(`a8a1e86`) CI [`43048635235`](https://github.com/JongHyun070105/village-coverage/actions/runs/43048635235) Attempt 3 `backend`(`130972427305`)·`frontend`(`130972425216`) 전수 `SUCCESS` 및 POC 테스트 `16/16 PASS`. |
| `PR25_MERGED` | **`SKIP`** | 10대 조건 및 CI `SUCCESS` 완료; 브로커 승인 **`a3c60e9e49a841f9`** 대기 중. |
| `FINAL_MAIN_CI_PASS` | **`EXEC PASS`** | `origin/main` PR #24 병합(`0b3acf3`, CI [`42761296270`](https://github.com/JongHyun070105/village-coverage/actions/runs/42761296270)) 및 PR #26 병합(`ef99ecf`, CI [`43163875212`](https://github.com/JongHyun070105/village-coverage/actions/runs/43163875212)) 모두 `backend`·`frontend` 전수 `SUCCESS`. |
| `SQLITE_POLICY_A` | **`EXEC PASS`** | 사용자 옵션 A 명시적 확정 및 반영 완료 (`/tmp/villagecoverage-public-demo.sqlite`, 30분 세션 TTL, PII 입력 차단, 시드 자동 복원, UI 안내 유지). |
| `RENDER_DEPLOYED` | **`EXEC PASS`** | 브로커 승인 **`b70074cb2c3744e0`** 실행으로 `0b3acf3`을 `submission/public-demo-deploy`에 푸시 완료; Web(`rndr-id: bca092cd-ddff-47ed`) 및 API(`rndr-id: c8a6b323-9e08-40c2`) 모두 신규 빌드·보안 헤더 반영 LIVE 확인 (`2026-11-12 14:51 KST`). |
| `RENDER_HEALTH_PASS` | **`EXEC PASS`** | 신규 배포 LIVE 후 Web `/`(`HTTP 200`), API `/health`(`HTTP 200`), 통합 `/api/health`(`HTTP 200`, `road_routes_cached=2916, road_route_origins=54`) 및 주간 예약 실행 5건 전수 `HTTP 200` 확인. |
| `CLOUDFLARE_WORKER_DEPLOYED` | **`SKIP`** | 무크론 사전 배포 승인 **`4769a671fc034536`** 대기 중 (`--dry-run` 및 계정 Cron `0개` 검증 완료). |
| `GITHUB_SCHEDULE_REMOVED` | **`EXEC PASS`** | 브로커 승인 **`67647dc4303c4490`** 실행으로 [PR #26](https://github.com/JongHyun070105/village-coverage/pull/26)(`a755e5c`)이 `origin/main`(`ef99ecf`)에 병합 완료되어 `schedule:` 블록 제거 및 실행 중 job `0건` 확인. |
| `GITHUB_MANUAL_DISPATCH_PRESERVED` | **`EXEC PASS`** | `origin/main`(`ef99ecf`)의 `.github/workflows/render-free-keepalive.yml`에 `on: workflow_dispatch:` 및 `.github/scripts/render_keepalive.py` 보존 확인. |
| `CLOUDFLARE_CRON_ACTIVE` | **`SKIP`** | Cron Trigger 3개 활성화 배포 승인 **`5db08b1853704ad8`** 대기 중. |
| `CLOUDFLARE_HTTP_200` | **`SKIP`** | Cloudflare Worker 배포 승인 대기 중이므로 실제 Cloudflare 예약 GET `0건`. |
| `SCHEDULE_INTERVAL_VERIFIED` | **`FAIL`** | GitHub Actions `schedule`은 일 1~2회만 실행되어 10분 간격 유지 실패(`schedule:` 제거 완료); Cloudflare Cron 활성화(`5db08b1853704ad8`) 후 10분 주기 실측 예정. |
| `PRODUCTION_E2E_PASS` | **`EXEC PASS`** | 신규 LIVE 배포된 운영 사이트(`0b3acf3`)에서 `public-demo-live.spec.ts` 15단계 전체 여정(`1 passed (2.2m)`), `/plans` stale region 자동 복구, 지역 전환·지도 SVG·오류 복구, 4개 뷰포트×14개 정적 라우트(`56/56 PASS`) 및 동적 라우트 2개, API 계약 19건 전수 통과. |
| `SECURITY_PASS` | **`EXEC PASS`** | 운영 LIVE 보안 헤더 6종, CORS 오리진 제한, 세션 쿠키 격리(`HttpOnly; Secure; SameSite=Lax`), 운영 PII 차단(`HTTP 404 DEMO_MODE_RESTRICTED`), 의존성 감사(`npm audit`, `pip-audit`) 등 14대 항목 전수 통과. |
| `PRIMARY_CHECKOUT_PRESERVED` | **`EXEC PASS`** | `/Users/jonghyun/Projects/village-coverage` (`fix/demand-negation-20261029` @ `ce3bc40`) 및 기존 dirty 파일 65건 무변경 보존. |
| `FINAL_REPORT_PUBLISHED` | **`STATIC`** | `.worktrees/v26-report-20261109/V29_FINAL_PRODUCTION_RELEASE_HANDOFF.md` 최신 결과 반영 및 커밋 완료 (원격 브랜치 푸시는 브로커 승인 대기). |
