# 공개 테스트 URL 배포 기록

## 2026-10-12 current status

상태: PREVIOUSLY_DEPLOYED · CURRENT_HTTPS_VERIFIED (GET only) · CURRENT_BROWSER_FLOW_VERIFIED=NOT_VERIFIABLE · 신규 배포 NOT_DEPLOYED

- Web URL: https://villagecoverage-public-demo-web.onrender.com
- API health URL: https://villagecoverage-public-demo-api.onrender.com/api/health
- GitHub deployment records: web/API 모두 success, source ref submission/public-demo-deploy, SHA 7b696499c6c4b59fd613866faa89c1afe8934398.
- Manifest at that SHA: Next.js and eslint-config-next 16.3.7; React and React DOM 19.2.8.
- One low-frequency check on 2026-10-12 returned web HTTP 200 in 22.685s and API health HTTP 200 in 52.644s; TLS verification succeeded.
- This confirms URLs and a past deployment, not the entire judge browser journey, stable availability, or the unmerged 16.3.8 patch.
- The 16.3.8 security branch is separate. This work did not merge, push the deployment branch, change Render, or deploy.

The historical configuration snapshot below predates the observed deployment and its old “expected URL / no deployed URL” status is superseded. Its technical constraints remain planning context only.

## 구성과 임시 데이터

Render has one Free Node.js frontend and one Free Python API. The frontend runs the Next standalone server; the API runs one Uvicorn worker. Both use platform HTTPS. The public demo uses synthetic/public data and temporary SQLite files, not a paid persistent database. The database is ephemeral: a restart, redeploy, or spin-down can erase plans. The UI now states this possibility. Public demo sessions expire after 30 minutes idle.

Render Free web services spin down after 15 minutes of inactivity and may take about one minute to wake. One GET response in this audit took 52.644 seconds, but this is not a guaranteed maximum or proof of a cold start. API error UI provides a human-readable status and manual retry; no continuous polling or keep-alive was added.

## Unverified browser journey

The following remote browser steps have not been run in this audit:

- [ ] Open web root in a fresh browser and reach the Dashboard.
- [ ] Refresh and open a direct route.
- [ ] Compare four scenarios.
- [ ] Generate a plan, record provider decline, and replan.
- [ ] Open a plan and its Decision Memo/export.
- [ ] Observe session cookie flags on the live host.
- [ ] Verify an API cold-start failure, user-facing retry, and later recovery.
- [ ] Confirm session expiry / plan-loss notice through a full judge session.

Local isolated Playwright tests are not remote production evidence.

## Do not conflate these states

URL_EXISTS: host is known.
PREVIOUSLY_DEPLOYED: GitHub records a successful deployment at a particular SHA.
CURRENT_HTTPS_VERIFIED: one low-frequency HTTPS request returned 200.
CURRENT_BROWSER_FLOW_VERIFIED: full remote user journey; not verified here.
DEPLOYED_SHA_VERIFIED: deployment records identify SHA 7b696499c6c4b59fd613866faa89c1afe8934398.
READY_FOR_SUBMISSION: false until current browser journey, final materials, Q&A review and applicant approval are complete.

No Render deployment or configuration update was performed in this audit. Render Free service limits: [official Render Free documentation](https://render.com/docs/free).
