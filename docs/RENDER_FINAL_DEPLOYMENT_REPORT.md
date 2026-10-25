# Final Render deployment report 2026-10-24

**NOT_DEPLOYED / RELEASE_BLOCKED.** This run has not updated main or submission/public-demo-deploy and has not triggered Render. User conditional GO remains subject to the release gates. No new approval for an ordinary demo update is being requested; the missing requirement is verified operational access and evidence.

## Deployment preflight

| Service | Historical successful GitHub record | Successful timestamp UTC | Render record |
|---|---|---|---|
| API | 7b696499c6c4b59fd613866faa89c1afe8934398 | 2026-10-10T12:52:41Z | [dep-db538mbrjlhs73acg680](https://dashboard.render.com/web/srv-db3oh84s728c73fl4vlg/deploys/dep-db538mbrjlhs73acg680) |
| Web | 7b696499c6c4b59fd613866faa89c1afe8934398 | 2026-10-10T12:50:52Z | [dep-db538mbrjlhs73acg630](https://dashboard.render.com/web/srv-db3oh84s728c73fl4vl0/deploys/dep-db538mbrjlhs73acg630) |

The GitHub deployment status API was queried directly. These are historical success records, not proof of today's running image SHA, Live state, current linked branch or rollback availability. Current deployed_sha is null. Render Dashboard could not be opened: computer-use returned no browsers/apps and an app-server error; attempting the in-app browser returned Browser is not available: iab. No Render connector, CLI, configured Render environment credential name, or normal Render CLI config was available. Secret values were not read.

Current Render logs, failed instances, environment-variable names/settings, live build/runtime status and current tracked branch are **NOT_VERIFIABLE**. Tracked render.yaml is STATIC evidence only: two free Singapore services, Python 3.12.10, Node 22.18.0, one API worker, health paths /health and /, public-demo cookie Secure=true, same-origin proxy. Service recreation, paid plans and secret changes were not attempted.

## Low-volume baseline HTTPS observation

Exactly one request per listed endpoint; no retry loop and no load test. No cookie value was saved. These requests occurred before any new deployment.

| Endpoint | HTTP | Content-Type | elapsed seconds |
|---|---|---|---:|
| `https://villagecoverage-public-demo-api.onrender.com/health` | TIMEOUT | NOT_VERIFIABLE | 65.24 |
| `https://villagecoverage-public-demo-api.onrender.com/api/health` | TIMEOUT | NOT_VERIFIABLE | 65.081 |
| `https://villagecoverage-public-demo-web.onrender.com/` | 200 | text/html; charset=utf-8 | 43.438 |
| `https://villagecoverage-public-demo-web.onrender.com/api/regions` | 200 | application/json | 29.924 |
| `https://villagecoverage-public-demo-web.onrender.com/api/schedules` | 200 | application/json | 0.36 |

Web regions/schedules responses parsed as JSON and issued a demo-session cookie; Web / did not. API health cookies and status could not be observed due to timeout. Request latency is not proof of the cold-start mechanism or an uptime guarantee. The web request took 43.438 seconds and regions 29.924 seconds; both API health requests exceeded 65 seconds.

## Change and persistence review

Compared with origin/submission/public-demo-deploy: next.config.ts, render.yaml, database schema/database.py and public_demo.py are unchanged. Production Python lock changes are restricted to security updates for certifi 2026.10.23, opentelemetry-api 1.45.1 and Pillow 13.0.0; ReportLab remains 4.5.1. Runtime changes include the security dependency pins, bounded GET recovery, mobile Decision Memo wrapping, temporary-plan-loss notice, test-only routing fixtures and the narrowly scoped sparse hub symmetry fix documented in the release audit. Official Office binaries are additions from the original package and byte-identical to that branch. No new migration, DB reset, environment setting or allowlist relaxation was introduced.

Render Free has an ephemeral filesystem. Its local SQLite changes can disappear after redeploy/restart/spin-down; no existing SQLite was directly deleted, reset or restored. [Official Free limits](https://render.com/docs/free).

## Rollback plan and stop gate

[Official rollback documentation](https://render.com/docs/rollbacks) requires a retained successful build artifact. Free service documentation permits rollback to the two most recent previous deploys. A historical successful SHA alone does not prove the relevant build artifact is retained.

1. With an existing authenticated Dashboard session, verify both service IDs, linked repo/branch, current deploy SHA, free compute and latest two successful deploys. Inspect masked env settings and sanitized logs without revealing values.
2. Confirm that the intended successful build has an available Rollback action for each service, and record its exact deploy ID and SHA before any update.
3. Rollback in Dashboard reuses the selected artifact and disables auto-deploys. API rollback does not disable them. No rollback has been executed in this task.
4. If retained-artifact rollback is unavailable, prepare and test an ordinary history-preserving revert/recovery commit before deploying. Never force-push/reset, restore an unverified SQLite image or delete user data.
5. The prior 7b696499 runtime uses affected Next/React versions. Reverting to it can restore prior behavior but does not satisfy the new security gate; it is not labeled a secure final recovery version.

**Rollback readiness: NOT_VERIFIABLE. Deployment stays blocked.** This is an external access/evidence blocker, not a missing human GO. No operational changes occurred, so no rollback is currently necessary.

## Final remote journey and captures

Latest candidate API/Web SHA, 16-step browser journey, remote A/B isolation, UI decline/replan, Decision Memo, PDF/CSV and four remote viewports are **SKIP / NOT_VERIFIABLE for the candidate**. No new public capture or video was fabricated. Historical October 13 browser artifacts remain unchanged and cannot establish deployment of this candidate. Local Chromium results are reported separately.

## 재개 시 반드시 남길 증거

- API/Web 각각 서비스 ID·현재 추적 브랜치·현재 SHA·마지막 Live 시각·health 경로·free plan·auto-deploy 방식
- 직전 정상 deploy ID와 retained rollback 버튼/가용 build artifact, 비밀 값이 없는 env 설정/로그 검토 결과
- 최종 RC HEAD와 성공 CI run head 일치 및 main/deploy branch의 조상 관계
- 배포 started/build success/runtime started/health passing/Live/실제 SHA를 서비스별로 확인
- 새로운 A/B Chromium 세션으로 UI 불참·v2·메모·PDF/CSV·권한 없는 접근 404 및 4개 뷰포트 검증
- 원격 캡처별 시각·정확한 배포 SHA·공개 URL·테스트 유형·합성 고지·성공 여부. 쿠키/키 값은 저장 금지

현재 조건부 GO가 이 정상 공개 업데이트를 이미 승인했다. 별도 유료 자원, 키 변경, 파괴적 작업 또는 게이트 예외는 포함하지 않는다.

## 20시 재개 관측: 후보 배포와 분리

[remote-resume-health.json](../artifacts/release/evidence-20261024/remote-resume-health.json)에 2026-10-24 20:30–20:32 KST의 단발 GET 5개를 추가했다. 기존 timeout 기록은 위 표에 그대로 보존한다.

| 경로 | HTTP | Content-Type | 응답 초 | 세션 발급 |
|---|---:|---|---:|---|
| API /health | 200 | application/json | 42.513 | 없음 |
| API /api/health | 200 | application/json | 42.528 | 없음 |
| Web / | 200 | text/html | 42.569 | 없음 |
| Web /api/regions | 200 | application/json | 42.888 | 있음 |
| Web /api/schedules | 200 | application/json | 0.487 | 있음 |

네 JSON은 정상 파싱됐다. 세션 속성은 HttpOnly=true, Secure=true, SameSite=Lax, Path=/api, Max-Age=1800이다. 쿠키 값·키·실제 사용자 데이터는 저장하지 않았다. 첫 응답 지연은 관측일 뿐 cold-start 원인 확정이 아니다.

현재 source CI는 9a8c4be / run 40073124556 성공으로 갱신됐다. 그러나 Render tool/인증 브라우저가 여전히 없고 iab 생성도 실패했다. 실제 API/Web SHA·추적 branch·Live·logs·env·retained rollback 확인은 NOT_VERIFIABLE이다. 이번 후보 배포, main 갱신, deploy branch 갱신은 미실행이며 복구 작업도 필요하지 않다. 현재 접속 가능하다는 사실을 후보 배포 완료나 16단계 시연 PASS로 표시하지 않는다.
