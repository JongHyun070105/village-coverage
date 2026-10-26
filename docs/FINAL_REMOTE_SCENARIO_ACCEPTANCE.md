# Final Remote Scenario Acceptance

**기록:** 2026-10-26 14:37 KST
**기존 배포 SHA:** `420a3b78b3e7f5b52100e6f20f2de14aa31a3a81`
**검증 코드 SHA:** `ad2a4d1eba8932e810f9acb94da7817caf9a9fce`
**원격 재검증 상태:** `USER_CONFIRMATION_REQUIRED` (Render workspace 선택 전 로그/metrics 호출을 보류함)

## 배포 및 원격 증거

- 기존 제출 배포 기록: API `srv-db3oh84s728c73fl4vlg`, deploy `dep-dbeukbuk1f9s73fm9lgg`; Web `srv-db3oh84s728c73fl4vl0`, deploy `dep-dbeukbuk1f9s73fm9lkg`.
- 기준 작업 지시에서는 두 service가 SHA `420a3b78…`로 Live였고 rollback하지 않은 상태였다. 이번 코드 변경은 배포하지 않았으며 현재 Live 상태를 다시 조회하지 않았다.
- 저장된 실패 trace: `/api/schedules` POST에서 Cloudflare 형식 520, 40.951초, 예산 4,000,000원. 브라우저 후속 요청은 없었다.
- FastAPI의 201 로그는 같은 시간 구간에 있으나 request correlation이 없어 실패 요청과 동일하다고 볼 수 없다.
- 과거 별도 원격 시연의 16/16 기본 journey 성공 기록은 보존한다. 해당 journey와 시나리오 실패는 서로 다른 결과다.
- 과거 4정책 compare journey는 4개 schedule 응답이 각각 201이었으나, minimum-coverage analysis가 30.151초 뒤 500이었다. 이 기록은 16/16 기본 journey를 소급해 무효화하지 않는다.

## 수락 항목

| 항목 | 결과 |
|---|---|
| 새 버전 API/Web 동일 SHA Live | `SKIP` — 배포하지 않음 |
| Render rollback 검증 | `NOT_VERIFIABLE` — 서비스 조회 보류 |
| 원격 4정책 4/4 | `FAIL` — 기존 저장 검증에서 HTTP 520, 현재 코드 원격 재실행 미수행 |
| 원격 minimum-coverage analysis | `FAIL` — 기존 별도 journey에서 HTTP 500 기록 |
| 기존 16/16 기본 journey | `EXEC PASS` — 기존 증거 유지, 재실행하지 않음 |
| 이번 코드의 로컬 4정책 4/4 | `EXEC PASS` — 500만원 합성 fixture, production standalone 경유 |
| 이번 코드의 remote session isolation | `NOT_VERIFIABLE` — 원격 재실행 미수행 |
| 배포/rollback | `SKIP` — 원격 원인 및 배포 게이트 미확정 |

## 제출 판정

현재 상태는 `PARTIAL / NO-GO FOR TECHNICAL READY`다. 로컬 계산과 오류 복구 테스트는 통과했으나 `ROOT_CAUSE_CONFIRMED`, `CI_VERIFIED`, `DEPLOYED_VERIFIED`, `REMOTE_SCENARIO_4_OF_4_PASS`, `SESSION_ISOLATION_PASS`, `SUBMISSION_TECHNICAL_READY`는 아직 충족되지 않았다. 제출 영상 촬영과 공개 URL 최종 승인은 실제 Render 4정책 비교 재검증 전까지 차단한다.

## 2026-10-26 Release v2.0 checkpoint

- Render MCP 인증 및 workspace 조회: `EXEC PASS`; `My Workspace` / `tea-db3ogj49v7es73dspep0`가 기대 ID와 일치했다. CLI는 설치되어 있지 않았다.
- API/Web 서비스 식별: `EXEC PASS`; 두 서비스는 Free, auto deploy on, `submission/public-demo-deploy`를 추적한다. 현재 양쪽 Live SHA는 기존 `420a3b78b3e7f5b52100e6f20f2de14aa31a3a81`이며 Deploy ID는 API `dep-dbeukbuk1f9s73fm9lgg`, Web `dep-dbeukbuk1f9s73fm9lkg`다.
- 신규 버전 원격 실행: `NOT_VERIFIABLE`; 새 코드 배포 또는 원격 POST를 실행하지 않았다. 기존 16/16 성공 기록과 이전 520/500 실패는 과거 evidence로 보존했다.
- 이번 로컬 production standalone: 500만원 4정책 모두 201과 카드 4개, minimum analysis 성공. HTTP 520/504, 설명 GET 실패, 중복 실행 방지 테스트도 통과했다.
- 현재 Render CPU/메모리 확인은 분당 표본만 제공했다. API `0.056–0.133 / 0.15 vCPU`, `291–302 / 537 MB`; Web `0.009–0.038 / 0.15 vCPU`, `129–138 / 537 MB`. request-level latency/status 및 CPU 순간 peak는 `NOT_VERIFIABLE`이다.
- Rollback 실행/복구 리허설은 `SKIP`. 이전 Live deploy 식별자는 확인됐지만 원격 rollback을 실행하지 않았다.

따라서 배포 이후에만 판정할 수 있는 `REMOTE_SCENARIO_4_OF_4_PASS`, `DEPLOYED_VERIFIED`, `REMOTE_PRODUCT_PASS`, `SUBMISSION_TECHNICALLY_READY`는 여전히 `NOT_VERIFIABLE`이다. 이 checkpoint의 전체 JSON은 `artifacts/qa/remote_scenario_acceptance_20261026.json`이다.

## 2026-10-26 07:51 UTC pre-deployment verification refresh

- Render MCP workspace `My Workspace` / `tea-db3ogj49v7es73dspep0` was present. API ID `srv-db3oh84s728c73fl4vlg` and Web ID `srv-db3oh84s728c73fl4vl0` are Free and track `submission/public-demo-deploy` with Auto Deploy enabled. The shorter Web ID written in an earlier checkpoint was incorrect.
- Both services are still Live at `420a3b78b3e7f5b52100e6f20f2de14aa31a3a81`; API deploy `dep-dbeukbuk1f9s73fm9lgg`, Web deploy `dep-dbeukbuk1f9s73fm9lkg`. The prior deploy is the identified rollback candidate. No deploy, restart, or rollback was executed during this read-only recheck.
- GitHub Actions `40286471102` passed on exact PR head `1c5d33caf23b94e0575508a81bd3510076360240` (Backend and Frontend).
- The preserved browser trace shows a 40.951-second Cloudflare 520 at 22:19:14.404Z. API app logs show an uncorrelated `201 Created` at 22:19:31.693Z. Web `ECONNRESET` was an earlier `/api/minimum-coverage/analysis` at 22:17:33.309Z. Root cause and API 201 correlation remain `UNKNOWN`.
- Historical resource metrics were minute-level: API CPU 0.056–0.073 vCPU in the two request minutes (limit 0.15), interval maximum 0.133 vCPU; API memory 277–288 MiB of 512 MiB. Web CPU maximum 0.038/0.15 vCPU, memory 123–131 MiB of 512 MiB. Request logs and HTTP request metrics returned no data.
- New code has not yet been deployed; remote 4-policy comparison, minimum analysis, provider replan, exports, and session isolation remain pending. This refresh does not mark remote acceptance or submission readiness as PASS.
