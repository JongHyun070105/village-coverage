# VillageCoverage v23 — Render Free 안정화 보고서

작성일: 2026-11-02 (KST)

## 결과 요약

- 판정: **PARTIAL**. 기능 수정과 격리 PR은 준비했고, PR CI와 병합 승인을 기다리고 있습니다.
- 공개 제출 URL 및 Render 배포 브랜치는 변경하지 않았습니다.
- main 병합, 정기 Ping 활성화, Render 배포·재시작, DB/플랜 변경은 실행하지 않았습니다.
- SQLite 보존 대상 여부가 확인되지 않아 배포 준비는 차단 상태입니다.

## 기준 상태 및 SHA

| 항목 | 확인값 |
| --- | --- |
| 시작 시 main | `61e7532ed5e00952b4eed1baba55f3d9ed293dd8` |
| 현재 origin/main 재확인 | `61e7532ed5e00952b4eed1baba55f3d9ed293dd8` |
| 기능 안정화 PR #20 head | `221a72f505cd99ceeb073b356fa4b367185d8170` |
| 운영 자동화 PR #19 head | `6537399b21f5c306af91fcdd259e98a4ff9cc1b3` |
| Render 배포 브랜치 원격 head | `submission/public-demo-deploy` = `36319c6551b5c80d3f8c4e1aaa43bc7bbf8fe6e3` |
| Web/API LIVE SHA | 직전 V22 Render 점검 기록은 두 서비스 모두 `36319c6551b5c80d3f8c4e1aaa43bc7bbf8fe6e3`; 이번 작업 중 Render Dashboard의 새 LIVE 조회는 하지 않음 |

기존 `V22_MERGE_DEPLOY_PRODUCTION_VERIFICATION_REPORT.md`의 Web/API 설정 기록은 Free, Singapore, autoDeploy 활성화입니다. 배포 브랜치 head는 이번에 `git ls-remote`로 다시 확인해 그 기록과 일치했습니다. 현재 LIVE 상태 자체는 재조회하지 않았습니다.

## 수정 내용

### 날짜·시간·개인정보 P2

- 재현 전: `오후 2시 세탁 서비스가 필요합니다.`가 개인정보 이름 탐지에 훼손되어 `02:00`으로 정규화됐고, `이번 주` 표현도 이름으로 오인되어 기간 정보가 사라졌습니다.
- 수정 후: `오후 2시`는 보존되어 `14:00`으로, `이번 주`는 `requested_period="이번 주"`로 유지됩니다. 상대 날짜는 현재 날짜로 계산하지 않습니다.
- 오전/오후 1~12시, 24시간제, 정오·자정, 이번/다음 주·주말·달, 오늘/내일/모레, 계절·반기, 월간 빈도와 일정이 포함된 문장을 회귀 테스트에 추가했습니다.
- 같은 원인의 추가 결함인 `홍길동` 비식별 누락(이름의 `동`을 행정구역 접미사로 보던 규칙), 복합 성씨, 이름 접속 조사, 라벨 이름 처리도 수정했습니다. `서울시`, `홍성`, `강남구` 및 시간 표현은 이름으로 오인하지 않는 테스트를 포함합니다.
- Fake Gemini client 계약 테스트에서 주민 원문·이름·전화번호가 원격 payload로 가지 않고, 로컬 파서가 추린 허용 서비스 ID 후보만 전달되는 것을 확인합니다. 이름이 비식별되면 원격 호출 없이 규칙 기반 fallback을 씁니다. 실제 Gemini 호출은 하지 않았습니다.

두 개의 독립 cross-provider 코드 검토에서 `홍길동` 이름 비식별 누락과 주말·계절·정오·자정 등의 추가 시간 표현 손상 가능성을 찾았습니다. MAIN이 이를 입력/출력으로 재현하고 수정한 뒤 해당 회귀 테스트를 통과시켰습니다.

### Gemini 화면 표시

- 화면은 원문과 날짜·시각·빈도를 로컬 규칙이 분석한다고 설명합니다.
- Gemini 결과는 “규칙 기반 추출 · Gemini 서비스 ID 확인”으로 표시하고, confidence도 ID 확인 보조 신호로 한정했습니다.
- 미호출·실패·fallback 결과는 “규칙 기반 초안/참고값”으로 구분합니다. “Gemini 초안” 같은 오해 가능한 표현은 제거했습니다.

### Cold Start 연결 복구

- health 요청에 단일 비행(shared in-flight) 처리를 유지하고 전체 시도 시간을 120초로 제한합니다. 한 번의 probe는 Next proxy 제한보다 짧은 55초입니다.
- 검증된 `application/json`의 `{"status":"ok"}`만 준비 완료로 봅니다. Render 기동 중 HTML 200, 계약 없는 5xx, 429, 502/503/504, 일시 네트워크 오류는 제한적으로 재시도합니다.
- 유효한 JSON 계약 오류는 실제 오류로 표시합니다. 조회/health 경로만 재시도하며 계획 생성 POST는 자동 재전송하지 않습니다.
- 연결 완료 전 재시도 버튼을 노출하지 않고, 전체 제한시간이 끝난 뒤 복구 선택지를 제공합니다.
- 합성 Playwright 테스트에서 HTML 200 → 비정형 500 → 정상 health JSON 순서를 확인했습니다. 실제 Render 절전·기동은 관측하지 않았습니다.

## Render Free Keep-Alive

### 구현 및 활성화

워크플로는 GitHub Actions이며 외부 유료 서비스나 새 Render 서비스를 만들지 않았습니다. UTC cron은 다음과 같습니다.

| UTC cron | KST 실행 |
| --- | --- |
| `55 23 * * *` | 08:55 사전 기동 |
| `5,15,25,35,45,55 0-7 * * *` | 09:05~16:55, 10분 간격 |
| `5,15,25,35,45 8 * * *` | 17:05~17:45, 10분 간격 |

대상은 기존 Web `/`, API `/health`이며, 08:55 또는 복구 검사에서 Web `/api/health`도 확인합니다. 토·일 포함입니다. 요청은 순차 GET, 무인증, 무쿠키입니다. URL allowlist, 외부 redirect 차단, 요청별 75초 timeout, endpoint별 최대 3회 시도, `Retry-After` 상한, 응답 4 KiB 제한 및 최소 정상 응답 검사를 적용합니다. 응답 본문·Location·사용자 정보는 로그에 남기지 않습니다. 실패는 서비스별로 기록하며 재배포/재시작은 하지 않습니다.

실제 UTC cron 대비 5분 초과 지연은 로그를 남기고 건너뜁니다. KST 08:55~18:00 전에도 매 요청·재시도 시각을 재확인합니다. 동시 실행은 workflow concurrency group으로 제한하고, workflow 권한은 `contents: read`뿐입니다. GitHub Actions schedule은 default branch에 병합된 뒤에만 실행됩니다. 따라서 현재 **SCHEDULER_ACTIVE: NO**입니다.

### 사용량 추정 및 관측

08:55 기동, 17:45 마지막 정시 ping, 15분 idle 종료를 가정한 **추정치**:

| 월 길이 | Web | API | 합계 |
| ---: | ---: | ---: | ---: |
| 30일 | 약 272.5 h | 약 272.5 h | 약 545 h |
| 31일 | 약 281.6 h | 약 281.6 h | 약 563.2 h |

마지막 ping이 허용 지연 5분만큼 늦고 첫 요청은 정시에 온 보수적 경우 합계는 30일 약 550 h, 31일 약 568.3 h까지 늘 수 있습니다. 모두 이 workflow의 명목 계산이며 워크스페이스 실제 사용량이나 상한이 아닙니다. 시간외 방문, 기타 Free 서비스, 재시작, Render 산정 차이는 추가될 수 있습니다.

Render Dashboard의 월간 사용량은 이번에 확인하지 않았습니다. Workspace 전체 사용량을 읽는 도구·workspace 선택이 확인되지 않았으므로 실제 수치로 추정값을 표시하지 않습니다. Render의 공식 문서도 Free 시간은 workspace 단위로 합산되고 Dashboard의 Monthly Included Usage에서 확인하도록 안내합니다. [Render Free 제한 및 사용량](https://render.com/docs/free)

운영자는 실제 workspace 합계 600 h에서 확인을 시작하고, 650 h에서 운영 방식을 재검토하며, 700 h에서는 사람이 개입해 스케줄 중단 여부를 결정하도록 문서화했습니다. Workflow는 Render 계정 사용량을 읽거나 자동 중단하지 않습니다.

GitHub는 schedule이 default branch에서 실행되고, 부하 시 지연·누락될 수 있으며, 공개 저장소는 활동이 60일 없으면 schedule이 비활성화될 수 있다고 안내합니다. [GitHub schedule 이벤트](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)

## SQLite 데이터 보존 및 배포 차단

V22 Render 사전검증은 public-demo SQLite가 OS 임시 경로에 있고 Render Free 파일시스템에는 영속 디스크가 없으며 workspace에 Render Postgres가 없다고 기록했습니다. Render 공식 문서는 Free 서비스가 15분 유휴 뒤 절전할 수 있고, 서비스가 절전·재시작·재배포되면 로컬 파일이 사라진다고 명시합니다. [Render Free 파일시스템 정책](https://render.com/docs/free)

**A. 시연 데이터:** 합성 입력, 데모용 계획·승인·이력처럼 재생성 가능한 데이터입니다. synthetic fixture가 있는 테스트는 이를 재생성하는 경로를 검증하지만, 이것만으로 운영 DB 내용까지 합성임을 증명하지 않습니다.

**B. 보존 대상:** 복구 불가능한 주민 입력, 실제 조사 자료, 보존 의무가 있는 승인 기록·운영 이력입니다. 현재 배포 인스턴스의 레코드 내용을 조회하지 않았으므로 A/B 중 어느 쪽인지 확정할 수 없습니다. B가 있거나 분류되지 않은 상태에서는 **DEPLOY_READY: BLOCKED**입니다. Keep-Alive는 낮 시간 절전 빈도를 줄일 뿐, 밤 시간·재시작·재배포 데이터 손실을 막지 않습니다. 외부 DB, 유료 플랜, 데이터 이전은 수행하지 않았습니다.

## 검증 결과

| 구분 | 결과 |
| --- | --- |
| Backend Ruff | PASS |
| Backend pytest 전체 | **726 passed, 1 skipped** (6 dependency/runtime deprecation warnings) |
| R1–R13 proposal acceptance | **113 passed; OVERALL PASS** |
| Scheduler unittest | **19 passed** |
| Scheduler Ruff / format | PASS |
| GitHub Actions YAML 파싱 | PASS |
| Frontend ESLint / TypeScript / production build | PASS (로컬 scratch checkout; production build는 webpack 경로) |
| Frontend unit | **19 passed** |
| Playwright standard | **24 passed, 1 skipped** |
| Public Demo 합성 E2E | **15 passed** |
| Responsive UI regression | **5 passed** (4 viewport coverage 포함) |
| PR CI에서 발견한 테스트 selector 충돌 | 상태 note만 선택하도록 selector를 좁힘; scratch E2E **1 passed** |
| PR #20 최종 head CI | **backend PASS / frontend PASS** — [run 41416402396](https://github.com/JongHyun070105/village-coverage/actions/runs/41416402396) |
| PR #19 코드 head CI | **backend PASS / frontend PASS** — [run 41413595920](https://github.com/JongHyun070105/village-coverage/actions/runs/41413595920) |
| Gemini live call | SKIP — fake client 테스트만 사용 |
| Render public cold start / 새 코드 브라우저 E2E | NOT_VERIFIABLE — 배포 승인 전, 실 서비스 wake 요청도 하지 않음 |
| 현재 Render usage / 최신 LIVE Dashboard 확인 | NOT_VERIFIABLE — Render workspace를 선택하지 않음 |

PR #19의 workflow·코드 head CI와 PR #20의 수정된 최종 head CI는 backend·frontend 모두 통과했습니다. PR #20 최초 frontend CI는 피드백 note의 다중 locator 때문에 실패했지만, selector를 수정한 뒤 단독 E2E와 최종 전체 CI가 통과했습니다. 이 보고서를 PR #19에 포함하면 GitHub가 문서 포함 최종 head CI를 새로 실행합니다. 최신 상태는 각 PR의 [#19 checks](https://github.com/JongHyun070105/village-coverage/pull/19/checks), [#20 checks](https://github.com/JongHyun070105/village-coverage/pull/20/checks)에서 확인합니다.

## PR 및 변경 활성화 게이트

- [PR #20 — 기능 안정화](https://github.com/JongHyun070105/village-coverage/pull/20)
- [PR #19 — Render Free Keep-Alive](https://github.com/JongHyun070105/village-coverage/pull/19)
- PR #20 병합 및 PR #19 병합은 별도 사용자 승인 대상입니다. PR #19 병합은 실제 정기 GET ping을 활성화합니다.
- Render 배포 브랜치 push, 재배포·재시작, 환경변수 변경, DB 변경은 하지 않았습니다.
- PR 병합 승인이 나더라도 SQLite 보존 대상 여부가 확인되기 전에는 Render 배포를 진행하지 않습니다.

## 최종 상태

- **CODE_VERIFIED:** YES
- **CI_VERIFIED:** YES — PR #19/#20의 변경 head CI 통과; 보고서가 포함될 PR #19 후속 CI는 checks 링크에서 확인
- **SCHEDULER_READY:** YES — 코드·단위 검증 통과
- **SCHEDULER_ACTIVE:** NO — PR #19 미병합
- **DEPLOY_READY:** BLOCKED — SQLite 데이터 보존 여부 미확인
- **DEPLOY_VERIFIED:** NO
- **PRODUCTION_E2E_PASS:** NOT_VERIFIABLE
- **OVERALL:** PARTIAL
