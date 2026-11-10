# VillageCoverage v27.2 — 최종 PR 통합·Cloudflare 전환·Render 배포 게이트 Handoff (`V27_2_RELEASE_FINALIZATION_HANDOFF.md`)

- **작성 시각**: `2026-11-09 18:32 KST` (`2026-11-09T09:32:00Z`)
- **재검증·갱신 시각**: `2026-11-10 13:41 KST` (`2026-11-10T04:41:00Z`) — 승인된 브로커 요청 `344a210dbd534443` 실행으로 [PR #22](https://github.com/JongHyun070105/village-coverage/pull/22)(`7979253` → mergeCommit `63e8d578a3cec0a282254e17147ad9d91737bab9`) 병합 완료, PR #23·#25 Base `main` 전환 후 `e0039b941e9f4817` 실행으로 [PR #23](https://github.com/JongHyun070105/village-coverage/pull/23)(`15b87a8` → mergeCommit `8ccabeaa08e40cf878f051a216ac32056884e397`) 병합 완료, 그리고 [PR #24](https://github.com/JongHyun070105/village-coverage/pull/24)(`4e00aa3`) 병합 브로커 승인 요청(`e39b90d288f7456b`: `PENDING`) 상태를 반영함.
- **기준 저장소**: `https://github.com/JongHyun070105/village-coverage`
- **작업 범위**: 기존 v21~v27.1 성과를 보존하고(새 기능 개발·전체 QA 재실행 없음), **v27.1 보고서의 사실 오류 4건 정정, PR #22·#23 실제 `main` 병합 완료 및 PR #24 승인 게이트 점검, Cloudflare 이중 스케줄러 위험 제거 및 15단계 전환 절차 수립, Free 한도·Subrequest 정밀 감사, SQLite 옵션 A/B 10대 코드 검증 및 고지 문구 준비, Render 최종 배포 절차 확정**을 기록한다.

---

## 1. GitHub 최신 상태 및 승인 사용 여부

| 항목 | 실측값 | 판정 |
|---|---|---|
| 원격 `origin/main` SHA | `8ccabeaa08e40cf878f051a216ac32056884e397` (`tree`: `7f5b353e415ed4a13c34e488f06cce6b17e172e4` — PR #23 `15b87a8` 트리와 100% 동일, 통합 RC `460dcbd`와는 PR #24의 2개 파일 `+160/-0`만 차이) | `EXEC PASS` |
| [PR #21](https://github.com/JongHyun070105/village-coverage/pull/21) | `state: MERGED` (`2026-11-09T06:56:10Z` / `15:56:10 KST`), `headRefOid: 819fcce9807002423a937fc6abf8123e23fd689d`, `mergeCommit: 90bd6c87df0278d72228b154ee45ca7b6de45a2f` (5 files, `+96/-58`) | `EXEC PASS` |
| [PR #22](https://github.com/JongHyun070105/village-coverage/pull/22) | `state: MERGED` (`2026-11-10T04:33:25Z` / `13:33:25 KST`), `baseRefName: main`, `headRefOid: 7979253eac579db9e084fd6d6222b099adb12396`, `mergeCommit: 63e8d578a3cec0a282254e17147ad9d91737bab9` (`orch-approval run 344a210dbd534443` 실행 완료, 8 files `+1171/-60`) | **`EXEC PASS` (병합 완료)** |
| [PR #23](https://github.com/JongHyun070105/village-coverage/pull/23) | `state: MERGED` (`2026-11-10T04:38:25Z` / `13:38:25 KST`), `gh pr edit 23 --base main`으로 Base를 `main`으로 변경·2개 파일(`tests/test_render_keepalive.py`, `V25_PRODUCTION_READINESS_AND_FULL_QA_REPORT.md`, `+312/-0`) diff 검증 후 `orch-approval run e0039b941e9f4817`로 병합 완료, `headRefOid: 15b87a80d3fb8890b2ccb21008fcdda49f9ee217`, `mergeCommit: 8ccabeaa08e40cf878f051a216ac32056884e397` | **`EXEC PASS` (병합 완료)** |
| [PR #24](https://github.com/JongHyun070105/village-coverage/pull/24) | `state: OPEN`, `baseRefName: main`, `headRefOid: 4e00aa3c30a4f72350f799a61833dbb9e3915abb`, 최신 `main`(`8ccabea`) 기준 `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN` (2 files: `backend/demand.py` `+5`, `tests/test_demand.py` `+155`, 총 `+160/-0`) — 브로커 승인 `e39b90d288f7456b` (`PENDING`) 대기 | `EXEC PASS` (승인 대기) |
| [PR #25](https://github.com/JongHyun070105/village-coverage/pull/25) | `state: OPEN`, `baseRefName: main` (`gh pr edit 25 --base main`으로 Base 전환 완료), `headRefOid: a8a1e8653282625e0ae2022779f5d5bbc62c2aaa`, `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN` (고유 커밋 `301a5b9`, `a8a1e86` — Cloudflare 전용 5 files `+282/-18`) | `EXEC PASS` (생성·Base 전환 완료, 별도 승인 대상) |
| 신규 병합 여부 | **2건 (`PR #22`, `PR #23` 병합 완료)** — `orch-approval run 344a210dbd534443` 및 `orch-approval run e0039b941e9f4817` 실행으로 `main`이 `8ccabeaa08e40cf878f051a216ac32056884e397`로 전진함. PR #24는 브로커 승인 `e39b90d288f7456b` (`PENDING`) 대기 | `EXEC PASS` |
| 최신 CI 실행 결과 | • 구 `main` (`90bd6c8`): [`42576124307`](https://github.com/JongHyun070105/village-coverage/actions/runs/42576124307) — `completed / success`<br>• PR #22 HEAD (`7979253`): [`42580300058`](https://github.com/JongHyun070105/village-coverage/actions/runs/42580300058) — `completed / success` (`backend`, `frontend` PASS); 병합 커밋(`63e8d57`) CI: [`42756612413`](https://github.com/JongHyun070105/village-coverage/actions/runs/42756612413)<br>• PR #23 HEAD (`15b87a8`, 트리 `7f5b353` 동일): [`42569948191`](https://github.com/JongHyun070105/village-coverage/actions/runs/42569948191) — `completed / success` (`backend` `129004774448`, `frontend` `129004774230` PASS); 병합 커밋(`8ccabea`) CI: [`42757140198`](https://github.com/JongHyun070105/village-coverage/actions/runs/42757140198)<br>• PR #24 (`4e00aa3`): [`42576144570`](https://github.com/JongHyun070105/village-coverage/actions/runs/42576144570) — `completed / success` (`backend`, `frontend` PASS) | `EXEC PASS` |
| 기존 승인 ID 상태 (`orch-approval status`) | • `834c2bfa6ca24056` / `21cd9a94f8b4437a`: **`EXPIRED · 이미 사용됨 (재실행 불가)`**<br>• `344a210dbd534443` (PR #22 `7979253` 병합): **`APPROVED · 이미 사용됨 (재실행 불가)`** (이전 잡 `122011f8ce85463f`는 미사용 `PENDING`)<br>• `e0039b941e9f4817` (PR #23 `15b87a8` 병합): **`APPROVED · 이미 사용됨 (재실행 불가)`**<br>• `e39b90d288f7456b` (현재 잡 PR #24 `4e00aa3` 병합, 이전 잡 `3321e4ff016e4b4c`): **`PENDING`** | `EXEC PASS` |
| Primary Checkout 보존 | `/Users/jonghyun/Projects/village-coverage` (`fix/demand-negation-20261029` @ `ce3bc40`) — 기존 dirty/untracked 파일 전혀 수정·삭제하지 않고 그대로 보존 | `EXEC PASS` |

---

## 2. v27.1 보고서(`V27_1_INTEGRATION_HANDOFF.md`) 사실 오류 정정 내역

| 정정 항목 | 기존 `V27_1_INTEGRATION_HANDOFF.md` (`82ebc64`) 기술 | 실제 검증된 사실 및 수정 내용 |
|---|---|---|
| **B-1. 예약 실행 `42570675754` HTTP 200 오기** | `42570675754`(`2026-11-09 15:02:24 KST`, `db48109`)를 최근 `schedule` 실행으로만 적거나 이전 응답 요약에서 GET 전송·HTTP 200 성공처럼 혼합 기술 | 원본 job 로그 재조회 결과 `outcome=schedule_delay delay_seconds=450`, `outcome=skipped_late_schedule delay_seconds=450`으로 확인됨. **GitHub Actions job 결론만 `success`(`exit 0`)였을 뿐 실제 HTTP GET 전송은 `0건`이고 코드상 `SKIP` 처리됨.** 누적 24회 예약 실행 중 Web/API/통합 `HTTP 200`은 **`0 / 0 / 0`** 임을 명시하고 수동 health probe 결과와 엄격히 분리함. |
| **B-2. Cron 워크플로 파일 경로 오기** | `.github/workflows/render-keepalive.yml`로 표기 (45, 151, 221행) | 실제 저장소 파일 경로인 **`.github/workflows/render-free-keepalive.yml`** 로 전수 수정함. 또한 PR #22(`origin/main...7979253`)의 실제 변경 8개 파일 목록과 PR #24(`+5/+155`) 라인 수를 실제 `git diff --numstat`과 일치시킴. |
| **B-3. Cloudflare Workers Logs 보존 정책 표현** | `"영구 관측성 설정"`, `"Workers Logs에 구조화 JSON 로그가 영구 수집됨"`으로 기술 (131~132행) | 1) **로그 수집 설정 활성화**(`wrangler.toml` `[observability] enabled = true`)만 코드에 추가된 상태이며, 2) **실제 운영 로그 수집은 미배포 상태이므로 `0건`(`NOT_VERIFIABLE`)** 이고, 3) **무료 플랜 보존 기간은 3일(72시간, 일 200,000 이벤트 상한)** 이며 영구 보존되지 않음, 4) **Cron Events 대시보드는 최근 100회 실행**(약 1.85일)만 표시, 5) **무료 플랜에는 외부 영구 저장(Logpush)이 없음**을 명확히 구분하여 수정함. 6) (`21:45 KST` 추가) 공식 요금 문서상 **`2026-12-01`부터 Workers Logs가 Cloudflare Observability 요금제로 전환**(Free: 일 0.5 GB 수집, 7일 보존, 한도 도달 시 00:00 UTC까지 수집 중단)되므로 "3일"은 `2026-11-30`까지의 값임을 V27.1 §9에 명시함. |
| **H-1. Cloudflare 전환 시 이중 스케줄러 위험** | Step 1에서 `npx wrangler deploy`로 병행 카나리 실행(2~3회 관측) 후 Step 2에서 GitHub `schedule:` 제거 | `wrangler.toml`에 `crons`가 선언된 채 배포하면 GitHub Actions와 Cloudflare가 동시에 Keep-Alive 요청을 보낼 위험이 있으므로 **병행 카나리 절차를 폐기**하고, **GitHub `schedule:` 선행 비활성화 및 잔여 잡 종료 확인 후 Cloudflare Cron Trigger를 단독 활성화**하도록 수정함. |

---

## 3. Scheduler — GitHub Actions 예약 실행 재평가 (Phase G)

`2026-11-03 15:26Z` ~ `2026-11-10 01:25Z` (`10:25 KST`) 기준 `.github/workflows/render-free-keepalive.yml` 전체 실행 로그 전수 대조 결과:

| 검증 항목 | 구 `main` (`db48109`, PR #21 병합 전) | 새 `main` (`90bd6c8`, `11-09 15:56:10 KST` PR #21 병합 후 ~ `11-10 10:25 KST`) |
|---|---|---|
| 기대 10분 크론 슬롯 수 (주간 창 `08:55~17:45 KST`, 하루 54슬롯) | `11-04 08:55` ~ `11-09 15:55 KST` 약 313슬롯 (5일×54 + 당일 43) | **22개 주간 슬롯** (`11-09 16:05~17:45 KST` 12개 + `11-10 08:55~10:25 KST` 10개) |
| 실제 `schedule` 이벤트 및 job 생성 수 | **24회** (생성률 약 `7.7%`; 그중 운영 창 안 생성은 **12회**, 하루 약 2회 — 12시대·15시대 KST, 나머지 12회는 20:57~01:16 KST 창 밖 지연 도착) | **주간 창 내 `0회` (`0.0%`), 야간 창 밖 지연 도착 `2회`**:<br>• [`42650923138`](https://github.com/JongHyun070105/village-coverage/actions/runs/42650923138) (`11-10 01:03:51 KST`, job 생성·`success`)<br>• [`42674363508`](https://github.com/JongHyun070105/village-coverage/actions/runs/42674363508) (`11-10 03:28:39 KST`, GitHub 플랫폼 오류로 `jobs: []` 채 `failure`) |
| 최신 `main` SHA(`90bd6c8`) 사용 여부 | 전수 `db48109` 사용 | 야간 2회(`42650923138`, `42674363508`) 모두 **`90bd6c87df0278d72228b154ee45ca7b6de45a2f` 사용 확인** |
| Keep-Alive 코드상 `SKIP` | **22회** (`skipped_late_schedule`, `42570675754` `delay_seconds=450` 포함, **GET 0건**, job 결론만 `success`) | **1회** (`42650923138`: `outcome=schedule_cron_validated` → `outcome=skipped_window kst=2026-11-10T01:03+09:00`, **GET 0건** — PR #21 수정으로 `skipped_late_schedule` 대신 창 판정에 도달함 확인) + **플랫폼 job 미생성 실패 1회**(`42674363508`, `jobs: []`, **GET 0건**) |
| 실제 HTTP `GET` 요청 전송 실행 수 | **2회** (`41980788277`, `42344214454` — 각 9회씩 총 **18회 GET 전송**) | **`0회`** (주간 창 내 실행 0건, 야간 2회는 창 밖 SKIP 및 플랫폼 실패로 GET 0건) |
| 예약 실행의 Web `HTTP 200` | **`0건`** (구 `main` 3회 시도 한도로 6회 모두 `HTTP 503`) | **`0건`** |
| 예약 실행의 API `HTTP 200` | **`0건`** (6회 모두 `HTTP 503`) | **`0건`** |
| 예약 실행의 통합(`/api/health`) `HTTP 200` | **`0건`** (6회 모두 `HTTP 503`) | **`0건`** |
| 주간 운영 시간대 실행 간격 / 최대 공백 | 창 내 연속 실행 간격 `150~185분`; 08:55 슬롯 대비 첫 실행까지 최대 공백 **`231분`** (`11-05` 08:55 → 12:46 KST) | `11-09 15:02:24~18:00 KST`(`177분 36초`) 및 `11-10 08:55~10:25 KST`(`90분+`) 주간 창 내 **연속 무실행** |
| Cloudflare POC 상태 / 실제 전환 여부 | RC `6e90a67`: 유닛 `13 passed`, `wrangler deploy --dry-run` `PASS`; 로컬 `workerd` 실 Render GET 증거는 V26 보고서 "실제 런타임 실행"(`14:48 KST`)에 한정; 신규 `a8a1e86`: `16 passed`, `21:43 KST` 창 밖 `workerd` 실행에서 `skipped_window`·Render 요청 0건 | **미전환** — 대상 계정에 Worker `villagecoverage-keepalive-poc` 미존재(`code 10007`) |

- **핵심 분리 평가**:
  - **HTTP 복구 안정성 (`EXEC PASS` 로컬 검증)**: PR #21(지연 도착 시 주간 창 내 조기 SKIP 제거) + PR #22/#23(16회/240s 엔드포인트 예산, 480s 전체 예산, 429/503/Retry-After 처리)은 **스케줄러가 잡을 실행해 주기만 하면** Render Cold Start(실측 46~102.5초)를 안정적으로 복구한다.
  - **GitHub 스케줄러 전달 안정성 (`FAIL`)**: GitHub Actions `schedule` 자체가 주간 슬롯의 92% 이상을 누락하고 PR #21 병합 후에도 `18:00 KST`까지 단 한 번도 실행되지 않았으므로, GitHub `schedule`만으로는 15분 spin-down을 막을 수 없다.

---

## 4. Cloudflare Cron 무료 한도·Subrequest·관측성·안전 전환 절차 (Phases H & I)

### 4.1 Cloudflare Workers Free 한도 및 Subrequest 정밀 감사

| 항목 | Cloudflare Workers Free 공식 한도 | POC (`poc/cloudflare-workers-keepalive/`) 설계 및 실측 | 여유도 및 판정 |
|---|---|---|---|
| 요금제 / 결제 설정 / 계정 권한 | Free 플랜 ($0/월; Paid는 최소 $5/월) | `CLOUDFLARE_API_TOKEN`은 없지만 **Wrangler OAuth 세션 존재**(`wrangler whoami`: `Bobi09361@gmail.com's Account`, ID `6c9308b5…5315`; `account (read)`, `workers (write)`, `workers_scripts (write)`, `workers_tail (read)` 등). billing 권한이 없어 플랜·결제수단 조회 불가. 이 계정이 의도한 배포 대상인지 사용자 확인 필요 | 인증 `EXEC PASS` / 플랜·결제 **`NOT_VERIFIABLE`** |
| Cron Trigger 상한 | 계정당 최대 **5개** | 3개 (`55 23 * * *`, `5,15,25,35,45,55 0-7 * * *`, `5,15,25,35,45 8 * * *`) | 계정 내 기존 Cron Trigger **≤ 2개**인지 사전 확인 필수 (`NOT_VERIFIABLE` — Wrangler에 계정 단위 목록 명령이 없어 대시보드 확인 필요) |
| Worker 호출 횟수 | 일 **100,000회** (UTC 자정 리셋) | 일 **54회** (`08:55~17:45 KST`, 10분 간격) | 한도의 **0.054%** (`EXEC PASS`) |
| **Subrequest 사용량** | invocation당 최대 **50회** | • `redirect: "manual"` 고정으로 3xx 리디렉션 추가 subrequest **0건**<br>• 외부 바인딩(KV/D1/R2/Cache) 호출 **0건**<br>• **합성(0ms mock clock) 최악 상한**: 3개 엔드포인트 × `MAX_ATTEMPTS(16)` = **48회 (< 50)**<br>• **실제 wall-clock(`monotonic`+`sleep`) 최악 상한**: 백오프(`5s, 10s, 20s...`)와 엔드포인트당 `240s` 예산(`ENDPOINT_RECOVERY_BUDGET_MS`)으로 인해 단일 엔드포인트는 최대 **14회**(`235s` 누적 대기 후 종료)까지만 호출 가능하며, 전체 `480s` 예산(`MAX_RUN_MS`) 안에서는 3개 엔드포인트 합산 최대 **`14 + 14 + 2 = 30회`** (정상 1회 성공 시 2~3회, 40s+90s 콜드스타트 복구 시 ~14회) | 합성 루프 상한 **48/50**, 실제 런타임 시간 예산 상한 **30/50 (여유 20회 / 40%)** — 예외 상황에서도 50회 한도 초과 불가. `a8a1e86`에 "지속 503 → 정확히 30회", "시계 정지 → 정확히 48회" 테스트 추가(`16 passed`). 여유가 충분하여 재시도 예산은 변경하지 않음 (`EXEC PASS`) |
| CPU 시간 | invocation당 **10 ms** (네트워크 I/O 대기 제외) | 4KB 제한 텍스트 디코딩 + JSON 파싱 + `Intl.DateTimeFormat` 호출뿐이므로 < 2 ms 예상 | 로컬 `PASS` / 에지 실측은 배포 후 확인 |
| Wall-clock 시간 | Cron invocation당 최대 **15분** | 엔드포인트당 4분(`240s`), 전체 실행 최대 **8분(`480s`)**, `18:00 KST` 하드 컷오프 | 15분 한도의 **53%** (`EXEC PASS`) |
| `Retry-After` / 재시도 | — | 지수 백오프 `5s → 10s → 20s(상한)`, `Retry-After` 정수초·HTTP-date 파싱 후 `180s`(`MAX_RETRY_AFTER_MS`) 상한 적용, `18:00 KST` 또는 잔여 예산 초과 시 즉시 중단 | 유닛 테스트 `13 passed` (`EXEC PASS`) |
| 관측성 및 보존 기간 | • Workers Logs Free: **일 200,000 이벤트, 3일(72시간) 보존** (`2026-11-30`까지) → `2026-12-01`부터 Observability Free **일 0.5 GB, 7일 보존**<br>• Workers Logpush: Workers Paid 전용<br>• Cron Events: **최근 100회 실행**(신규 Worker는 표시까지 최대 30분) | • `wrangler.toml`에 `[observability] enabled = true, head_sampling_rate = 1` 설정<br>• 8대 필드(`scheduled_at`, `started_at`, `request_sent`, `status`, `attempts`/`retries`, `elapsed_ms`, `outcome`, `failure`) JSON 기록, 개인정보·쿼리스트링·응답 본문 미포함<br>• 트리거 누락은 Cron Events 실행 시각 간격 및 `scheduled_delay_seconds`로 관측<br>• `scheduled()`는 `outcome !== "ok"`이면 예외를 던지므로 18:00 직전 지연 도착의 `skipped_window`/`partial`도 Cron Events에 예외로 표시됨(오탐 가능, 코드 미변경) | 로컬 검증 `EXEC PASS` / **실제 운영 로그 수집은 미배포 상태이므로 `0건`(`NOT_VERIFIABLE`)** |

### 4.2 이중 스케줄러 위험을 제거한 15단계 안전 전환 절차 (Phase H-2, `21:45 KST` 개정)

**핵심 설계**: (a) `wrangler.toml`은 Cron Trigger를 선언하므로 배포 즉시 트리거가 활성화된다. 공식 문서상 `[triggers]`를 생략·주석 처리하면 기존 트리거가 **유지**되고, `crons = []`로 배포해야만 **전부 제거**된다. 그래서 같은 Worker 이름에 `crons = []`만 다른 `wrangler.nocron.toml`(`a8a1e86`)을 크론 없는 업로드 겸 롤백 스위치로 쓴다. (b) 두 스케줄러 모두 `08:55~17:59 KST` 밖에서는 요청을 보내지 않으므로, 전환을 **운영 창 밖(18:00~08:30 KST)** 에 수행하면 전파 지연(최대 15분) 동안 중복도 공백도 생기지 않는다. (c) GitHub 쪽은 코드 변경 없이 즉시 되돌릴 수 있는 `gh workflow disable/enable`을 우선 사용한다.

> **수동 테스트 주의 (H-3)**: `fetch()`는 항상 `404 Cron-only worker`이며 공개 트리거를 추가하지 않는다. scheduled 검증은 로컬 `wrangler dev` + `/cdn-cgi/local/scheduled?cron=...`(Wrangler 4.158.0 실측: 플래그 없이 `/cdn-cgi/local/scheduled`·`/cdn-cgi/handler/scheduled` 동작, `/__scheduled`만 `--test-scheduled` 필요)로 한다. 운영 창 안에서 실행하면 실제 Render GET이 발생하고, 창 밖에서는 `skipped_window`(요청 0건, 예외 때문에 HTTP 500)로 끝난다.

| # | 단계 | 정확한 명령 / 확인 | 승인 |
|---|---|---|---|
| 1 | 인증 확인 | `wrangler whoami` → 의도한 계정 ID인지 사용자 확인 | 불필요(읽기) |
| 2 | Free 요금제·결제수단 | 대시보드 Workers & Pages → Plans: Workers Free, 결제수단 미등록 | 사용자 확인 |
| 3 | 기존 Cron Trigger 수 | 대시보드에서 계정 전체 Cron Trigger ≤ 2개 (Free 상한 5) | 사용자 확인 |
| 4 | 무료 한도 재확인 | 50 subrequests(POC 최대 30, 하드캡 48), CPU 10ms, Cron wall 15분(POC 최대 8분), 일 100,000 요청(POC 54 invocation) | 불필요 |
| 5 | 코드·설정 감사 | `node --test test/worker.test.mjs`(16 passed), `wrangler deploy --dry-run` 및 `--config wrangler.nocron.toml --dry-run`(둘 다 16.56 KiB) | 불필요 |
| 6 | 크론 없는 배포(선택) | `wrangler deploy --config wrangler.nocron.toml` → 대시보드 Triggers에 Cron 0개 확인 | **필요**(운영 배포) |
| 7 | 수동 호출 검증 | 로컬 `wrangler dev` + `/cdn-cgi/local/scheduled` (운영 Worker에는 공개 트리거 없음) | 불필요(로컬) |
| 8 | GitHub schedule 비활성화 (**18:00 이후 수행**) | `gh workflow disable render-free-keepalive.yml` (영구화는 `.github/workflows/render-free-keepalive.yml`의 `schedule:` 제거 PR로 별도 처리) | **필요** |
| 9 | 잔여 GitHub 예약 job 종료 확인 | `gh run list --workflow render-free-keepalive.yml --status queued` 및 `--status in_progress` 모두 0건, `gh workflow view render-free-keepalive.yml`이 `disabled_manually` | 불필요 |
| 10 | Cloudflare Cron 활성화 (창 밖) | `wrangler deploy` (기본 `wrangler.toml`, 3개 크론) | **필요** |
| 11 | 전파 확인 | 최대 15분 대기 후 대시보드 Triggers에 3개 크론 표시 확인; 첫 실행은 다음 날 `08:55 KST`(`55 23 * * *`) | 불필요 |
| 12 | 실제 예약 실행 확인 | Cron Events(최근 100회) + Workers Logs의 `scheduled_start`/`scheduled_complete` | 불필요 |
| 13 | Web/API 200 확인 | `scheduled_complete.endpoints[]`의 `web`/`api`(+08:55 `integrated-health`) `status: 200`, `outcome: "ok"` | 불필요 |
| 14 | 반복 간격 확인 | 08:55~17:45 KST 10분 간격, 18:00 이후 요청 0건; Workers Logs 보존 기간(현재 3일) 안에 증거 보관 | 불필요 |
| 15 | 실패 시 롤백 | ① `wrangler deploy --config wrangler.nocron.toml`(트리거 전부 제거) → ② 최대 15분 전파 + 진행 중 실행 최대 8분 대기, Cron Events에 신규 실행이 없음을 확인 → ③ `gh workflow enable render-free-keepalive.yml`. 긴급 시에도 ①을 먼저 실행 | **필요** |

---

## 5. SQLite 임시 데모 정책 최종 점검 및 고지 문구 (Phase J)

### 5.1 실제 코드 기준 10대 항목 재확인 (`EXEC PASS` / `STATIC`)

| # | 점검 항목 | 코드 근거 및 확인 결과 |
|---|---|---|
| 1 | 합성 데이터와 공개 데이터의 구분 | `frontend/app/layout.tsx:23-24` 전역 배너 및 `frontend/app/plans/page.tsx:371`(`public_data_fixture_sha256`, `route_matrix_fingerprint`)에서 공개 통계/합성 시드 데이터와 모델 추정치임을 명확히 구분함. |
| 2 | 실제 주민 입력 차단 | `backend/public_demo.py:42-98` allowlist가 설문 등록, 자유텍스트 수요 구조화(`/api/demand*`), CSV 업로드(`/api/imports*`), 피드백, 중복 판정 API를 전수 `PUBLIC_DEMO_BLOCKED`(`HTTP 404 DEMO_MODE_RESTRICTED`)로 원천 차단함. |
| 3 | 방문자 세션 분리 | `backend/public_demo.py:26-30, 107-120`에서 `vc_demo_session` 쿠키(`HttpOnly; SameSite=Lax; Secure`)의 SHA-256 해시(`session_hash`)별로 `public_demo_plan_owners` 소유권을 격리함(최대 256 활성 세션, 세션당 최대 20개 계획). |
| 4 | 계획·승인 기록의 임시성 | `PUBLIC_DEMO_SESSION_IDLE_SECONDS = 1800`(30분 비활동 만료) 경과 시 세션 소유 계획·회차·불참·승인 기록을 자동 퍼지하며, `frontend/app/plans/page.tsx:38, 261`에서 `"데모 승인됨"` 및 `"PLANNER·REVIEWER는 시연용 역할이며 실제 인증이 아닙니다"`로 명시함. |
| 5 | UI의 데이터 손실 안내 | `frontend/app/layout.tsx:24`: *"계획·불참·승인 상태는 브라우저 세션별로 격리되며 30분 동안 활동이 없으면 만료됩니다. 무료 데모 서버의 재시작·재배포 시 임시 계획이 초기화될 수 있습니다."* 가 이미 모든 화면 상단에 표시됨. |
| 6 | 초기 seed 자동 복원 | `backend/database.py:674-681`이 DB 경로를 `/tmp/villagecoverage-public-demo.sqlite`(상한 64 MiB)로 강제하며, 컨테이너 시작 시 FastAPI lifespan(`backend/main.py:267`)의 `initialize_public_demo_storage()`(`backend/main.py:304`)가 `data/demo.json`으로 `seed_reference_data`·`seed_provider_data`·`seed_public_demo_routes`(지역 54개 → 54×54 = 2,916 경로)를 재적재함. DB 크기 상한 `PUBLIC_DEMO_MAX_DATABASE_BYTES = 64 MiB`(`backend/public_demo.py:30`). |
| 7 | Render spin-down 영향 | Render Free 서비스는 15분 무트래픽 시 spin-down되며, 이 때 컨테이너 로컬 `/tmp` SQLite 파일이 초기화되어 방문자 임시 세션·계획은 사라지고 재기동 시 기본 시드만 복원됨. |
| 8 | 개인정보 저장 여부 | 공개 데모에서는 주민 원문·설문·피드백 입력 API 자체가 차단되어 개인정보가 저장될 경로가 없으며(`0건`), 비데모 경로에서도 `backend/demand.py:858-882`가 PII 마스킹 후 후보 서비스 ID만 처리함. |
| 9 | 재시작 후 사용자 경험 | 재시작 후 읽기 요청(`GET`)은 즉시 복원된 기본 시드 데이터를 정상 반환하며, 만료·초기화된 세션 쿠키로 쓰기 요청 시 `HTTP 410 DEMO_SESSION_EXPIRED`를 반환하여 `frontend/components/api-error.tsx:9, 34`가 *"이 브라우저 세션이 만료되었습니다. 할 일: 공개 데모를 새로고침해 새 세션으로 시작하세요."* 안내와 재시도 버튼을 제공함. |
| 10 | 저장된 계획 조회 실패 시 안내 | `frontend/app/plans/page.tsx:286-293`에서 계획이 없을 때 *"저장된 계획이 없습니다. 시나리오 비교에서 계획을 생성하면 이곳에 표시됩니다."* 및 `/scenarios` 이동 링크를 표시하며, 삭제된 `schedule_id` 조회 시 `ApiErrorNotice`(`HTTP 404/410`)와 *"최신 상태 다시 불러오기"* 버튼을 표시함. |

### 5.2 옵션 A vs 옵션 B 및 사용자 고지 문구 준비

- **옵션 A (권장 — 순수 임시·합성 데모 유지)**:
  - **코드 변경**: `0줄` (`frontend/app/layout.tsx:20-31`에 이미 임시성·30분 만료·재시작/재배포 시 초기화 안내가 반영되어 있음).
  - **외부/제출 안내용 표준 고지 문구 (옵션 A 선택 시 즉시 사용 가능)**:
    > *"본 공개 데모(`villagecoverage-public-demo`)는 공모전 심사를 위한 합성·공개 데이터 기반 체험 환경입니다. 실제 주민 개인정보나 설문 원문 입력은 보안 정책상 차단되어 있으며, 방문자가 생성한 공급계획·불참·데모 승인 이력은 브라우저 세션별로 격리되어 30분 비활동 시 또는 무료 데모 서버의 절전(spin-down)·재시작·재배포 시 자동 초기화되고 기본 시드 데이터로 복원됩니다."*
- **옵션 B (대안 보존 — 영속 DB 전환)**:
  - Render 유료 플랜 전환 + Persistent Disk 마운트(또는 `backend/database.py` 3,585줄 외부 DB 이식) 및 `backend/database.py:674-681` `/tmp` 경로 가드 수정 필요.
- **배포 차단 게이트**: 현재 운영 컨테이너 `/tmp/villagecoverage-public-demo.sqlite` 내부의 실시간 세션 레코드 존재 여부는 외부에서 조회 불가(`NOT_VERIFIABLE`)하므로, **사용자의 명시적인 옵션 A(데이터 초기화 수용) 또는 옵션 B 선택 전까지 Render 배포를 보류**한다.

---

## 6. Render 최종 배포 준비 및 실행 절차 (Phase K)

- **현재 LIVE 배포 추정 SHA (`origin/submission/public-demo-deploy`)**: `36319c6551b5c80d3f8c4e1aaa43bc7bbf8fe6e3`
- **최종 배포 후보 조건**: 기존 로컬 RC SHA(`460dcbd` / `6e90a67`)를 그대로 배포 브랜치에 넣지 않고, **PR #22 → PR #23 → PR #24가 모두 사용자 승인 하에 `main`에 순차 병합되고 최종 `main` CI가 `SUCCESS`를 통과한 정확한 `main` SHA**를 배포 대상으로 고정한다.
- **사전 호환성 확인 (`36319c6` 대비 통합 트리)**:
  - `render.yaml`, `pyproject.toml`, `uv.lock`, `frontend/package.json`, `frontend/package-lock.json`, DB `SCHEMA_VERSION`(`27`), Web/API 시작 명령 및 환경변수: **변경 0건 (`0 diff`)**.
  - LIVE(`36319c6`) → 통합 RC(`460dcbd`) 미배포 변경: 전체 53 files `+4880/-105`, 그중 문서·테스트·POC·e2e 제외 런타임/설정 **25 files `+1195/-94`** (보안 헤더 `backend/security_headers.py`·`frontend/next.config.ts`, 요청 크기 제한 `backend/request_limits.py`, 권한 `backend/authz.py`, 세션 보장 비동기화 `backend/public_demo.py`, Gemini 10초 타임아웃 `backend/demand.py`(PR #24), `/plans`·홈 콜드스타트 UX `frontend/app/plans/page.tsx`·`frontend/app/page.tsx`·`frontend/lib/api.ts`, Keep-Alive 스크립트). 이 중 PR #22·#23·#24 몫은 keep-alive 스크립트·문서·테스트·POC 및 `backend/demand.py +5`뿐이고, `frontend/lib/cold-start.ts`는 RC와 LIVE 사이 변경 목록에 없음.
  - `36319c6`은 `origin/main`의 조상(`git merge-base --is-ancestor` YES)이므로 배포 브랜치 갱신은 force 없이 **fast-forward** 가능.
  - 공개 데모에서 `/api/demand*`는 `DEMO_MODE_RESTRICTED`로 차단되고 `render.yaml`에 `GEMINI_API_KEY`가 없으므로, Gemini 타임아웃 변경은 공개 데모 런타임 동작에 영향 없음(Render 대시보드 비밀값은 미확인).
  - **데이터 영향**: `render.yaml`에 디스크가 없고 공개 데모 DB는 `/tmp/villagecoverage-public-demo.sqlite`로 강제되므로(`backend/database.py:674-681`), **재배포 자체가 현재 컨테이너의 방문자 세션·임시 계획을 모두 지운다**. 이것이 SQLite 정책 결정이 배포 승인의 선행 조건인 이유다.
  - **Rollback 후보**: 기존 `submission/public-demo-deploy` HEAD인 `36319c6551b5c80d3f8c4e1aaa43bc7bbf8fe6e3`.

### 승인 후 12단계 배포 실행 절차 (현재 미실행)
1. PR #22·#23·#24 병합 완료 후 **최종 `main` SHA의 Backend/Frontend CI `SUCCESS`** 확인.
2. 사용자의 **SQLite 정책(옵션 A 임시 데이터 초기화 수용 여부)** 최종 승인 확인.
3. 배포 대상 커밋을 최종 `main` SHA(`<FINAL_MAIN_SHA>`)로 고정하고 `git diff 460dcbd <FINAL_MAIN_SHA>`가 비어 있는지(트리 `c92da39` 동일) 확인. `0710e78`(`6e90a67`)에는 어떤 PR에도 없는 관측성 커밋 `301a5b9`가 포함되어 있어 main과 일치할 수 없으므로 비교 기준이 아님.
4. 별도 배포 승인(`orch-approval`) 하에 `git push origin <FINAL_MAIN_SHA>:refs/heads/submission/public-demo-deploy` (fast-forward push, force-push 불필요) 실행.
5. Render Web(`villagecoverage-public-demo-web`) 및 API(`villagecoverage-public-demo-api`) 배포 시작 및 완료 대기(콜드 빌드/기동 여유 포함).
6. 배포 브랜치 원격 SHA 및 응답 헤더(`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Permissions-Policy`)로 신규 버전 LIVE 반영 확인.
7. API 단독 헬스체크: `curl -sS -i https://villagecoverage-public-demo-api.onrender.com/health` → `HTTP 200` (`{"status":"ok"}`).
8. Web-API 통합 헬스체크: `curl -sS -i https://villagecoverage-public-demo-web.onrender.com/api/health` → `HTTP 200` (`demo_data_available: true`).
9. 16개 주요 페이지 읽기 전용(GET) Smoke Test (`HTTP 200` 확인, 운영 DB 쓰기 없음).
10. 핵심 시나리오 읽기 전용 브라우저 QA (`/`, `/scenarios`, `/plans`, `/fairness`, `/data-status` 등 콘솔 오류·레이아웃 깨짐 0건 확인; 운영 DB 쓰기 E2E는 별도 승인 없이는 미실행).
11. 응답 지연·오류 로그 점검.
12. 이상 발생 시 즉시 Rollback: Render Dashboard에서 `36319c6` 배포를 Rollback(빌드 재사용) 하거나, 별도 승인 후 `36319c6` 트리를 되돌리는 revert 커밋을 배포 브랜치에 forward push(force push 금지). Rollback 역시 `/tmp` DB를 초기화함.

---

## 7. QA 및 통합 RC 보존 검증 (Phase F)

- **코드 트리 동일성 확인**:
  - PR #22(`7979253`), PR #23(`15b87a8`), PR #24(`4e00aa3`), `origin/main`(`90bd6c8`) 모두 이전 검증 시점 이후 코드 변경이 **0바이트**이므로, 통합 RC `460dcbd0b968a40d27b500bc9242f1fd4e0ef42c` (tree `c92da39fa920b8b0d375b419bd5afe4205223aaf`) 및 Cloudflare 관측성 포함 RC `6e90a67ca07ca9cc76354faa3445462596e587d1` (tree `0710e7859e1201a66f1ca71e54e2ef6fb797ab90`)의 검증 증거가 100% 유효하다(불필요한 전체 테스트 재실행 생략).
- **보존된 통합 RC 검증 결과**:
  - Backend Pytest: `766 passed, 1 skipped` (타겟 `test_render_keepalive.py` + `test_demand.py` + `test_public_demo.py` `161 passed, 33 subtests`)
  - R1–R13 수용 기준: `113 passed, 0 failed`
  - Frontend Unit (Vitest): `19 passed, 0 failed`
  - Playwright Public Demo E2E: `16 passed` (`/plans` stale region 교정 포함)
  - Cloudflare POC: `node --test` `13 passed, 0 failed`, `npx wrangler deploy --dry-run` `PASS` (`16.56 KiB`)
  - Lint / Typecheck / Build / Security Audit (`ruff`, `compileall`, `eslint`, `tsc`, `next build`, `pip-audit`, `npm audit`): 전수 **PASS (취약점 0건)**
- **이번 갱신에서 실행한 검증**: `a8a1e86`에서 `node --test` `16 passed, 0 failed`; `wrangler 4.158.0 deploy --dry-run`(`wrangler.toml`, `wrangler.nocron.toml` 각 `16.56 KiB / gzip 4.24 KiB`); 로컬 `workerd` scheduled 3경로 호출(`skipped_window`, Render 요청 0건); 예약 실행 24건 로그 전수 재집계. Backend/Frontend 코드는 변경하지 않아 재실행하지 않음.
- **관측성 커밋 PR 생성 및 Base 전환 완료 ([PR #25](https://github.com/JongHyun070105/village-coverage/pull/25))**: `301a5b9`·`a8a1e86`(`feat/v27.1-cloudflare-observability-20261109`, HEAD `a8a1e8653282625e0ae2022779f5d5bbc62c2aaa`)을 원격에 푸시하고 PR #22 병합 직후 `gh pr edit 25 --base main`으로 Base를 `main`으로 전환 완료함(Cloudflare 전용 5개 파일 `+282/-18`, `MERGEABLE/CLEAN`). PR #25 병합은 별도 승인 대상임.
- **미검증 사항 (`NOT_VERIFIABLE` / 승인 대기)**:
  - PR #24 실제 `main` 병합 후 생성될 최종 `main` 머지 커밋의 CI (브로커 승인 `e39b90d288f7456b` 후 확인 예정)
  - Cloudflare 실제 에지 배포 후 Cron 전달 간격 및 Workers Logs 실수집
  - 실제 Gemini 원격 API 호출 (무키 오프라인 정책에 따라 실제 SDK `httpx` 레이어까지만 검증)
  - 신규 배포 후 프로덕션 LIVE E2E

---

## 8. 최종 상태 판정표 (Phase M — 14개 필수 항목)

| 항목 | 등급 | 실제 증거 |
|---|---|---|
| `MAIN_CI_PASS` | **`EXEC PASS`** | 구 `origin/main` (`90bd6c8`) CI [`42576124307`](https://github.com/JongHyun070105/village-coverage/actions/runs/42576124307) `completed / success`; 현재 `origin/main` (`8ccabeaa08e40cf878f051a216ac32056884e397`, PR #23 병합 커밋, 트리 `7f5b353e415ed4a13c34e488f06cce6b17e172e4`)과 동일 트리인 `15b87a8` CI [`42569948191`](https://github.com/JongHyun070105/village-coverage/actions/runs/42569948191) `completed / success` (`backend` `129004774448` PASS, `frontend` `129004774230` PASS) 및 병합 커밋 CI [`42756612413`](https://github.com/JongHyun070105/village-coverage/actions/runs/42756612413)·[`42757140198`](https://github.com/JongHyun070105/village-coverage/actions/runs/42757140198) 실행 |
| `PR22_INTEGRATED` | **`EXEC PASS`** | [PR #22](https://github.com/JongHyun070105/village-coverage/pull/22) (`7979253eac579db9e084fd6d6222b099adb12396`, CI [`42580300058`](https://github.com/JongHyun070105/village-coverage/actions/runs/42580300058) `SUCCESS`) — `orch-approval run 344a210dbd534443` 실행으로 `2026-11-10T04:33:25Z`에 `MERGED` 확인(`mergeCommit`: `63e8d578a3cec0a282254e17147ad9d91737bab9`) |
| `PR23_INTEGRATED` | **`EXEC PASS`** | [PR #23](https://github.com/JongHyun070105/village-coverage/pull/23) (`15b87a80d3fb8890b2ccb21008fcdda49f9ee217`, Base `main` 전환 후 2 files `+312/-0`, CI [`42569948191`](https://github.com/JongHyun070105/village-coverage/actions/runs/42569948191) `SUCCESS`) — `orch-approval run e0039b941e9f4817` 실행으로 `2026-11-10T04:38:25Z`에 `MERGED` 확인(`mergeCommit`: `8ccabeaa08e40cf878f051a216ac32056884e397`) |
| `PR24_INTEGRATED` | **`SKIP`** | [PR #24](https://github.com/JongHyun070105/village-coverage/pull/24) (`4e00aa3c30a4f72350f799a61833dbb9e3915abb`, Base `main`, 2 files `+160/-0`, 최신 `main` `8ccabea` 기준 `MERGEABLE/CLEAN`, CI [`42576144570`](https://github.com/JongHyun070105/village-coverage/actions/runs/42576144570) `SUCCESS`) 병합 시도 시 브로커 승인 `e39b90d288f7456b` (`PENDING`, 이전 잡 `3321e4ff016e4b4c` `PENDING`)가 반환되어 TUI 승인 대기 |
| `FINAL_RC_VERIFIED` | **`EXEC PASS`** | 격리 워크트리 `.worktrees/v27-rc-20261109`에서 새 `main`(`90bd6c8`) + PR #22/#23/#24 통합 RC(`460dcbd`, tree `c92da39`) 및 Cloudflare 관측성 보강 RC(`6e90a67`, tree `0710e78`) 구성 완료; Backend `766 passed`, R1–R13 `113 passed`, Vitest `19 passed`, Playwright Public Demo `16 passed`, `pip-audit`/`npm audit` `0건` 검증 완료 |
| `GITHUB_SCHEDULE_DELIVERY` | **`FAIL`** | `.github/workflows/render-free-keepalive.yml` 누적 기대 슬롯 대비 ~7.5%만 실행 생성되었고, PR #21 병합(`11-09 15:56:10 KST`) 이후 주간 22개 슬롯(`11-09 16:05~17:45`, `11-10 08:55~10:25 KST`) 동안 주간 `schedule` 실행 **0건** (야간 창 밖 지연 도착만 2건: `42650923138` `01:03 KST` `skipped_window`, `42674363508` `03:28 KST` 플랫폼 `jobs: []` 실패) |
| `SCHEDULER_HTTP_200` | **`FAIL`** | 누적 26회 GitHub `schedule` 실행 중 구 `main` 22회는 `outcome=skipped_late_schedule`(최신 [`42570675754`](https://github.com/JongHyun070105/village-coverage/actions/runs/42570675754) `delay_seconds=450` 포함, **HTTP GET 0건**), 2회(`41980788277`, `42344214454`)는 각 9회 GET 모두 `HTTP 503` 실패, 새 `main`(`90bd6c8`) 야간 2회(`42650923138`, `42674363508`)도 **HTTP GET 0건**이어서 **예약 실행을 통한 Web/API/통합 HTTP 200은 `0 / 0 / 0`** |
| `CLOUDFLARE_POC_PASS` | **`EXEC PASS`** (로컬) | RC `6e90a67` `13 passed`; 신규 `a8a1e86` `16 passed, 0 failed`(지속 503 → 30회, 시계 정지 → 48회 < Free 50, no-cron 설정 일치), `wrangler 4.158.0` dry-run 두 설정 PASS, 로컬 `workerd` scheduled 실행 확인, [PR #25](https://github.com/JongHyun070105/village-coverage/pull/25) 생성·Base `main` 전환 완료. 운영 Cron 성공을 의미하지 않음 |
| `CLOUDFLARE_CUTOVER_READY` | **`STATIC`** | §4.2 개정 절차(창 밖 전환, `gh workflow disable` 선행, `wrangler.nocron.toml` 롤백 스위치, 공식 문서 기준 `crons = []` 제거·최대 15분 전파). 남은 조건: 계정 소유·Free·기존 Cron 수 사용자 확인, [PR #25](https://github.com/JongHyun070105/village-coverage/pull/25) 병합, 배포 승인 |
| `CLOUDFLARE_LIVE_VERIFIED` | **`SKIP`** | Wrangler OAuth 세션은 있으나 대상 계정에 Worker 미존재(`code 10007`), 배포 승인 없음 → 운영 Cron 실행·Workers Logs 실수집 `0건` |
| `SQLITE_POLICY_RESOLVED` | **`NOT_VERIFIABLE`** | 코드 10대 항목 검증 및 옵션 A(순수 임시·합성 데모 유지, 코드 수정 0줄, 고지 문구 준비 완료) vs 옵션 B(영속 DB) 정밀 대조 완료; 운영 `/tmp` SQLite 내부 레코드 유무는 외부 확인 불가하며 사용자의 최종 정책 선택 대기 |
| `DEPLOY_READY` | **`STATIC`** | LIVE(`36319c6`) 대비 `render.yaml`·`uv.lock`·`pyproject.toml`·`frontend/package*.json`·`SCHEMA_VERSION=27` 무변경, `36319c6`→main fast-forward 가능, 12단계 배포·롤백 절차 준비; 차단 조건: PR #24 병합 및 최종 main CI, SQLite 정책(재배포 시 `/tmp` DB 초기화 수용 여부) 사용자 결정 |
| `DEPLOY_VERIFIED` | **`SKIP`** | 사용자 배포 승인 전이므로 `submission/public-demo-deploy` 브랜치(`36319c6`) 푸시 및 Render 재배포 미실행 |
| `PRODUCTION_E2E_PASS` | **`SKIP`** | 신규 배포 및 운영 DB 쓰기 E2E 승인이 없으므로 프로덕션 쓰기 E2E 미실행 |

---

## 9. 승인 실행 완료 내역 및 남은 승인 대기 작업 (`2026-11-10 13:41 KST` 기준)

| 순서 | 작업 | 정확한 명령 | 실행 전 재확인 / 실행 결과 | 승인 상태 |
|---|---|---|---|---|
| 0 | 보고서 push | `orch-approval run 834c2bfa6ca24056` (`7c6b250..4878157`)<br>`orch-approval run 21cd9a94f8b4437a` (`4878157..f57fff6`)<br>`git push origin 1ab275d:refs/heads/docs/v26-release-gate-20261109` | 원격 `origin/docs/v26-release-gate-20261109` fast-forward 반영 완료 | **`EXEC PASS` (실행 완료)** |
| 1 | PR #22 병합 | `orch-approval run 344a210dbd534443` (`gh pr merge 22 --merge --match-head-commit 7979253eac579db9e084fd6d6222b099adb12396`) | `2026-11-10T04:33:25Z` `MERGED`, `mergeCommit`: `63e8d578a3cec0a282254e17147ad9d91737bab9` | **`EXEC PASS` (`344a210dbd534443` 실행 완료)** |
| 2 | 새 main CI 확인 | `gh run view 42756612413` (`63e8d57`) / `gh run view 42757140198` (`8ccabea`) | PR #22 HEAD CI `42580300058` 및 PR #23 동일 트리(`7f5b353`) CI `42569948191` `SUCCESS` 확인, 머지 커밋 CI 실행 | **`EXEC PASS`** |
| 3 | PR #23 Base 변경 | `gh pr edit 23 --base main` → `gh pr diff 23 --name-only` | `tests/test_render_keepalive.py`, `V25_PRODUCTION_READINESS_AND_FULL_QA_REPORT.md` 2개 파일만 포함 확인 | **`EXEC PASS` (실행 완료)** |
| 4 | PR #23 병합 | `orch-approval run e0039b941e9f4817` (`gh pr merge 23 --merge --match-head-commit 15b87a80d3fb8890b2ccb21008fcdda49f9ee217`) | `2026-11-10T04:38:25Z` `MERGED`, `mergeCommit`: `8ccabeaa08e40cf878f051a216ac32056884e397` (트리 `7f5b353e415ed4a13c34e488f06cce6b17e172e4`) | **`EXEC PASS` (`e0039b941e9f4817` 실행 완료)** |
| 5 | PR #24 병합 | `gh pr merge 24 --merge --match-head-commit 4e00aa3c30a4f72350f799a61833dbb9e3915abb` | 최신 `main`(`8ccabea`) 기준 `MERGEABLE/CLEAN`, CI `42576144570` SUCCESS | **`e39b90d288f7456b` (`PENDING`, 이전 잡 `3321e4ff016e4b4c` `PENDING`)** |
| 6 | 최종 main 검증 | `git diff 460dcbd <FINAL_MAIN_SHA> --stat`이 비어 있음 + main CI SUCCESS | 현재 `8ccabea`와 `460dcbd` 차이는 정확히 PR #24의 2개 파일(`+160/-0`)뿐임을 확인 | PR #24 병합 후 확인 |
| 7 | Cloudflare POC PR #25 Base 전환 | `gh pr edit 25 --base main` | Base `main` 전환 완료, Cloudflare 5개 파일만 포함, `MERGEABLE/CLEAN` (병합은 별도 승인 대상) | **`EXEC PASS` (Base 전환 완료)** |
| 8 | SQLite 정책 결정 | 옵션 A(재배포 시 `/tmp` DB 초기화 수용) 또는 옵션 B | — | **사용자 결정** |
| 9 | Render 배포 | `git push origin <FINAL_MAIN_SHA>:refs/heads/submission/public-demo-deploy` (fast-forward) | 원격 배포 브랜치가 여전히 `36319c6` | **신규 요청 필요**(SHA 확정 후) |
| 10 | Cloudflare 전환 | §4.2 6·8·10·15단계 | [PR #25](https://github.com/JongHyun070105/village-coverage/pull/25) 병합, 계정 확인 | **각각 신규 요청 필요** |

