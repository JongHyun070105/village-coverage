# Frontend Security Audit — Next.js 16.3.8

Audit date: 2026-10-12 (UTC)
Baseline: `origin/main` at `4f2089e9da83308c011fc9cafb306f18baeca8f6`
Patch branch: `security/nextjs-16-3-8-review-rerun`
Source diff SHA-256: `6b6d1e0fe081db5e0b38dfb5d7086969c8d67a571e71101ed769fd923c55d29a`

## Decision

**Patch preparation: `PATCH_PARTIAL`. Deployment: `NOT_DEPLOYED`.** The requested 16.3.8 dependency patch and regression work are preserved on the security branch. Production dependencies have no High or Critical npm advisories. Tests, build, standalone-browser checks, and R1–R13 pass. The development dependency tree still has five npm High findings through the ESLint `braces` chain. The backend tests and source-scoped Ruff checks pass; an unfiltered `ruff check .` also inspected a Python example shipped inside the untracked Node runtime under `artifacts/security/run-tmp` and reported three findings there (`F401` once and `F841` twice). The repo-wide scan excluding that generated runtime and the backend source scan both pass. This scope issue is recorded rather than hidden.

`PATCH_PARTIAL` reflects the reported broad Ruff result and remaining development advisory. The patch is committed and pushed only to this security branch; it was not merged to `main` or deployed to Render.

## Dependency and advisory status

| Package/audit | Before | Current | Result |
|---|---:|---:|---|
| `next` | 16.3.7 | 16.3.8 | Patched |
| `eslint-config-next` | 16.3.7 | 16.3.8 | Patched |
| `react` / `react-dom` | 19.2.8 / 19.2.8 | unchanged | No unrelated upgrade |
| All npm High | 6 | 5 | Development ESLint dependency graph |
| All npm Critical | 0 | 0 | None reported |
| Production High / Critical | 1 / 0 | 0 / 0 | Production audit clear |

`npm ci` and `npm ls next eslint-config-next react react-dom --depth=0` verified the lockfile resolves exactly to Next.js 16.3.8, eslint-config-next 16.3.8, React 19.2.8, and React DOM 19.2.8. The current full audit exits nonzero because the High development advisory remains. `npm audit --omit=dev` exits successfully with no production findings. No `npm audit fix --force` was run.

The remaining advisory is `GHSA-vfj7-8cjw-p6xm` (`braces <=3.0.3`) through `eslint-config-next -> @next/eslint-plugin-next -> fast-glob -> micromatch -> braces`. No compatible fix was identified; npm's suggested ESLint downgrade was not applied. Raw before/after audit reports are retained in `artifacts/security/npm_audit_*.json`.

The official Next.js post says an additional security update is scheduled for 2026-10-14 and that affected versions and fixes will be published with it. Those details are not yet available, so the status is `UPSTREAM_ADVISORY_PENDING`; no speculative package change was made. [Official Next.js announcement](https://nextjs.org/blog/upcoming-nextjs-security-update-october-2026).

The stable 16.3.8 release includes the previously recorded framework fixes for Image Optimization SSRF, metadata-image route information disclosure, SSG/ISR cache issues, Draft Mode leakage, and the development MCP endpoint. See the [Next.js 16.3.8 release](https://github.com/vercel/next.js/releases/tag/v16.3.8).

## Verification

| Check | Result | Evidence |
|---|---|---|
| Backend pytest | `EXEC PASS` — 585 passed, 1 skipped | Fresh full run |
| Ruff source | `EXEC PASS` — `backend scripts tests` | Fresh run |
| Ruff repo excluding generated Node runtime | `EXEC PASS` | Fresh run |
| `ruff check .` without exclusion | `FAIL` on three findings (`F401` once, `F841` twice) in the generated Node `lldb_commands.py` only | Untracked `artifacts/security/run-tmp` vendor file; no project source finding |
| Python compileall | `EXEC PASS` | Fresh run |
| Frontend lint / typecheck | `EXEC PASS` / `EXEC PASS` | Fresh run |
| Node 22.18.0 production build | `EXEC PASS` | Next.js 16.3.8 standalone build |
| Existing frontend E2E | `EXEC PASS` — 17/17 | 12 standard + 5 Public Demo |
| R1–R13 acceptance | `EXEC PASS` — 112/112 | `artifacts/qa/r1-r13-security-completion-20261012T061759Z.json` |
| UI regression | `EXEC PASS` — 2 tests over the four requested viewports | Playwright standalone-server configuration |
| Standalone CSS/JS | `EXEC PASS` — requests returned 200 | Fresh Node 22.18.0 standalone-browser run |
| Same-origin API/session | `EXEC PASS` | `/api` requests stayed on app origin; demo cookie was HttpOnly, `/api`, SameSite Lax |
| CSV/PDF export | `EXEC PASS` | CSV and Decision Memo PDF download links returned expected file types |
| Secret scan | `STATIC PASS` — 0 matches in reviewed commit candidates | Dedicated gitleaks/trufflehog binaries unavailable |

The local health-capacity evidence in `artifacts/security/health_regression_local.json` is preserved from the prior isolated run: 300 requests each to `/health` and `/api/health` returned HTTP 200 with 256 synthetic sessions unchanged and no `Set-Cookie`. That specific 600-request check was not repeated in this completion. Backend session isolation and health-probe regression tests passed in the fresh 585-test run.

The existing Session Hash PII safeguard is still present in `tests/test_public_demo.py`: stored text fields are checked for email and phone patterns, while only a 64-character hexadecimal `session_hash` digest is treated as opaque. It passed as part of the full backend run. `tests/test_public_demo_sessions.py` also retains the session ownership, provider-participation isolation, and health-capacity probe cases.

## UI regression detail

The old `/evidence` failure was an assertion race: the test captured a one-shot layout snapshot before the route's data effect had rendered the provenance badge, then checked badge visibility later. The route rendered the correct source rows once loading completed. The test now waits for the source rows and exact provenance labels before measuring the layout; it checks both the external survey (`참고`, `외부 조사 기준값`) and public-data (`실제`, `공공데이터`) classifications. No product UI behavior was changed.

The Playwright matrix covers Dashboard, Scenario Compare, Plans, Providers, Evidence, and the generated Decision Memo at 390×844, 768×1024, 1280×800, and 1440×900. Assertions cover loaded responsive CSS, sidebar/content placement, scenario cards and grid columns, visible controls, readiness/error state, badge content, document overflow, clipped text, CSS/JS response status, and browser/hydration errors. The standalone flow also checks same-origin API rewrite, the session cookie, and CSV/PDF exports. It generated 28 screenshots in task-local temporary storage; automated results are not represented as a full manual visual review. `adb devices -l` found no attached device, so native ARTEMIS visual inspection is `NOT_VERIFIABLE`.

## Privacy, worktree, and deployment boundaries

The secret scan covered only the intended commit candidates. It found no API-key/token patterns, cookies, contact details, local absolute paths, SQLite files, or captured response logs. Raw npm audit reports contain dependency advisories and package metadata only. `gitleaks` and `trufflehog` were unavailable, so dedicated-scanner coverage is `NOT_VERIFIABLE`.

An earlier test created 256 synthetic sessions in an OS temporary SQLite database outside the project. Its removal remains pending approval `060ecb10c9f54ccd`; no deletion, alternate cleanup, or approval bypass was performed. New UI runs used separate synthetic SQLite paths in a task-specific temporary directory. Existing primary and auxiliary worktrees were preserved.

No `main` integration, Render deployment, or Render load test was performed. The recorded deployment branch still identifies the unpatched deployment; local 16.3.8 results do not establish that a public deployment contains this patch.

## Before a later deployment

After 2026-10-14, check the official advisory for affected and fixed versions, re-run dependency and regression checks against any required update, and resolve or explicitly accept the development-only `braces` finding. Re-run the unfiltered Ruff command in a checkout without generated Node runtime files. Obtain the separate deployment GO before changing the deployment branch or deploying.
