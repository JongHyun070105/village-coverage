# VillageCoverage v26 — Release Gate and Scheduler Cutover Report

작성: 2026-11-09 KST 약 14:40–15:30. 증거 등급: **EXEC PASS**(이번 작업에서 실행), **STATIC**(코드·문서 읽기만), **SKIP**, **FAIL**, **NOT_VERIFIABLE**.
이전 보고서(V21/V23/V24.2/V25)는 변경하지 않았습니다. **병합, 배포, Cloudflare 변경, GitHub schedule 비활성화는 하나도 실행하지 않았습니다.**

## 0. 한 문단 결론

v25 브랜치로 스택 PR **#23**을 만들었고(base = PR #22 브랜치, 변경 파일 2개뿐), `main + #21 + #22 + #23` 조합은 **충돌 없이 병합**됩니다. 통합 head `15b87a8`은 v25에서 전체 테스트를 통과한 `7979253`+`55aa4cb`에 보고서 하나를 더한 트리입니다. GitHub Actions 기록을 다시 집계해도 v25와 숫자가 같고(예약 run 23건, 예약 실행의 HTTP 200 **0건**), PR #21/#22는 코드 결함 두 가지만 고치며 **GitHub의 예약 전달 부족은 코드로 고칠 수 없습니다.** Cloudflare Worker POC는 이번에 **실제 workerd 런타임(wrangler 4.158.0, 로컬)**에서 cold 상태의 Render를 92.6초 만에 복구했습니다. 이것은 런타임 호환성의 증거이고 Cloudflare의 **Cron 전달 신뢰성**은 여전히 NOT_VERIFIABLE입니다. 추가로 Gemini 무제한 대기(P2)를 재현해 수정했습니다(별도 브랜치, push 승인 대기). 배포는 **SQLite 손실 수용 결정**과 병합 승인 전까지 보류합니다. **독립 교차 리뷰는 얻지 못했고 이 보고서는 MAIN 단독 검증입니다.**

## 1. 작업 요약

| 항목 | 내용 |
|---|---|
| Primary checkout | `fix/demand-negation-20261029` @ `ce3bc40`, 기존 수정·미추적 파일 그대로. 이번 작업에서 수정하지 않음 |
| 사용한 worktree | `.worktrees/v25-readiness-20261109`(읽기·테스트만), `.worktrees/v26-gemini-timeout-20261109`(수정), `.worktrees/v26-report-20261109`(이 보고서) |
| 새 PR | **#23** `[V25] Add cold-start regression matrix and production QA evidence` (base `fix/v24.2-coldstart-retry-20261104`) |
| 코드 변경 | `backend/demand.py` +5, `tests/test_demand.py` +27 (커밋 `585c8d3`, 브랜치 `fix/v26-gemini-timeout-20261109`, **원격 push는 승인 대기** — approval `b4ff2e4355ea4c6e`) |
| 외부 설치 | wrangler 4.158.0을 저장소 밖 툴 캐시에만 설치. Cloudflare 계정 접속·토큰 사용 없음 |
| 독립 리뷰 | **미확보.** `orch-parallel`과 `orch-delegate`(깨끗한 worktree에서 재시도) 모두 `SNAPSHOT_FILE_COUNT_LIMIT` 감독자 오류로 출력 전에 실패. 한도를 우회하지 않음 |

## 2. PR 통합 준비

| PR | Head | Base | 변경 | 자동 CI | Mergeable |
|---|---|---|---|---|---|
| #21 | `819fcce` | `main` | 5개 파일 +96/−58 | backend, frontend **success** (run 41607333440) | MERGEABLE / CLEAN |
| #22 | `7979253` | #21 브랜치 | 8개 파일 (#21 이후 변경만) | **없음**(base가 main 아님) | MERGEABLE / CLEAN |
| #23 | `15b87a8` | #22 브랜치 | 2개 파일 +312 (`tests/test_render_keepalive.py`, V25 보고서) | **없음**(base가 main 아님) | MERGEABLE / CLEAN |

- 원격 v25 HEAD는 `15b87a8`, `55aa4cb`는 조상, V25 보고서 포함. 예상 밖 파일 없음, #21/#22와 중복 diff 없음 (EXEC PASS).
- 병합 시뮬레이션: `git merge-tree --write-tree origin/main origin/fix/v25-readiness-20261109` → 충돌 없음, 결과 트리 `7f5b353` (EXEC PASS). `main..v25` 커밋은 7개(#21 1, #22 4, v25 2)이며 main은 `db48109` 그대로.
- **통합 head CI 공백 보강:** `gh workflow run CI --ref fix/v25-readiness-20261109`로 head `15b87a8`에서 CI를 직접 실행 — run 42569948191: **backend·frontend 모두 success** (EXEC PASS).
- 통합 트리 검증: `ruff check backend scripts tests` 통과, 스케줄러 테스트 30 passed, Cloudflare POC 12/12 (이번에 재실행). v25가 `7979253`+`55aa4cb`에서 실행한 전체 결과(backend 751 passed/1 skipped, R1–R13 113, Playwright 24+16, 반응형 5, npm audit/pip-audit 0)는 코드가 동일하므로 재실행하지 않고 인용합니다.

**병합 방식 주의:** 반드시 **merge commit**(저장소 기존 이력도 `Merge pull request #N`)으로 병합하세요. #21을 squash하면 #22가 #21의 커밋을 중복으로 들고 있어 base 변경 후 diff가 부풀거나 충돌합니다.

## 3. Scheduler

### 3.1 GitHub schedule 재집계 (2026-11-03 15:26Z → 11-09 03:03Z, 5.48일)
v25 이후 새 run은 **없음**(마지막 12:03 KST). 현재 시각 기준 업무시간 중 2시간 40분 넘게 예약 run이 없었습니다.

| 지표 | 값 |
|---|---|
| run 총수 | 24 (schedule 23, workflow_dispatch 1) |
| cron 슬롯 | 하루 54개(1 + 48 + 5) × 5.48일 ≈ 296 → 생성 23건 ≈ **7.8%** |
| 결과 분류 | `skipped_late_schedule` 21 (GET 0건), `http_failed` 3 (GET 각 9건) |
| GET 전송 / HTTP 200 / HTTP 503 | 27 / **0** / 27 |
| 업무시간(08:55–18:00 KST) 예약 run | 11건. 같은 날 연속 간격 158, 163, 161, 150, 184분 (목표 10분) |
| 코드 | 모든 예약 run이 `main`@`db48109`를 체크아웃 (schedule은 기본 브랜치에서만 실행) |

구분: (1) **코드 결함** — main의 지연 판정이 슬롯 간 시간을 "지연"으로 오인해 21건을 요청 0건으로 SKIP(그러면서 녹색). (2) **재시도 창 부족** — 3회/약 35초, 실측 cold start는 약 53–100초. (3) **전달 부족** — 기대 대비 약 8%만 run 생성. 생성되지 않은 슬롯이 "지연"인지 "유실"인지는 API(run 생성 시각만 제공)로 구분할 수 없으므로 **유실로 단정하지 않습니다.** GitHub 문서는 예약 이벤트가 부하 시 지연되거나 큐에서 유실될 수 있다고 설명합니다.

| | #21 + #22가 해결 | 해결하지 못함 |
|---|---|---|
| 오판 SKIP | ✅ (#21) | |
| 35초 재시도 창 | ✅ 최대 16회 / endpoint 4분 / run 8분 (#22) | |
| schedule 이벤트가 거의 안 만들어지는 문제 | | ❌ GitHub 측 문제 |
| 이벤트 도착 시각의 불규칙 | | ❌ |

→ **#21/#22 병합만으로 10분 간격 keep-alive는 완성되지 않습니다.**

### 3.2 Cold Start 복구 증거 (재사용)
- v25 실측: 실제 cold Render에 #22 스크립트 로컬 실행 → 93.7초, Web/API/통합 200, exit 0. (**1회 실측이며 GitHub 전달 신뢰성의 증거가 아님**)
- v25 합성 매트릭스(#23, 5건): Web/API 5/5, 5/60, 40/90, 5/180, 90/5, 60/150초 × 502/503/504, timeout/DNS/TLS/reset, 영구 장애 ≤8분·≤16요청, 17:59 시작은 18:00 이후 0요청, 18:00 시작은 0요청. 이번에 스케줄러 테스트 30 passed 재확인.
- 429/Retry-After, HTML 200 대기 페이지, 잘못된 JSON, 리디렉션 미추적, URL allow-list는 기존 테스트가 다룸. GitHub 15분 job timeout은 run 상한 8분이라 초과 경로 없음(STATIC).
- 이번에 새 결함은 재현되지 않아 스크립트는 수정하지 않았습니다.

### 3.3 Cloudflare Workers Cron — 공식 문서 재확인 (2026-11-09 조회)
| 항목 | 값 (출처 페이지 최종 수정일) | v25 값과 |
|---|---|---|
| Free 요청 | 100,000/일, UTC 자정 리셋, 초과 시 Error 1027 ([limits](https://developers.cloudflare.com/workers/platform/limits/), 10-29) | 동일 |
| CPU | Free 10 ms/invocation (HTTP·Cron 동일). **fetch 네트워크 대기는 CPU에 포함되지 않음** | 동일 |
| Subrequest | Free 50 / Paid 10,000 | 동일 |
| Cron Trigger | Free **5개**/계정, Paid 250 | 동일 |
| Cron wall-clock | 15분/invocation (플랜별 구분 없음) | 동일 |
| 시간대 | **UTC만** ([cron-triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/), 10-17) | 동일 |
| 설정 전파 | 추가·수정·삭제 후 **최대 15분** | 동일 |
| 전달 지연/보장 | **문서에 기재 없음.** "underutilized machines에서 실행" 문구만 있음 | — |
| 로컬 테스트 | `/cdn-cgi/local/scheduled?cron=…` (이전의 `--test-scheduled`/`/cdn-cgi/handler/scheduled` 아님) | **변경됨** |
| 로그 | Free: 일 200,000 이벤트, **3일 보존**. Cron Events 대시보드는 최근 100건. 2026-12-01부터 Observability 요금제로 전환 예고 ([workers-logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/), 10-12) | 신규 |
| 비용 | Free $0 (Paid 최소 $5/월). 이 용도는 Free 한도의 약 0.05% (54회/일) | — |
| 권한 | "Workers Scripts Edit" 등재(검증). **Cron Trigger 설정에 필요한 권한은 문서에 명시 없음 — Workers Scripts Edit로 충분한지는 추론(UNVERIFIED)** | — |
| 비밀정보 | 이 Worker는 비밀정보 불필요(URL 3개 하드코딩). 배포 토큰은 저장소에 저장하지 않음 | — |

### 3.4 POC 감사 (`poc/cloudflare-workers-keepalive/`)
| 점검 | 결과 | 등급 |
|---|---|---|
| cron의 UTC→KST | `55 23`=08:55 KST, `5,15,…,55 0-7`=09:05–16:55, `5,…,45 8`=17:05–17:45 KST. 하루 54개, 업무창과 일치 | EXEC PASS(계산) |
| 18:00 이후 요청 금지 | 시작·재시도 직전 KST 시각 검사, 재시도 지연이 18:00을 넘으면 중단 | EXEC PASS(테스트 12/12) |
| URL allow-list / GET 전용 / 리디렉션 | URL 3개만, `method:"GET"`, `redirect:"manual"` | STATIC + 테스트 |
| 허용 외 cron | **실제 workerd에서** `invalid_schedule` 예외(HTTP 500) | EXEC PASS |
| fetch 핸들러 | **실제 workerd에서** GET `/` → 404 | EXEC PASS |
| 한도 | 최악 호출 수 16×3=48 ≤ subrequest 50, run 상한 8분 < 15분 | STATIC |
| 로그 정확성 | 예정 시각(`scheduled_at`)과 시작 시각(`started_at`), 지연초를 구분해 기록. 비밀정보·응답 본문 미기록 | EXEC PASS |
| **실제 런타임 실행** | wrangler 4.158.0 / workerd 1.20261104.1, `wrangler dev --local`, 14:48 KST, **실제 Render GET**. cold 상태에서 web: timeout→503→503→200(4번째, 46.1초), api: 503→503→timeout→200(4번째, 46.1초), 통합 health 200(1번째). 총 92.6초, `outcome:"ok"`, `Retry-After` 반영 | **EXEC PASS** |
| 사소한 결함(미수정) | ① `body === null` 검사는 도달 불가(`body_too_large` 미발생, 대신 4KB로 절단). ② `invalid_schedule` 예외 메시지가 "0 failed endpoint(s)"로 표시. 둘 다 동작에 영향 없음 | P3 |
| **증명되지 않은 것** | Cloudflare 실제 에지에서의 Cron **전달 지연·누락률**, Render 쪽이 Cloudflare 에지 IP를 막는지, 로그 보존의 실사용, 계정의 Free 여부와 기존 Cron 점유 수 | NOT_VERIFIABLE |

로컬 실행의 `scheduled_delay_seconds=0`은 수동 호출 값이며 Cloudflare의 실제 전달 지연이 아닙니다. 이번 실행으로 Worker가 **이벤트를 받기만 하면** 올바르게 동작함을 확인했을 뿐, 이벤트가 제시간에 오는지는 배포 후 실측해야 합니다.

### 3.5 전략 비교
| 기준 | A. GitHub Actions 유지 | B. Cloudflare Workers Cron 단독 | C. 다른 무료 스케줄러(cron-job.org / UptimeRobot) |
|---|---|---|---|
| 실행 신뢰성 | **실측 7.8% 생성**, 200 성공 0 | 가설. 문서상 보장 없음, 실측 0 | 가설. cron-job.org는 "punctuality 보장 불가" 명시 |
| 정확한 운영 시간 | cron으로 가능하나 전달이 불규칙 | UTC cron으로 정확히 표현 가능(검증) | cron-job.org: timezone 필드 있음(Asia/Seoul 명시는 못 찾음). UptimeRobot Free: 5분 간격, **시간대별 활성 창 기능은 확인 못 함** → 18:00 이후 요청 차단을 보장하기 어려움 |
| 무료 | ✅ | ✅ $0, 한도의 0.05% | ✅ (cron-job.org 무료, UptimeRobot Free 50 monitors) |
| 실측 가능성 | run 목록 API | Cron Events 100건 + Workers Logs 3일 + 자체 구조화 로그 | cron-job.org 최근 50회·응답 2일 보존 |
| 보안 | 토큰 없음, `contents: read` | 코드로 URL·메서드 고정. 배포 토큰 필요 | 외부 서비스가 임의 URL 호출 설정(코드 검증 불가), 재시도 로직 없음(cron-job.org 30초 timeout) |
| 유지보수 | 기존 | wrangler 배포 1회 + 토큰 관리 | 대시보드 설정 |
| Cold Start 재시도 | #22 스크립트(검증됨) | POC(검증됨) | **없음.** 단발 GET이라 cold start 중에는 503이어도 다음 ping까지 방치 |
| 중복 ping 위험 | — | GitHub와 동시 가동 시 2배 → 전환 절차로 차단 | 동시 가동 시 2배 |
| 기존 URL 유지 | ✅ | ✅ (Cloudflare는 호스팅 안 함) | ✅ |
| 벤더 정책 변경 | GitHub 예약 정책 | Free 한도·로그 정책(2026-12-01 로그 요금 개편 예고) | 무료 정책·fair use |

**권고:** B를 우선 실증하되 **"더 안정적"은 가설**입니다. C는 재시도·18:00 차단을 직접 구현하지 못해 현재 요구에 덜 맞습니다. 여러 서비스를 동시에 설치하지 않습니다.

### 3.6 Cloudflare 전환 계획 (승인 후에만, 이번에는 실행하지 않음)
1. **계정 확인:** Free 플랜 여부, 기존 Cron Trigger 점유 수(필요 3 ≤ 남은 슬롯, 총 5). 부족하면 중단.
2. **권한:** 이 Worker 전용 API 토큰(Account scope, Workers Scripts Edit만). 저장소·채팅에 토큰을 남기지 않음. Cron 설정 권한은 배포 시 실패 여부로 확인(문서에 명시 없음).
3. **코드 검증:** `node --test`(12/12) + `wrangler dev --local` 재실행(이번에 수행).
4. **GitHub schedule 비활성화:** `schedule:` 블록을 제거하는 PR(워크플로 `workflow_dispatch`는 유지). `gh workflow disable`은 수동 실행까지 막으므로 쓰지 않음. 비활성화 시점이 Cloudflare 활성화보다 **먼저**여야 이중 ping이 없음.
5. **대기 중 run 확인:** `gh run list --workflow … --status in_progress,queued`가 비었는지 확인.
6. **배포:** `wrangler deploy`(3개 cron). **전파 최대 15분** → 이 구간과 4~5단계 사이에 ping 공백이 생길 수 있음. GitHub 예약이 하루 약 2회뿐이어서 공백으로 잃는 실제 ping은 적음. 공백 시작/종료 시각을 기록.
7. **Cron Event 관측:** 대시보드 Cron Events와 Worker 로그의 `scheduled_start`에서 `scheduled_delay_seconds`를 수집.
8. **Render 200 확인:** `/health`, `/`, `/api/health`를 GET으로 확인.
9. **운영 시간대 반복 검증(≥3 영업일):** 합격 기준 — 54슬롯 중 시작 **≥95%**, 지연 5분 이내 비율 기록, **18:00 KST 이후 요청 0건**, 슬롯마다 Web/API 200. Workers Logs는 3일만 보존하므로 매일 내보내기.
10. **미달 시 중단**하고 기준 미달 근거를 기록.
11. **롤백:** 배포 취소(`wrangler delete`) 또는 `crons = []`로 재배포(키 주석 처리로는 비활성화되지 않음, 전파 최대 15분) → GitHub `schedule:` 복원 PR 병합. 롤백 중에도 이중 가동 금지.

## 4. Render

| 항목 | 값 | 등급 |
|---|---|---|
| deploy 브랜치 `submission/public-demo-deploy` | `36319c6` (main의 조상, **18 커밋 뒤**) | EXEC PASS |
| Web / API / 통합 health | 14:52 KST 모두 HTTP 200 (`{"status":"ok"}`, `demo_data_available:true`) | EXEC PASS |
| LIVE ≠ main 증거 | API 응답에 `x-frame-options`, `permissions-policy` 없음 (main의 SecurityHeadersMiddleware가 추가) | EXEC PASS |
| LIVE SHA | Render 대시보드는 읽을 수 없음. 브랜치 SHA로 추정 | NOT_VERIFIABLE |
| LIVE→main 차이 | 46개 파일: 보안 헤더·authz·request limits, Gemini/demand 파싱, 대시보드 hydration, 세션, keep-alive 스크립트, 테스트. **DB 마이그레이션·의존성·`render.yaml`·환경변수·시작 명령 변경 없음** (`database.py`는 `commit` 인자, `public_demo.py`는 `asyncio.to_thread`뿐) | EXEC PASS |
| 시작 명령 | API `uv run --no-sync uvicorn backend.main:app … --workers 1`, Web `node .next/standalone/server.js` | STATIC |
| Free 플랜 | spin-down 15분, 워크스페이스당 월 750 instance hours ([render.com/docs/free](https://render.com/docs/free)). 이 문서는 인바운드 ping 금지를 명시하지 않음. 업무창 keep-alive 추정 ≈ 545h/월(2개 서비스) | STATIC / 추정 |

### SQLite — 선택지 비교
공개 데모 DB는 `tempfile.gettempdir()/villagecoverage-public-demo.sqlite`(`render.yaml`에 디스크 없음)이므로 재시작·spin-down·재배포 시 방문자가 만든 세션·계획·승인 기록은 사라집니다. 시드 데이터는 재생성됩니다. keep-alive는 spin-down 손실을 줄일 뿐 영속성이 아닙니다.

| | A. 시연 전용 임시 데이터 | B. 외부 영속 저장소 |
|---|---|---|
| 작업량 | 안내 문구 확인, 실제 주민 데이터 입력 금지 고지 | SQLite 전용 코드(PRAGMA user_version, 스키마·마이그레이션) 이식, 이전·백업·복구 설계 |
| 위험 | 기록 손실(합성 데이터라 영향 작음) | 마이그레이션 회귀, 개인정보 보관 책임, 무료 한도·만료 정책(**이번에 조사하지 않음**) |
| API 호환 | 변경 없음 | 변경 필요 |
| 공모전 데모 적합성 | **높음** | 제출 전 도입은 위험이 이득보다 큼 |

**권고: A.** 단, 배포는 "방문자 기록이 배포·재시작 때 사라진다"는 수용을 **명시 승인**한 뒤에만 진행합니다. 이번에 기존 DB는 변경하지 않았습니다.

### 배포 계획 (승인 후)
- 사전: 병합 후 main CI 성공 SHA 확정 → 환경변수/시작 명령 변경 없음 확인(위 표) → 손실 수용 확인.
- 실행: `submission/public-demo-deploy`는 main의 조상이므로 **fast-forward push**(`git push origin <승인된 main SHA>:submission/public-demo-deploy`)로 가능. **force push 불필요.** Web/API AutoDeploy로 두 서비스가 재배포되며 임시 SQLite가 초기화됩니다.
- 검증: `/health`·`/`·`/api/health` 200(cold 복구 약 100초 예상), 16개 페이지 읽기 전용 순회, 보안 헤더 확인. 운영 DB 쓰기 테스트는 별도 동의 없이 하지 않음.
- 롤백: 이전 SHA로의 되돌림은 non-fast-forward이므로 `git revert` 커밋을 push하거나 Render 대시보드의 이전 배포 재배포를 사용(대시보드 기능은 이번에 확인하지 못함). force push는 별도 승인.

## 5. QA

| 영역 | 결과 | 등급 |
|---|---|---|
| Backend 전체 pytest | `fix/v26-gemini-timeout`(= main + 수정): **746 passed, 1 skipped**(7분 14초). 통합 스택은 v25 실측 751 passed/1 skipped 인용 | EXEC PASS |
| 수정 범위 | `tests/test_demand.py` 109 passed(신규 1건 포함). 신규 테스트는 수정 없이 `KeyError: 'http_options'`로 **실패**, 수정 후 통과 | EXEC PASS |
| Ruff (CI 범위) | `ruff check backend scripts tests` 통과 | EXEC PASS |
| R1–R13, Playwright, 반응형, 프런트엔드 | v25에서 동일 코드로 통과(113 / 24+16 / 5 / lint·unit 19·tsc·build) — 재실행 안 함 | 인용 |
| 브라우저(LIVE) | v25: 16페이지×4뷰포트=64회 200, overflow·콘솔 오류·spinner 0, GET 외 요청 0. 이번에 재실행하지 않음(코드 미변경) | 인용 |
| 의존성 보안 | v25: npm audit / pip-audit 0건 | 인용 |
| 스케줄러 | 30 passed, POC 12/12, workerd 실행 1회 | EXEC PASS |
| 개인정보·Gemini | 업로드 텍스트는 PII 마스킹 후, 마스킹이 걸리면 로컬 경로. Gemini에는 후보 service_type ID만 전송(주민 원문 미전송). **실제 Gemini 호출은 실행하지 않음** | STATIC |
| 보안(쿠키/CORS/CSRF fuzz, 에러 누출, CSV injection, load) | 이번 작업 범위에서 새로 실행하지 않음. v25는 코드 검토만 | SKIP / STATIC |
| Actions 권한 | CI `contents: read`, keep-alive도 읽기 전용 | STATIC |
| 성능 | v25: LIVE 순회 median 1.3초/p95 5.0초(부하 시험 아님). 이번 작업에서 부하·P95 시험 없음 | 인용 |

## 6. 남은 결함

| 등급 | 항목 | 재현 | 상태 |
|---|---|---|---|
| **P2** | Gemini 호출에 timeout이 없음. SDK 1.75.0 기본값이 `None`→무제한 | **재현됨**: 응답 않는 로컬 소켓에서 12초 넘게 블록, `timeout=3000`이면 3.0초 후 `ReadTimeout`. 영향: 비데모(non-public) 환경에서 `/api/demand` 요청이 threadpool 스레드를 무한 점유. 공개 데모는 해당 endpoint를 차단 | **수정함**(요청 단위 10초, 기존 fallback 사용). 브랜치 `fix/v26-gemini-timeout-20261109`@`585c8d3`, **push·PR은 승인 대기** |
| P3 | 요약 PDF ₩3,841,685 vs 메모 PDF 하한 ₩3,841,690 (5원) | 코드로 원인 확인: 최적화기는 구간(leg)별 올림 합, 메모는 round 단위 구성요소별 올림 합. `travel_reconciliation_residual_won`으로 계산되고 `docs/OPTIMIZATION_MODEL.md`가 "숨기지 않고 보고, 데모 플랜 1원"이라 명시 | **설계된 반올림 차이이며 계산 오류 아님.** 수정하지 않음. 5원 규모의 표기 일치가 필요하면 메모에 잔차를 표기하는 별도 변경 |
| P3 | `ruff check .`가 `submission/final-draft/build_submission_package.py`에서 실패 | KEIT 제출 문서(PPTX/DOCX)를 만드는 일회성 생성기. 앱·CI와 무관 | 수정하지 않음. CI 범위(`backend scripts tests`)는 올바름 |
| P3 | POC 사소한 결함 2건(§3.4) | 코드 확인 | 미수정, 영향 없음 |
| P1(운영) | GitHub schedule 전달 부족 | 실측 7.8%, 예약 200 성공 0 | 코드로 해결 불가 → Cloudflare 실증(승인 필요) |
| P1(운영) | LIVE가 main보다 18커밋 뒤(보안 헤더 등 누락) | 헤더로 확인 | 배포 승인 필요 |
| P2(운영) | 방문자 기록의 비영속 | 구조상 | 정책 결정 필요 |

P0는 발견하지 못했습니다.

## 7. 승인 게이트 (각각 독립)

1. **PR #21 병합.** 정확한 head `819fcce`, CI success(run 41607333440), merge commit 방식. 병합 후 main CI 확인. 영향: 코드만, 운영 서비스는 배포 전까지 불변.
2. **PR #22 병합.** #21 병합 후 `gh pr edit 22 --base main`, 변경 8개 파일만 보이는지 확인, 새로 생기는 자동 CI 성공 확인 후 head `7979253`에서 병합.
3. **PR #23 병합.** #22 병합 후 base를 main으로 바꾸고 2개 파일만 남는지 확인 후 head `15b87a8` 병합. (수동 CI run 42569948191 success)
4. **Gemini timeout 브랜치 push + PR.** approval `b4ff2e4355ea4c6e` 대기 중. main에 영향 없는 새 브랜치 push.
5. **Cloudflare Cron 전환.** §3.6의 1~11단계. 필요한 것: Cloudflare 계정 Free 여부·Cron 슬롯 확인, 전용 토큰, GitHub `schedule:` 제거 PR 병합. 이중 가동 금지.
6. **SQLite 손실 수용 또는 영속 저장소 도입.** 권고는 A(임시 데이터 정책 수용).
7. **Render 배포.** 위 1–3 병합과 6번 결정 후, 승인된 main SHA를 fast-forward push. AutoDeploy가 켜져 있어 push가 곧 운영 배포이며 임시 DB가 초기화됩니다.
8. **공모전 자료 외부 제출.** 이번 작업에서 다루지 않음.

## 8. 최종 판정

| 판정 | 상태 | 등급 |
|---|---|---|
| CODE_VERIFIED | 통합 스택(`15b87a8` 트리) 테스트는 v25 전체 실행 + 이번 스케줄러/POC 재실행 | EXEC PASS |
| CI_VERIFIED | #21 head 자동 CI success. 통합 head는 수동 CI run 42569948191 backend·frontend success | EXEC PASS |
| STACKED_PRS_READY | #21→#22→#23 모두 MERGEABLE/CLEAN, main과 충돌 없음 | EXEC PASS |
| MAIN_INTEGRATED | 병합 안 함 | FAIL (미실행, 승인 대기) |
| SCHEDULER_ACTIVE | 워크플로 active | EXEC PASS |
| SCHEDULER_EXEC_PASS | 예약 run 중 HTTP 200 0건 | **FAIL** |
| CLOUDFLARE_POC_VERIFIED | 로컬 workerd에서 실행·200·복구 확인. 전달 신뢰성 미확인 | EXEC PASS(런타임) / NOT_VERIFIABLE(전달) |
| CLOUDFLARE_CUTOVER_READY | 계획·합격 기준 준비. 계정·슬롯·토큰 미확인 | NOT_VERIFIABLE |
| RENDER_LIVE_VERIFIED | Web/API/통합 200 (읽기 전용). LIVE SHA는 대시보드 미접근 | EXEC PASS(health) / NOT_VERIFIABLE(SHA) |
| DATA_PRESERVATION_VERIFIED | 비영속 구조, 백업 없음 | FAIL |
| DEPLOY_READY | 코드는 준비, 승인·손실 수용 결정 대기 | NOT_VERIFIABLE |
| DEPLOY_VERIFIED | 배포 없음 | N/A |
| PRODUCTION_E2E_PASS | 운영 쓰기 E2E 미실행 | NOT_VERIFIABLE |
