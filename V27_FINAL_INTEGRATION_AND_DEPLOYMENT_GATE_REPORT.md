# VillageCoverage v27 — Final Integration and Deployment Gate Report

Date: 2026-11-09 (UTC). Author: Claude Code (Sonnet 5.5) under the orchestrator.
Nothing in this report was merged, deployed, enabled or deleted. Every merge, deploy, scheduler switch and data-policy item below is **waiting for explicit user approval**.

Grades used: `EXEC PASS` (executed, observed passing) · `STATIC` (read, not executed) · `SKIP` · `FAIL` · `NOT_VERIFIABLE` (no access from this environment).

## Verdict

| Status | Grade | Evidence |
|---|---|---|
| CODE_VERIFIED | EXEC PASS | RC tree `40a3d09` (see §3) |
| CI_VERIFIED | EXEC PASS on remote heads (#21, #23 tree, #24 `585c8d3`); `4e00aa3` and RC `40a3d09` not CI-run (unpushed) | PR #21 `819fcce`, stack `15b87a8`, Gemini PR #24 — see §1/§2 |
| GEMINI_TIMEOUT_VERIFIED | EXEC PASS (offline, real SDK) — live Gemini NOT_VERIFIABLE | §2 |
| STACKED_PRS_READY | EXEC PASS | #21 `MERGEABLE/CLEAN`; stack CI green; no conflicts in scratch merge |
| MAIN_INTEGRATED | NOT DONE | no merge approved |
| SCHEDULER_EXEC_PASS | **FAIL** (GitHub) | 0 of 24 scheduled runs produced a scheduled HTTP 200 — §4 |
| CLOUDFLARE_POC_VERIFIED | EXEC PASS offline only | 12/12 Node tests; no real Cron event ever observed — §5 |
| CLOUDFLARE_CUTOVER_READY | **NOT READY** | no account access, plan/trigger count unchecked, logging not configured — §5 |
| DATA_PRESERVATION_VERIFIED | **NOT_VERIFIABLE / FAIL by design** | demo DB is in `/tmp`, wiped on restart, redeploy **and spin-down** — §6 |
| DEPLOY_READY | **NOT READY** — user decision required | LIVE is 18 commits behind main; data-loss acceptance not given — §6 |
| DEPLOY_VERIFIED / PRODUCTION_E2E_PASS | NOT DONE | nothing deployed |

## 1. Git state (re-verified at start of this run)

| Ref | SHA | Note |
|---|---|---|
| `origin/main` | `db4810946b47a2433463eb988ea2eefa3079c6fd` | unchanged |
| PR #21 head | `819fcce9807002423a937fc6abf8123e23fd689d` | base `main`; MERGEABLE / CLEAN; CI run `41607333440` success (pull_request) |
| PR #22 head | `7979253eac579db9e084fd6d6222b099adb12396` | base = #21 branch; no CI run on this exact head — last CI `41781917451` on `cc7693a`; the two later commits are docs-only (`V24.2_…REPORT.md`, +77 lines). Covered by #23's CI tree |
| PR #23 head | `15b87a80d3fb8890b2ccb21008fcdda49f9ee217` | base = #22 branch; CI `42569948191` success (workflow_dispatch) |
| Gemini PR **#24** (new) | remote head `585c8d3995c201d008a84f8e776500492c805aca`; local head `4e00aa3` | https://github.com/JongHyun070105/village-coverage/pull/24 — base `main` |
| Render deploy branch | `origin/submission/public-demo-deploy` = `36319c6551b5c80d3f8c4e1aaa43bc7bbf8fe6e3` | equals the SHA reported as LIVE; LIVE SHA itself NOT_VERIFIABLE here (no Render access) |
| RC (scratch, local only) | `40a3d09e926033814e9e58af7e136580232adc7d` | branch `integration/v27-rc-20261109`, worktree `.worktrees/v27-rc-20261109`; never pushed |

- New in this run: PR #24 (created, auto-allowed), local branch `integration/v27-rc-20261109`, local commit `4e00aa3` on the Gemini branch, this report.
- **Pending approval `d771e9553b5e441b`:** `git push origin fix/v26-gemini-timeout-20261109` (publishes `4e00aa3` so PR #24 contains the real-SDK tests and CI runs on them). Until it is approved, PR #24's remote head and CI run (`42574607275`) cover only `585c8d3`. PR #24's body describes `4e00aa3`; this mismatch is real and resolves when the push runs.
- Primary checkout `fix/demand-negation-20261029` @ `ce3bc40`: not touched. Dirty/untracked entries at start: 65; 65 at end (unchanged) at end. All work used isolated worktrees.
- Other open PR: #2 (draft, old base) — ignored.
- V26 report: existed **only** as local commit `c6e7e47` on `docs/v26-release-gate-20261109` (not on any remote). It is preserved unchanged; this V27 report is committed on top of it on the same local branch. Publishing it needs a push approval (no PR needed).
- No `AGENTS.md`/`CLAUDE.md` exists in the repository.

## 2. Gemini timeout (PR #24)

**Reproduced:** with google-genai 1.75.0 (matches `uv.lock`), a call without `http_options.timeout` reaches httpx with `connect/read/write/pool = None` and no `X-Server-Timeout` → unbounded.

**Verified by source + execution (not mocks of the SDK):**
1. `HttpOptions.timeout` is **milliseconds** (`_api_client.py:214-224`, divides by 1000).
2. Per-request `config={"http_options": {"timeout": 10000}}` is honoured by `generate_content`: httpx receives 10.0 s for all four phases and the request carries `X-Server-Timeout: 10`.
3. A stall surfaces as `httpx.ReadTimeout` (subclass of `Exception`) → caught by the existing `except Exception` in `structure_demand` → deterministic fallback.
4. No SDK retry: 429, 503, ReadTimeout each produce exactly one request.
5. Malformed JSON, truncated JSON, empty text, schema-enum violation → fallback.
6. Request body: only locally extracted service-type IDs; no resident text, no API key. PII-redacted text never goes remote.
7. Tests need no key and no network.

**New tests (local commit `4e00aa3`):** 10 test cases in 5 functions: the `585c8d3` fake-client timeout test, plus in `4e00aa3` the real-SDK ReadTimeout test, 6 parametrised provider failures, 1 payload-privacy, 1 disabled/unkeyed. `tests/test_demand.py`: **118 passed** on the branch; ruff clean.

**Residual risks (not fixed, stated in the PR):**
- httpx timeouts are per-phase, not a total deadline; a server trickling bytes can exceed 10 s in aggregate. A hard deadline needs a wrapper (separate change).
- A stalled call still occupies one sync threadpool worker for up to ~10 s (bounded now; previously unbounded).
- Server-side honouring of `X-Server-Timeout` and behaviour against the real Gemini service: **NOT_VERIFIABLE** (no real call made, by instruction).

Independent cross-provider review (gemini-low via `orch-parallel`; the second worker was blocked: first launch failed `SNAPSHOT_FILE_COUNT_LIMIT` from the dirty primary checkout, retry from a clean worktree started 1 worker): agreed on all of the above and independently flagged the per-read-vs-total and thread-occupancy limits. Worker claims were re-checked against source by me.

**CI for #24:** run `42574607275` on remote head `585c8d3`: backend **success** (12m52s), frontend **success** (11m15s). The real-SDK tests in local `4e00aa3` were run locally (118 passed) but have **no CI run until approval `d771e9553b5e441b` is executed**.

## 3. Integrated release candidate

Scratch merge on `origin/main` (db48109): `15b87a8` (stack #21→#22→#23) then `fix/v26-gemini-timeout-20261109` (local head `4e00aa3`) → **`40a3d09`**. **No conflicts.** Gemini touches only `backend/demand.py` and `tests/test_demand.py`; the stack touches none of them in conflicting ways. RC diff vs main: 13 files, +1737/−116 (scheduler script/tests, plans page, e2e, Cloudflare POC, docs/reports, Gemini).

All results below were executed on tree `40a3d09` (Python 3.12.15 via `uv sync --frozen --all-groups`; Node v26.12.0 locally, CI uses Node 22):

| Check | Result |
|---|---|
| `ruff check backend scripts tests` | EXEC PASS |
| `compileall backend scripts tests` | EXEC PASS |
| `pytest -q` (full) | **766 passed, 1 skipped** (opt-in `VC_LIVE_SMOKE` live smoke), 33 subtests, 454 s |
| `tests/test_render_keepalive.py` | 30 passed, 33 subtests |
| `scripts/proposal_acceptance_check.py` (R1–R13) | 113 passed |
| `pip-audit` (46 locked prod deps) | 0 vulnerabilities |
| `npm audit --omit=dev --audit-level=high` | 0 vulnerabilities |
| `npm run lint` / `typecheck` | EXEC PASS |
| `npm run test:unit` | 19 passed |
| `npm run build` (Public Demo env) | EXEC PASS |
| Playwright standard (`test:e2e`) | 24 passed, 1 skipped (remote live spec, opt-in) |
| Playwright Public Demo | 16 passed |
| Playwright ui-regression (4 viewports) | 5 passed (2.3 min) |
| Cloudflare POC `node --test` | 12/12 passed |

Regression coverage of the integrated behaviours: `/plans` stale-region fix (public-demo e2e), cold-start retry/429/503/Retry-After/18:00 boundary (keepalive tests), Gemini fallback (demand tests), session isolation and duplicate-submit (public-demo e2e + backend), security headers/CORS/cookies (static review below + existing tests).

Test-count vs v25: not re-derived; v25's exact count was not re-run per instruction. Current suite includes +10 Gemini test cases (this run) and the +5 cold-start tests from #23.

Static review: API CORS `allow_credentials=False`, methods GET/POST; demo cookie `HttpOnly; SameSite=Lax; Secure` (when configured); API headers nosniff, X-Frame-Options DENY, referrer policy, permissions policy, `frame-ancestors 'none'`; CI workflow `permissions: contents: read`; keep-alive workflow `permissions: contents: read`, `timeout-minutes: 15`, actions pinned by SHA. Not re-tested in a browser against LIVE.

**Not run:** the 16 pages × 4 viewports full sweep (v25 evidence reused, unchanged pages); no LIVE write requests.

**RC status:** CODE-complete and locally verified; it is a scratch local branch, not pushed, not deployed.

## 4. GitHub Actions scheduled keep-alive (measured 2026-11-09 06:37 UTC)

Source: all 24 `schedule` runs of "Render Free keep-alive" (first 2026-11-03 15:26Z), logs downloaded and parsed.

| Metric | Value |
|---|---|
| Expected cron slots (23:55 + 00–07h ×6 + 08h ×5, UTC) in window | **311** |
| Schedule runs actually created | **24 (7.7 %)** |
| Runs that sent **no GET** (`outcome=skipped_late_schedule`) while showing green | **22** |
| Runs that sent GETs | 2 (2026-11-05 06:29Z, 2026-11-07 05:47Z) |
| Of those: result | both **failed**; web ×3, api ×3 and integrated-health ×3 attempts all **HTTP 503** (9 of 9) — 3 attempts is shorter than a Render cold start (delay at start was 164 s, i.e. under the old lateness threshold) |
| Scheduled runs with Web 200 / API 200 / integrated 200 | **0 / 0 / 0** |
| Consecutive in-window run gaps (min / median / max) | 150 / 163 / 184 min |
| Longest in-window silence (09:00–18:00 KST) | **227 min** (2026-11-05) |
| In-window runs per day | 2 (design: ~50) |

Why this matters: Render Free spins down after 15 min without inbound traffic. Gaps of 150–227 min mean the demo sleeps nearly all business hours, and because the filesystem is ephemeral across spin-down (§6), **each sleep also wipes the demo database**.

What code fixes: PR #21 removes the false `skipped_late_schedule` (it would have turned 22 skipped runs into real pings); PR #22 raises retries to 16/endpoint, 4 min/endpoint, 8 min/run, handles 429/503/Retry-After and stops at 18:00 KST — a live cold start measured in v25 (~93.7 s) and again today (API 102.5 s, web 22.8 s) is inside that budget.

What code **cannot** fix: GitHub's own delivery. GitHub documents that `schedule` can be delayed under load and queued jobs can be dropped (this statement came from a summarised fetch of the docs page, not verbatim — re-check before quoting). 7.7 % delivery is an input to the workflow, not a bug in it. Conclusion: **#21+#22 make each delivered run correct, but cannot reach the ~10-minute cadence; SCHEDULER_EXEC_PASS stays FAIL until a reliable trigger exists.** No post-fix scheduled run exists (fixes are unmerged), so post-fix effectiveness is **NOT_VERIFIABLE** by observation.

## 5. Cloudflare Workers Cron (preparation only)

**Official limits** (fetched 2026-11-09 from developers.cloudflare.com; limits page "last updated Oct 29, 2026", cron page Oct 17, pricing Oct 2, permissions Sep 15):

| Item | Workers Free |
|---|---|
| Requests/day | 100,000 (reset 00:00 UTC) |
| CPU per Cron invocation | **10 ms** |
| Subrequests per invocation | **50** |
| Cron Triggers per account | **5** (Paid 250) |
| Cron handler wall time | 15 min per invocation |
| Cron time zone / propagation | UTC / up to 15 min after a change |
| Delivery guarantee | **not stated.** Docs say cron Workers "run on underutilized machines" |
| Cron Events retention | 100 most recent invocations (≈ 2 days at 54/day) |
| Permission to create / update | Workers Admin (new) / Editor on that Worker (existing); no Routes permission needed |
| Price | Free price not stated as a number; Paid is $5/month minimum. Docs do **not** state that Free can never bill — only that Paid is a separate plan. Do not add a payment method |

All README numbers in the POC match these. Not stated by Cloudflare: whether cron invocations count toward the 100,000/day request limit (54 invocations/day make it immaterial).

**POC review (static + EXEC offline):** 3 cron triggers ≤ 5; UTC crons map to 08:55–17:45 KST, 54 invocations/day; worst case 48 subrequests per invocation (3 × 16, or 2 × 16 + 16 recovery) < 50; max run 8 min < 15 min; `redirect: "manual"`; strict 3-URL allowlist; GET only; 10 s request timeout; bounded body read; no response body in logs; fail-closed on unknown cron; throws on non-ok outcome so Cron Events shows a failure; no secrets needed. 12/12 offline tests pass.

**Gaps found:**
1. `wrangler.toml` has **no `[observability]` block** — `console.log` output is likely not persisted (only live `wrangler tail` / the last 100 Cron Events). Enable Workers Logs, or use Cron Events + Render request logs, before relying on it. (Not verified against a real deploy.)
2. 10 ms CPU per invocation on Free is unmeasured. Network waits are not CPU, but JSON parsing and repeated `Intl.DateTimeFormat` calls across up to 48 attempts are untested on real infrastructure.
3. Account plan and existing trigger count: **NOT_VERIFIABLE** — no Cloudflare credential, CLI session or MCP is available; none was requested or created.
4. Real-environment stability: **never observed.** Offline tests prove logic, not delivery.

**GitHub vs Cloudflare:** Cloudflare Cron is a first-party scheduler and a plausible improvement over GitHub's best-effort `schedule`, but that is an expectation, not a measurement; its docs give no delivery SLA either, so it is **unproven** until Cron Events and Render logs show it. Both keep the existing Render URLs; both are GET-only.

**Cost:** expected $0 on Workers Free. Overage/billing on Free is not documented either way — treat "never upgrade" as the control.

**Cutover plan (needs explicit approval; ordering prevents double scheduling):**
1. User supplies a scoped token via environment variable (Workers Editor on one Worker; Admin only if the Worker must be created). Never in chat/Git.
2. Verify plan = Free, existing cron count ≤ 2 (POC needs 3 of 5), account has no payment method.
3. Re-run `node --test` and, if Wrangler ≥ 4.139 is available, `wrangler dev` scheduled-event test; add `[observability] enabled = true`.
4. Merge #21/#22 first (so the GitHub fallback is correct).
5. Disable GitHub `schedule` (keep `workflow_dispatch`) — **before** deploying Cloudflare; confirm no schedule run is queued/in progress (`gh run list --event schedule --status in_progress` and `--status queued` both empty).
6. `wrangler deploy` with exactly the 3 crons (previous triggers are replaced by the `triggers` array); wait up to 15 min for propagation.
7. Observe ≥ 1 real Cron Event per cron expression; check `scheduled_delay_seconds` and Render request logs for Web/API/integrated HTTP 200.
8. Watch one full 09:00–18:00 KST day; success = no gap > 15 min and zero 503 after first recovery.
9. Rollback: set `crons = []` and redeploy (removes triggers), then re-enable GitHub `schedule`. Never run both.

## 6. Render and data

**Live probe today (read-only GET):** API `/health` HTTP 200 after **102.5 s** (cold); web `/api/health` HTTP 200 in 22.8 s with `demo_data_available: true`, 2916 cached routes. Matches v25 behaviour.

**LIVE vs RC:** `origin/submission/public-demo-deploy` (`36319c6`) → RC: **26 shipping files, +1271/−92** in `backend/` and `frontend/` (plus tests/docs/workflows that do not ship). Only `backend/demand.py` (+5, Gemini) and `frontend/app/plans/page.tsx` (+36) come from the four PRs. The rest is **18 commits already on main but never deployed** (e.g. `authz.py`, `request_limits.py`, `security_headers.py`, demand-parsing changes, `main.py`, home/scenarios pages, `next.config.ts`). So the deploy risk is mostly *main's* undeployed v21/v23 work, not the PRs. No change to `pyproject.toml`, `uv.lock`, `package*.json` or `render.yaml` (start commands, env vars, OR-Tools/uv pins unchanged). DB schema: only `save_schedule_plan(commit=True)` parameter; no DDL change in the diff I inspected (`database.py` +4/−2).

Render facts (docs fetched today): auto-deploy on push to the linked branch by default; Free services spin down after 15 min idle (~1 min to spin up); **filesystem is ephemeral and lost on redeploy, restart *and spin-down***; 750 free instance hours/month/workspace; persistent disks need a paid service; Free Postgres expires after 30 days (+14-day grace, then deleted), 1 GB, no backups. Prices for paid web/Postgres/disks were **not stated** on the fetched pages — get them from the dashboard before choosing. AutoDeploy status and the actual LIVE commit: **NOT_VERIFIABLE** (no Render access; only the deploy branch SHA equals the reported LIVE SHA).

**Data classification (code review of `backend/database.py`, `public_demo.py`):**
- **A — regenerable:** reference tables seeded from tracked `data/demo.json` (regions, village areas, population/household snapshots, service types, providers, route cache of 2916 straight-line rows). Re-created on start.
- **B — temporary demo records:** `public_demo_sessions` (30-min idle TTL, demo-owned rows purged on expiry), visitor-owned schedule plans/rounds/routes, approvals, structuring drafts, import batches, feedback, audit events — all scoped by `owner_session_hash`.
- **C — possibly preserve-worthy:** real resident input, irrecoverable survey records, real operational approvals, personal data. **Existence in the production DB is NOT_VERIFIABLE** (no shell/DB access). The app redacts PII before remote use and demo input is meant to be synthetic, but that is policy, not proof.

**Options (decision belongs to the user):**
- **A. Keep as ephemeral demo.** $0; no work; every redeploy, restart and spin-down wipes B (sessions invalid mid-visit). Acceptable only if the demo is declared synthetic/no-retention. Needs explicit acceptance of data loss.
- **B. Persistent store.** Paid Render web service + persistent disk (or external Postgres); needs DB-path change, migration plan, backups and cost approval; disks disable zero-downtime deploys. Free Postgres is not a fit (30-day expiry, no backups). Price: not verified.

The deploy is **blocked** until the user chooses A (accepts loss) or B. Do not change either without that decision.

**Deploy procedure (not executed):**
1. Approve data policy and merge order (§8).
2. Merge PRs, confirm main CI green after each (§8).
3. Build deploy candidate = current deploy branch + the shipping diff above (or fast-forward from main per user preference); review `git diff 36319c6..<candidate> -- backend frontend render.yaml`.
4. Push to `submission/public-demo-deploy` (this triggers Web and API auto-deploy; user approval required).
5. Wait for both deploys (cold ~100 s), then GET-only checks: `/health`, `/api/health`, 16 pages.
6. Rollback: Render dashboard → Deploys → redeploy previous deploy of `36319c6`, or push `36319c6` back to the branch (a forward push of the old tree; no force-push needed).

## 7. Final quality summary

| Area | Grade |
|---|---|
| Backend pytest 766/1 skip, ruff, compile, R1–R13 113 | EXEC PASS (local, tree 40a3d09) |
| Frontend lint, typecheck, unit 19, build | EXEC PASS |
| Playwright 24+16, ui-regression | EXEC PASS / 5 passed (2.3 min) |
| 16 pages × 4 viewports, PDF/CSV | v25 evidence reused; not re-run |
| Security (pip-audit, npm audit, headers, CORS, cookies, workflow permissions) | EXEC PASS audits / STATIC for headers, CORS, cookies |
| OR-Tools | covered by the pytest suite; no solver change in these PRs |
| Gemini | EXEC PASS offline (real SDK); live NOT_VERIFIABLE |
| Production E2E on a new deploy | NOT DONE |

## 8. Remaining approvals (each independent)

| # | Action | State |
|---|---|---|
| 0 | Push `4e00aa3` to the Gemini branch (approval `d771e9553b5e441b`) | **pending** |
| 1 | Merge PR #21 (`819fcce`), pinned with `--match-head-commit` | **approval requested `a86ad333f79c476f`, pending** |
| 2 | Retarget #22 to main, re-check CI, merge | after 1 |
| 3 | Retarget #23 to main, re-check CI, merge | after 2 |
| 4 | Merge Gemini PR #24 | after its CI on the final head |
| 5 | Cloudflare cutover (§5) incl. token, GitHub schedule disable | not requested |
| 6 | SQLite: accept data loss **or** fund persistence (§6) | not requested |
| 7 | Render deploy (push to `submission/public-demo-deploy`) | blocked on 6 |
| 8 | Push this report branch (`docs/v26-release-gate-20261109`, branch only, no PR) | **approval requested `c4fb0747341c4607`, pending** |

Merge notes: do not squash/rebase; after each retarget confirm CI on the new base (CI runs only for PRs to `main`, so #22/#23 had only manual dispatch runs until retargeted); if any head moves, earlier approval does not cover the new head.

## 9. What was and was not done

Done: state re-verification; real-SDK Gemini probes and tests; PR #24; scratch integration with full backend/frontend/security/scheduler/POC suites; 24-run GitHub schedule analysis; official Cloudflare/Render/GitHub doc checks; LIVE/deploy diff; data classification.

Not done (by constraint): merges, deploys, Render/Cloudflare/GitHub-setting changes, token creation, live Gemini call, LIVE write requests, DB access.
