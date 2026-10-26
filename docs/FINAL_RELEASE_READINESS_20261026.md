# Final Release Readiness — 2026-10-26

## Final release gate — 2026-10-26 11:17 UTC

The pre-deployment gate notes below are preserved; this section records the final live state.

### A. Render

Render CLI는 설치되지 않았다. Render MCP 인증은 성공했고 workspace `My Workspace` (`tea-db3ogj49v7es73dspep0`)와 API/Web 서비스 ID를 실제 목록에서 확인했다. 두 서비스는 Free, Singapore, `submission/public-demo-deploy`, Auto Deploy yes다.

- API live SHA `1fb24d14380bebb09260a7f0b69a9d33e20e6d71`; deploy `dep-dbfjav5g1s2s73adt580`. PR #7 was docs-only; runtime API code is unchanged from `5d51954a`.
- Web live SHA `27d5142de233011e35fff24ba8870d5de4205c23`; deploy `dep-dbfgp1cs728c73dhbtm0`. Web 파일 변경은 없어 이전 UI deploy가 유지된다.
- 직전 API deploy `5d51954a` (`dep-dbfilqs9v7es73dgpj90`), 그 이전 `49c41305`, `420a3b78` deploy ID가 Render 기록에 남아 있다. Web의 직전 deploy 후보는 `420a3b78` (`dep-dbeukbuk1f9s73fm9lkg`)다. 롤백은 실행하지 않았고 복구 훈련도 하지 않았다.

### B. 원인과 성능

과거 브라우저 520은 `POST /api/schedules`, 40.951초, Cloudflare HTML이었다. 겹친 FastAPI 201과 같은 요청인지 증거가 없어 root cause는 `UNKNOWN`이다. request correlation event가 운영에 없던 이유는 Uvicorn console handler/root propagation 설정이었다. 이를 `uvicorn.error` handler 계층에 연결하고 실제 Uvicorn config 테스트와 배포 후 브라우저/API 로그 matching으로 수정했다.

Local 5M single-sample API flow `27.634s → 21.394s`(22.6%), minimum analysis `14 solves / 5.751s → 1 solve / 0.054s`. Render Free 4M/5M compare는 각각 92.787s/87.716s였다. 정책 POST는 약 15.4–28.9초였다. 4정책 실행 중 API CPU는 분 평균 98.9%까지 관측돼 load margin이 작다. p50/p95를 말할 표본은 없다.

### C–E. 제품·QA·배포

- Backend: latest main CI PASS; local `598 passed, 1 skipped`, Ruff/compileall PASS.
- Previous full suite before the logger routing fix: `597 passed, 1 skipped`; latest code then added one actual-Uvicorn-handler regression.
- Frontend: latest main CI PASS; PR exact-head CI PASS including lint/typecheck/build, standard/Public Demo Playwright and four viewport regression.
- R1–R13 mapped acceptance is included in Backend CI and passed.
- Public Render 4M journey 16/16 PASS; 5M compare 4/4 PASS; session isolation, replan, memo and exports passed on the recorded `27d5142` journey. Request ID response/API log match was verified with a non-computing 422 request after runtime logger deploy `5d51954`; the current `1fb24d1` API deploy is docs-only and did not repeat that diagnostic.
- PR #4 scenario-recovery changes merged as `27d5142`; PR #5 initial logger level follow-up merged as `49c4130`; PR #6 Uvicorn logger routing merged as `5d51954`; PR #7 release evidence docs merged as `1fb24d1`. Main CI `40311552879` passed at exact merge SHA `1fb24d14380bebb09260a7f0b69a9d33e20e6d71`.
- `submission/public-demo-deploy` was advanced by normal fast-forward pushes; no manual Render deploy/restart was issued. API auto-deployed to `1fb24d1` because the API tracks repository root; Web remained at `27d5142` because `frontend/` did not change.
- After the API auto-deploy, API `/health` GET returned 200 in 0.344s. Web root GET timed out once after 20s with no response, then returned 200 in 0.358s on one bounded retry; the initial timeout cause is unknown. No solver POST was made after the docs-only deploy. The 11:11–11:17 UTC idle metric window peaked at API `0.0262 / 0.15 vCPU`, `120.7 / 512 MiB`; Web `0.0011 / 0.15 vCPU`, `102.8 / 512 MiB`. Request-level logs/HTTP metrics were empty.

### Gate table

| Gate | Result | Basis / limitation |
|---|---|---|
| RENDER_AUTHENTICATED | `EXEC PASS` | Authenticated Render MCP; CLI not installed |
| ROOT_CAUSE_CONFIRMED | `NOT_VERIFIABLE` | Historical 520 cannot be correlated retroactively |
| PERFORMANCE_IMPROVED | `EXEC PASS / SINGLE SAMPLE` | Local minimum analysis 14→1 solve; remote remains CPU-bound |
| SCENARIO_4_OF_4_PASS | `EXEC PASS` | 4M full journey and 5M compare |
| MINIMUM_ANALYSIS_PASS | `EXEC PASS / NOT_PROVEN VALUE` | Endpoint 201; returned minimum-cost values null/NOT_PROVEN |
| POST_SAFETY_PASS | `EXEC PASS / BOUNDED` | No automatic POST retry; ambiguous submit guard and A/B isolation passed. No general Idempotency-Key contract or duplicate replay test |
| UI_QA_PASS | `EXEC PASS` | Local regression + remote 4 viewport check; keyboard/screen-reader audit remains limited |
| FULL_REGRESSION_PASS | `EXEC PASS` | latest main CI including backend/frontend/R1–R13/Playwright/responsive |
| CI_VERIFIED | `EXEC PASS` | `40311552879`, exact main SHA `1fb24d1` |
| DEPLOYED_VERIFIED | `EXEC PASS` | API live `1fb24d1` (docs-only over runtime `5d51954`); Web live `27d5142`, no frontend code changed |
| REMOTE_PRODUCT_PASS | `EXEC PASS / SYNTHETIC` | Core 4M flow 16/16 and 5M compare 4/4; not a load test |
| SUBMISSION_TECHNICALLY_READY | `PASS_WITH_LIMITATIONS` | Suitable for guided synthetic demo; not field or production service readiness |

### F. Release decision and remaining limits

**GO:** guided public synthetic demo for the competition, with the limitations above displayed. **NO-GO:** real municipal service, real resident-impact claims, high-concurrency use, proven numeric minimum budget, or claims of live Gemini execution.

Artifacts: `artifacts/qa/remote_scenario_acceptance_20261026.json`, `artifacts/qa/product_quality_acceptance_20261026.json`, `artifacts/performance/scenario_optimization_before_after_20261026.json`, `artifacts/release/final_product_release_20261026.json`. Browser screenshots and SHA-256 manifest are under `artifacts/qa/render_public_demo_journey_20261026_v2_0/`.

Checkpoint: repository main and API live SHA `1fb24d14380bebb09260a7f0b69a9d33e20e6d71`; exact main CI `40311552879`; API runtime code is unchanged from `5d51954a`; Web and full browser journey screenshots are at `27d5142`. No production dataset reset or rollback occurred. The final post-deploy check was GET-only; no full solver journey was repeated.


> **Historical pre-deployment snapshot:** The sections below preserve the earlier NO-GO checkpoint and are superseded by the final release gate above.

## Pre-deployment decision — historical, superseded

**NO-GO for production release at this checkpoint.** Local product gates and CI at PR head `38f9af29872e97e0c0b796c2a20878bc7950b555` pass, but the updated code has not been deployed or accepted on Render. No production deploy or restart has been executed.

## Pre-deployment gate status — historical, superseded

| Gate | Status | Evidence / limitation |
|---|---|---|
| Render authentication | `EXEC PASS` | Render MCP workspace list confirmed `My Workspace` / `tea-db3ogj49v7es73dspep0`; CLI is not installed. |
| Current API/Web identity | `EXEC PASS` | Both Free services track `submission/public-demo-deploy`; current live SHA remains `420a3b78…`. |
| HTTP 520 root cause confirmed | `NOT_VERIFIABLE` | Browser got Cloudflare 520 after 40.951s; adjacent FastAPI 201 cannot be correlated in historical logs. |
| Local performance improved | `EXEC PASS` | 5M end-to-end local API flow: 27.634s historical → 21.394s current, one sample each; minimum analysis 14 → 1 solver call. |
| Render Free performance | `NOT_VERIFIABLE` | No new remote requests; local host does not emulate 0.15 vCPU or proxy behavior. |
| 4-policy local results | `EXEC PASS` | Production standalone browser E2E created 4/4 cards at 5M; direct API profile and minimum analysis returned 201 at both 4M and 5M. |
| Minimum analysis ownership / condition checks | `EXEC PASS` | Matching plan reused; mismatched budget and unowned plan rejected; no duplicate save in reuse path. |
| POST safety / partial results | `EXEC PASS` | Injected 520/504 and explanation failure preserved known plans, blocked unsafe full rerun, and sent no POST retry. |
| Public session isolation | `EXEC PASS` for existing local suite | Public Demo E2E retained three-browser isolation checks. New code is not yet remotely deployed. |
| UI accessibility / responsive | `EXEC PASS` | Keyboard/focus tests and four target viewport regressions passed. |
| Full backend and frontend regression | `EXEC PASS` | Backend 596 passed/1 existing skipped; R1–R13 112 passed; standard E2E 14/1 existing remote-only skip; public E2E 6; responsive 5. |
| Dependency security audit | `EXEC PASS` | npm production audit: 0 vulnerabilities; Python production pip-audit: no known vulnerabilities. |
| Security diff review | `EXEC PASS` | Exact diff `56cf8f4..38f9af2`; no reportable candidates. Render environment values remain unverified and were not exposed. |
| Final-head GitHub CI | `EXEC PASS` | Run `40285077567` completed successfully on exact head `38f9af29872e97e0c0b796c2a20878bc7950b555`; Backend and Frontend jobs passed, including R1–R13, Playwright, and responsive checks. |
| Render deploy and remote acceptance | `SKIP` | No deployment. Existing Live SHA/deploy IDs preserved; no rollback performed. |
| Submission technical readiness | `NOT_VERIFIABLE` | New version's public URL journey, current deployment SHA, and remote session isolation remain unverified. |

## Pre-deployment evidence snapshot — historical, superseded

- Branch: `fix/scenario-comparison-520-20261026`
- PR head with complete CI: `38f9af29872e97e0c0b796c2a20878bc7950b555`
- Final-head CI: [run 40285077567](https://github.com/JongHyun070105/village-coverage/actions/runs/40285077567), success
- Implementation commit: `12494aa` (minimum analysis reuse, correlation, write recovery, tests)
- PR: [#4](https://github.com/JongHyun070105/village-coverage/pull/4), open against `main`
- Baseline Live SHA: `420a3b78b3e7f5b52100e6f20f2de14aa31a3a81`
- Current API Live Deploy ID: `dep-dbeukbuk1f9s73fm9lgg`
- Current Web Live Deploy ID: `dep-dbeukbuk1f9s73fm9lkg`

Next technical release step is to re-check the tracked submission branch, rollback path, and release gates, then merge PR #4 and advance the existing auto-deploy branch under the user's conditional release authorization. After auto deploy, verify both service Live SHAs and run a limited remote acceptance journey. Do not claim `ROOT_CAUSE_CONFIRMED` without matching correlation evidence.


## 2026-10-26 07:51 UTC pre-deployment gate refresh

- PR #4 remains open and mergeable; exact head `1c5d33caf23b94e0575508a81bd3510076360240`; final-head CI `40286471102` completed successfully for Backend and Frontend.
- Render MCP authenticated `My Workspace` (`tea-db3ogj49v7es73dspep0`). API `srv-db3oh84s728c73fl4vlg` and Web `srv-db3oh84s728c73fl4vl0` are Free, track `submission/public-demo-deploy`, and have Auto Deploy enabled. Current live SHA remains `420a3b78b3e7f5b52100e6f20f2de14aa31a3a81`; deploy IDs remain API `dep-dbeukbuk1f9s73fm9lgg`, Web `dep-dbeukbuk1f9s73fm9lkg`. The prior live release is the identified rollback candidate; no rollback drill was performed.
- Historical 520 trace, application logs, and minute-level resource metrics were rechecked; the 201 correlation and originating failure remain unknown. Render HTTP request logs/latency metrics were not returned.
- Local backend/frontend/R1–R13/Playwright/responsive and dependency/security checks recorded for the current code remain passing. No schema migration or destructive database operation is present in the PR diff.
- **Decision before deployment:** merge and normal Auto Deploy are authorized by the user’s conditional release instruction because local and exact-head CI gates pass and the prior live deploy is identified. Root cause, Render-after-change performance, new-version remote scenarios, and submission readiness remain unverified until after deployment and bounded remote acceptance. No deployment or restart has yet been issued.
