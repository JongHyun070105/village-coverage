# VillageCoverage v25 — Production Readiness and Full QA Report

Checked: 2026-11-09 (KST 13:40–14:30). Evidence grades: **EXEC PASS** (executed here), **STATIC** (code reading only), **SKIP**, **FAIL**, **NOT_VERIFIABLE**.
Older reports (V21/V23/V24/V24.2) are preserved unchanged.

## 0. One-paragraph answer

The public site is up and every public route loads, but **the scheduled GitHub Actions keep-alive cannot keep it awake, and merging the existing fixes will not change that**. Over 5.5 days GitHub created 23 scheduled runs instead of ~300 expected; inside the 09:00–18:00 KST window there were about 2 per day, 150–184 minutes apart, and **none ever received HTTP 200**. The merged-code defect (`skipped_late_schedule`) is real and fixed by PR #21, and the too-short retry window is real and fixed by PR #22 (proved against live Render below). But the dominant cause is GitHub dropping/delaying `schedule` events, which no repository code can fix. Cloudflare Cron is the evidence-backed alternative and needs your decision. **Nothing was merged, deployed, or switched.**

## 1. Current service state

| Item | Value | Grade |
|---|---|---|
| GitHub `main` | `db4810946b47a2433463eb988ea2eefa3079c6fd` (unchanged since 11-03) | EXEC PASS (`git ls-remote`) |
| Render deploy branch `submission/public-demo-deploy` | `36319c6551b5c80d3f8c4e1aaa43bc7bbf8fe6e3` (ancestor of main, 18 commits behind) | EXEC PASS |
| PR #21 | OPEN, base `main`, head `819fcce`, MERGEABLE/CLEAN, CI run 41607333440 backend+frontend pass | EXEC PASS |
| PR #22 | OPEN, base = PR #21 branch, head `7979253`, CLEAN. No automatic checks (base is not `main`). Differs from CI-verified `cc7693a` only by one Markdown report (+77 lines) | EXEC PASS |
| PR #2 (old, unrelated) | still open, base `security/release-readiness-20261012`; not touched | — |
| Web / API / integrated health | all HTTP 200 at 13:42 and after cold recovery at 14:21 KST | EXEC PASS |
| Render Free plan, region, autoDeploy, dashboard env | `render.yaml` says `plan: free`, Singapore. Dashboard state, autoDeploy flag and secrets are **not readable here** | STATIC / NOT_VERIFIABLE |
| LIVE code equals main? | **No.** LIVE API headers lack `x-frame-options` and `permissions-policy`, which main's `SecurityHeadersMiddleware` adds | EXEC PASS |

Primary checkout (`fix/demand-negation-20261029`, many modified/untracked files) was **not modified**. All work is in worktree `.worktrees/v25-readiness-20261109` (branch `fix/v25-readiness-20261109`, from `7979253`).

## 2. Why GitHub Actions "failed"

Collected from `gh run list` + each run's job log (Render Free keep-alive, 24 runs, 2026-11-04 → 11-09 12:03 KST):

| Metric | Value |
|---|---|
| Runs | 24 (23 `schedule`, 1 `workflow_dispatch`) |
| Workflow conclusion | 21 success, 3 failure |
| Actual outcome | **21 `skipped_late_schedule` (0 GETs)**, 3 `http_failed` (9 GETs each) |
| GETs emitted / HTTP 200 / HTTP 503 | 27 / **0** / 27 |
| Runs inside 08:55–18:00 KST | 12 (9 skipped, 2 scheduled HTTP failures, 1 manual dispatch HTTP failure) |
| Gaps between consecutive in-window scheduled runs | 158, 163, 161, 150, 184 min (target: 10) |
| Expected vs created | ~54 cron slots/day ≈ 300 over the span vs 23 created ≈ 8% |
| Checked-out code in every scheduled run | `main` @ `db48109` (GitHub runs `schedule` only on the default branch, per GitHub docs) |

Three distinct causes, kept separate:

1. **Code defect on main (fixed in PR #21, unmerged).** The skip rule treated "time since the most recent cron slot" as delivery delay. With GitHub delivering ~4 events/day, nearly every run looked "late" and was skipped with zero requests, yet showed green. Note `delay_seconds` is only a true delay for the once-a-day `55 23` pre-warm cron (e.g. 11322 s on 11-09 = event arrived ~3 h after 08:55 KST); for the other crons it is meaningless. PR #21 removes the rule and keeps the KST window.
2. **Retry window too short (fixed in PR #22, unmerged).** Main retries 3 times in ~35 s. Measured cold start is longer (below). The three real failures logged 503 ×3 per endpoint ending ~35 s after start, and Render logs for the 11-07 failure showed FastAPI ready ~53 s after the run started (14:47:38 → 14:48:31 KST), i.e. after the retries had already ended.
3. **GitHub does not deliver the schedule (not fixable in code).** GitHub documents that scheduled events "can be delayed during periods of high loads" and queued jobs "can be lost". Observed delivery is ~8%. Whether the gap is delay or loss cannot be told from the API (it exposes run creation time, not the intended fire time), so I make no claim beyond "delivered ~2×/day in-window".

Other items from the checklist: HTML-200 wait pages, JSON contract errors, 429/Retry-After, 18:00 cutoff, redirects are handled by PR #22 code (tests below). Duplicate schedule runs: none observed; `concurrency` group serialises runs. 15-min job timeout: run cap is 8 min, so no overrun path found (STATIC + synthetic).

### 2.1 What PR #21 vs PR #22 each fix

| | PR #21 (`819fcce`) | PR #22 (`7979253`) |
|---|---|---|
| Late-schedule false SKIP | removed | (inherits) |
| KST window / 18:00 cutoff | kept | kept + blocks retries that would cross 18:00 |
| `/plans` stale saved region id | fixed + Playwright test | (inherits) |
| Retry budget | 3 attempts | ≤16 attempts, 4 min/endpoint, 8 min/run, 10 s request timeout, 5→20 s backoff, `Retry-After` honored ≤180 s |
| Cloudflare POC | — | `poc/cloudflare-workers-keepalive/` (not wired into any workflow; `workers_dev=false`, header says do not deploy) |
| Actions permissions | `contents: read` (workflow unchanged by both PRs); repo default workflow permission is `read` | same |

## 3. Keep-alive proof

| Status | Result | Grade |
|---|---|---|
| Workflow registered / enabled | yes, `active` | EXEC PASS |
| Schedule event received | yes, ~2/day in-window (not every 10 min) | EXEC PASS |
| Workflow started | yes | EXEC PASS |
| HTTP request emitted by a **scheduled** run | only 2 of 23 scheduled runs; both 503 | EXEC PASS |
| Web / API / integrated health 200 from a **scheduled** run | **0 occurrences** | FAIL |
| Recovery from cold start by the fixed script | **proven locally against live Render** (below) | EXEC PASS |
| Repeatability of scheduled success | not demonstrable until fix is merged and schedule actually fires | NOT_VERIFIABLE |

**Measured cold start (live, GET only, after 18 min idle, 14:00 KST).** API first 200 at +66 s; Web +33 s after its first request; integrated immediately after. Total ≈100 s. Requests hung to the 8 s curl timeout rather than returning instant 503 in this run, while GitHub runs saw instant 503 — both patterns are retried.

**PR #22 script vs cold live Render (second 18-min idle, started 14:20:26 KST, exit 0, 93.7 s):**
`web: 503,503,503 → 200 on attempt 4 (36.5 s)`, `api: 503×4 → 200 on attempt 5 (56.6 s)`, `integrated-health 200 attempt 1`, `outcome=complete`. The main-branch script stops after 3 attempts (~35 s), which is exactly what the three real failures show. This run was executed from a developer machine, not from GitHub Actions, so it proves the retry logic, not GitHub delivery.

**Synthetic cold-start matrix (`tests/test_render_keepalive.py`, +5 tests, 30 tests pass, 33 subtests).** Web/API ready at 5/5, 5/60, 40/90, 5/180, 90/5 and 60/150 s with 502, 503, 504; timeout, DNS (`gaierror`), TLS (`SSLError`), connection reset, `URLError` recovery; never-starting services stop ≤8 min and ≤16 requests each for every fault type; start 17:59 KST sends nothing at/after 18:00; start 18:00 KST sends zero requests. No script change was needed. Earlier tests already cover 429+Retry-After, HTML 200 wait page, malformed JSON, redirect not followed, URL allow-list.

## 4. Cloudflare alternative

**Needed?** The stated criterion (scheduled runs missing, or >15 min gaps in business hours) is **met** for GitHub. That makes Cloudflare a justified candidate; it does not prove Cloudflare is more reliable — no Cloudflare delivery data exists.

Verified against Cloudflare's limits page: Workers Free = 100,000 requests/day, 10 ms CPU per invocation (HTTP and Cron), 50 subrequests/invocation, **5 Cron Triggers per account**, 15 min Cron wall-clock. POC uses 3 triggers, 54 invocations/day, ≤48 GETs in the worst invocation (<50), 8-min cap. Network wait is not CPU time. Offline POC tests: **12/12 pass** (re-run here).
Not verifiable here: whether your account is on Free, how many Cron Triggers it already uses, actual Cron delay/SLA (docs state none), Wrangler/credentials (none present in this environment; Cloudflare env vars: none). No Worker was deployed, no GitHub schedule disabled.

If you approve a switch, the POC README's cutover order is sound: confirm Free plan and trigger count → disable GitHub `schedule` (keep `workflow_dispatch`) → deploy Worker with the 3 triggers → verify against Render request logs → rollback = disable Worker crons, re-enable GitHub schedule. Never run both at once (double traffic, wasted instance hours).

## 5. 16-page verification

Two environments, kept separate. **LOCAL** = PR #22 head built exactly like CI, public-demo mode, synthetic data. **LIVE** = Render, read-only browser navigation (64 loads = 16 routes × 4 viewports; verified zero non-GET requests to onrender.com; each visitor still receives the normal in-memory session cookie).

Automated metrics, both environments: 64/64 HTTP 200, **0 horizontal overflow**, **0 console errors/warnings/page errors**, 0 stuck spinners/`aria-busy`. Screenshots viewed by me: LOCAL mobile home, tablet scenarios, desktop restricted page; LIVE mobile home. I did **not** visually inspect all 128 screenshots; the other pages are covered by metrics only. LIVE navigation time (cold-free): median 1.3 s, p95 5.0 s, max 5.7 s (n=64, includes first-load API fetches; not a load test).

| Route | In code | In LIVE build | Browser LIVE | Notes |
|---|---|---|---|---|
| `/` dashboard | yes | LIVE_IMPLEMENTED | EXEC PASS | main adds v21 hydration/dashboard fixes (MAIN_ONLY) |
| `/scenarios` | yes | LIVE_IMPLEMENTED | EXEC PASS render; 4-policy compute EXEC PASS only LOCAL (ui-regression, 1.6 min) | |
| `/plans` | yes | LIVE_IMPLEMENTED | EXEC PASS render | stale-region fix is **PR_ONLY** |
| `/calendar` | yes | LIVE_IMPLEMENTED | EXEC PASS | |
| `/providers`, `/providers/[id]` | yes | LIVE_IMPLEMENTED | EXEC PASS | |
| `/villages/[id]` | yes | LIVE_IMPLEMENTED | EXEC PASS | |
| `/evidence`, `/data-quality`, `/methodology`, `/region-comparison` | yes | LIVE_IMPLEMENTED | EXEC PASS | |
| `/demand`, `/feedback`, `/imports`, `/pilot-imports`, `/pilot-setup` | yes | **intentionally disabled in public demo** (shows "이 기능은 공개 데모에서 사용할 수 없습니다") | EXEC PASS for the restriction notice | API allow-list blocks `/api/demand/*`, imports, pilot. Functionality verified only LOCAL in non-demo mode (standard Playwright 24/24 incl. pilot intake/loop) |

Core flows (LOCAL, synthetic): plan create → approval → provider decline → replan, session isolation across 3 browser contexts, cold-start auto-connect, HTML-200/429/500 handling, no re-POST on ambiguous failures — all in Public Demo Playwright **16/16**. PDF/CSV (LOCAL, real files generated and rendered): summary PDF and decision-memo PDF are 1-page A4, Hangul renders, no truncation, filenames `plan-<id>.pdf` / `decision-memo-<id>.pdf`, CSV has UTF-8 BOM. **P3 observation:** summary shows total ₩3,841,685 while memo shows known cost floor ₩3,841,690 (5 KRW). Likely cause (code reading, not executed): optimizer sums per-trip rounded cost, memo sums distance and time components separately. Not changed.
LIVE write flows (plan create/approve/decline, demand save), LIVE PDF/CSV download, and LIVE Gemini: **not run** (production writes need your approval; demand/Gemini unreachable in public demo).

## 6. CI-equivalent tests (on `7979253` + test-only commit `55aa4cb`)

| Gate | Result | Grade |
|---|---|---|
| `ruff check backend scripts tests` (CI scope) | pass | EXEC PASS |
| `ruff check .` / `ruff format --check .` | fail (89 findings, **all** in `submission/final-draft/build_submission_package.py`; 96 files unformatted, pre-existing). Outside CI scope | FAIL (not a gate) |
| compileall | pass | EXEC PASS |
| Backend pytest full | **751 passed, 1 skipped**, 4 subtests | EXEC PASS |
| R1–R13 acceptance | 113 passed | EXEC PASS |
| Scheduler tests | 30 passed (25 existing + 5 new), 33 subtests | EXEC PASS |
| Cloudflare POC offline | 12/12 | EXEC PASS |
| Frontend lint / unit / typecheck | pass / 19 of 19 / pass | EXEC PASS |
| `next build` (CI env) | pass, 17 routes | EXEC PASS |
| Playwright standard | 24 passed | EXEC PASS |
| Playwright Public Demo | 16 passed | EXEC PASS |
| Responsive UI regression (4 viewports) | 5 passed after rebuilding with CI env. A first run failed 5/5 because I built without `VILLAGE_COVERAGE_PUBLIC_DEMO_API_ORIGIN`, so the `/api` rewrite was missing — my environment error, not a code defect | EXEC PASS |
| `npm audit --omit=dev` / `pip-audit` | 0 vulnerabilities / 0 vulnerabilities (46 packages) | EXEC PASS |
| Skips / warnings | 1 pytest skip (not investigated); SWIG DeprecationWarnings from a dependency | disclosed |

## 7. Security, Gemini, OR-Tools, data (code review — STATIC unless stated)

- **Session cookie:** `HttpOnly; SameSite=Lax; Path=/api`, `Secure` over https; server-side hashed owner; sessions in memory; capacity 256, per-session plans ≤20. CORS: explicit origins, `allow_credentials=False`, methods GET/POST. CSRF risk is reduced by Lax + origin allow-list. Rate limits: shared 70, per session 20, solver capacity gate. Non-allow-listed demo routes return 404 `DEMO_MODE_RESTRICTED`.
- **Gemini:** PII redaction first; if redaction fired, locally ambiguous, or no key → deterministic path. When used, Gemini receives **no resident text**, only candidate service-type IDs, and output is re-verified locally; result carries `method: gemini_structured_output | deterministic_fallback`. Real Gemini calls: never executed here (no key); LIVE key presence NOT_VERIFIABLE and the endpoint is blocked in public demo. **P2, UNPROVEN:** the Gemini call sets no explicit timeout (`HttpOptions.timeout` exists in the installed SDK); the endpoint is a sync `def`, so it runs in the threadpool and does not block the event loop. Not changed (no reproduction).
- **OR-Tools:** `max_time_in_seconds`, one search worker, `solver_status` / `optimality_proven` / `time_limit_reached` surfaced; infeasible/not-proven are distinct states. Real solves executed locally (e.g. balanced 14/162, "최적성 확인 완료").
- **SQLite:** public demo DB is `tempfile.gettempdir()/villagecoverage-public-demo.sqlite` (path pinned under the temp dir), schema versioned via `PRAGMA user_version`. `render.yaml` declares no disk. Render Free filesystems are ephemeral: data is lost on restart/spin-down/deploy. **Regenerable:** seed/reference data. **Not preserved:** visitor-created plans, approvals, declines (synthetic by design; banner tells visitors). I could not read the production DB and made no claim about its contents. Keep-alive reduces spin-down loss but does not provide persistence. No backup exists.
- **Not done:** CSRF/CORS probing against live, error-message leakage fuzzing, load/P95/concurrency testing, memory/CPU profiling on Render.
- **Independent review:** **not obtained.** My delegate budget (3) was consumed by two supervisor errors (`SNAPSHOT_FILE_COUNT_LIMIT`, `MAIN changed during snapshot capture`) before any reviewer produced output; the final attempt returned `DELEGATION_BUDGET_EXHAUSTED`. I did not bypass the limit. All findings above are single-reviewer.

## 8. Render free-hour budget (estimate, not dashboard data)

Script constants: window 08:55–17:45 + 15 min idle shutdown = 545 min/day/service = 9.08 h. ×2 services ×30 days ≈ 545 h (≈563 h for 31 days) of 750. This is the nominal schedule only; other services in the same workspace, user traffic outside the window, and cold-start overlap are excluded, and Render dashboard usage was not accessible. Because GitHub currently fires ~2×/day, real consumption is below this today.

## 9. Final verdicts

| Verdict | State | Grade |
|---|---|---|
| CODE_VERIFIED | PR #22 head + new tests | EXEC PASS |
| CI_VERIFIED | PR #21 CI success on exact head; PR #22 code verified by CI run 41781917451 at `cc7693a` and by my local full run; **no automatic CI on PR #22 head** | PARTIAL, EXEC PASS |
| LIVE_CODE_CURRENT | LIVE is 18 commits behind main (header evidence) | **FAIL** |
| SCHEDULER_ACTIVE | workflow active | EXEC PASS |
| SCHEDULER_EXEC_PASS | 0 scheduled runs with HTTP 200 | **FAIL** |
| WEB_HEALTH_PASS / API_HEALTH_PASS | 200 on manual GET and from fixed script | EXEC PASS (not from scheduler) |
| COLD_START_RECOVERED | fixed script on live Render, 93.7 s | EXEC PASS (not from scheduler) |
| FRONTEND_E2E_PASS | local Playwright 45 tests; LIVE read-only navigation | EXEC PASS (local), EXEC PASS read-only (LIVE) |
| BACKEND_E2E_PASS | local suites | EXEC PASS |
| DATA_PRESERVATION_VERIFIED | ephemeral by design; no backup | FAIL / NOT_VERIFIABLE |
| DEPLOY_READY | code yes; blocked on approvals and data-loss decision | NOT_VERIFIABLE (needs your decisions) |
| DEPLOY_VERIFIED | no deploy performed | N/A |
| PRODUCTION_E2E_PASS | no production write E2E run | NOT_VERIFIABLE |

## 10. Handover

1. **Is the public site OK now?** Yes: all 16 routes loaded (11 functional + 5 intentionally disabled), 0 console errors, no overflow. It sleeps after 15 min idle and takes ~60–100 s to wake.
2. **Works for real:** dashboard, scenarios, plans, providers, calendar, evidence/data pages (LIVE, read-only); plan/approval/replan flows and exports (LOCAL).
3. **Code-only (not reachable on LIVE):** demand parsing, Gemini, CSV/pilot imports, v21 security headers/authz/request limits, dashboard fixes (MAIN_ONLY), `/plans` stale-region fix (PR_ONLY).
4. **Why Actions failed:** §2 — buggy skip rule + 35 s retry window + GitHub delivering ~8% of schedule events.
5. **Changed by me:** one test-only commit (`55aa4cb`) and this report. No script/app change was necessary.
6. **On GitHub?** PR #21 and #22 are open; this branch is not pushed unless a PR link appears below.
7. **On Render?** No. LIVE is still `36319c6`.
8. **Risks:** scheduler cannot hit 10-min cadence on GitHub; LIVE missing hardening; ephemeral data; no independent review; Gemini timeout (UNPROVEN); 5 KRW rounding (P3).
9. **Decisions needed from you (each separate):**
   - A. Merge PR #21 at exact head `819fcce`, then retarget #22 to `main` and merge at `7979253` (or later). Gives the fixed retry logic but **will not fix scheduler delivery**.
   - B. Cloudflare Cron trial (confirm Free plan, free trigger slots, supply a scoped token), with GitHub `schedule` disabled first.
   - C. Render deploy: pushing `submission/public-demo-deploy` auto-deploys and **wipes the temp SQLite**; confirm that is acceptable.
10. **After approval:** A → watch new main CI → retarget #22 → CI → merge → CI. B → follow §4 cutover and verify in Render request logs over ≥1 business day. C → merge main into deploy branch, push once, poll `/health` and `/api/health` until 200 (expect ~100 s), re-run read-only navigation; rollback = reset branch to `36319c6` and push.
