# Git Branch History

## Audit boundary

Repository: `JongHyun070105/village-coverage`. The starting remote refs were
re-fetched and matched the supplied SHAs for `main`, `submission/public-demo-deploy`,
and `quality/public-demo-stability-study`. There were 13 remote branches and no
open pull requests. GitHub reported the audited remote branches unprotected.
The existing tag `v5.2.0-rc1` points to `e9c6e9a49a485a998d1903e9cecf959b3c63006a`;
it was not moved or changed.

The Render deployment records available during this audit pointed to
`submission/public-demo-deploy` at `467c7381bed8066e5d9205bfa5097534923a6fd2`
for both web and API. The public API health endpoint returned 200 before any
new deployment. The live deployment SHA therefore remained the old SHA at that
time. Render dashboard configuration and non-GitHub automation references were
not available for a complete deletion audit.

## Milestones

| Milestone | Branch | Existing SHA | Main ancestry | Change/evidence recorded |
|---|---|---|---|---|
| V2 | `v2-proposal-complete` | `1ffe575eac237dd024ca70f7ada4ce5812c189b3` | Included | Proposal acceptance evidence; branch is an ancestor of `origin/main`. |
| V3 | `v3-operational-hardening` | `2362190db69b5a6c3dfe39329672428168de9497` | Included | Benchmark and acceptance evidence refresh; ancestor of `origin/main`. |
| V4 | `v4-evidence-public-sector` | `a3c11e91ddf0615706a78a01cbf924fb769ea583` | Included | Proposal acceptance evidence; ancestor of `origin/main`. |
| V5 | `v5-field-reality-hardening` | `9fa163cb26ef53ddd31d16594751e66798b0364a` | Included | Approved-plan review keyboard accessibility audit; ancestor of `origin/main`. |
| V5.1 | `v5-1-solver-completion` | `72f326782f79316e835e8855d017cb6e8f3e9b1e` | Included | Solver acceptance audit; ancestor of `origin/main`. |
| V5.2 readiness | `v5-2-field-pilot-readiness` | `db0e0409565704e0808f2c259ce1b01cacbfd99f` | Included | Pilot workflow and limitations audit; ancestor of `origin/main`. |
| V5.2 loop | `v5-2-pilot-loop-completion` | `9b70724677daa2fd09897182e7a5eb536ce6d6cf` | Included | V5.2 readiness acceptance evidence; ancestor of `origin/main`. |
| RC1 | `release/villagecoverage-v5.2-rc1` | `c49a3a62c7b47094ab33c7d5807f23a0653824f0` | Same as main | Branch equals `origin/main`; existing annotated tag remains at its own SHA. |
| Submission preparation | `submission/2026-ai-life-solution` | `8b3acde11329e65baca8a7f323436f49f9a6b0d2` | Not in main; included in deploy branch | Submission evidence/readiness mapping; verified ancestor of `origin/submission/public-demo-deploy`. |
| Public demo | `submission/public-demo-deploy` | `467c7381bed8066e5d9205bfa5097534923a6fd2` | Not in main | Public demo deployment commit; GitHub deployment records reference this SHA for web and API. Keep while Render uses it. |
| UI regression repair | `fix/public-demo-ui-regression` | `467c7381bed8066e5d9205bfa5097534923a6fd2` | Not in main; same as deploy branch | UI style repair; exact same SHA as the public demo deployment branch. |
| Quality study | `quality/public-demo-stability-study` | `ce3bc40a1815b59f507a7b9cf2a95d32e1567d02` | Not in main | Nine commits beyond the deployment branch and 15 beyond main; recorded regression, security, and quality study evidence. |
| Concurrency hardening | `fix/public-demo-concurrency` | Base `ce3bc40a1815b59f507a7b9cf2a95d32e1567d02` | Not in main at audit start | Local implementation adds anonymous session ownership, per-session provider state, bounded fairness, tests, and reports. Final task-branch SHA is in `artifacts/git/consolidation_acceptance.json`. |

All seven historical `v*` refs and the RC1 branch were locally proven ancestors
of `origin/main`. Submission preparation is included in the deployment branch;
UI repair equals that deployment branch. Quality includes the deployment
branch and is nine commits ahead. The concurrency branch starts at quality and
has not been removed. These ancestry facts preserve commits but do not by
themselves establish that branch deletion is safe.

## Retention decision

No remote branch was deleted. Keep `main` and the Render deployment branch.
Other merged historical refs remain deletion candidates only: active Render
service configuration and external automation dependencies could not both be
ruled out. The final per-branch evidence is recorded in
`artifacts/git/branch_cleanup_manifest.json`. No force push or tag change was
performed. Existing worktrees, including the dirty primary checkout, were
left in place.

## Final integration and cleanup audit

This section supersedes earlier point-in-time statements above where they
describe the pre-deployment state. Captured at 2026-10-09T14:23:26Z.

- `origin/main` advanced from `c49a3a62c7b47094ab33c7d5807f23a0653824f0` to
  `32de2a38e5a9444d80d3bb497aaad9bf09c7fbbf` and now equals `origin/submission/public-demo-deploy`. The
  fast-forward was already present on the remote when this continuation resumed;
  the clean local `main` worktree was fast-forwarded to that verified ref. This
  continuation did not push a main update.
- The concurrency implementation commit `839886ea302ebce9c849b1bc5b4a8fa654a2e1f2` and final acceptance
  commit `32de2a38e5a9444d80d3bb497aaad9bf09c7fbbf` are reachable from `main`. All 13 non-main remote branch
  tips were rechecked as ancestors of `origin/main`.
- GitHub reports successful web and API deployments for `32de2a38e5a9444d80d3bb497aaad9bf09c7fbbf` on
  `submission/public-demo-deploy`. Fresh HTTPS GETs returned 200 for the frontend
  homepage and API health endpoint. The deployed browser smoke recorded in the
  acceptance artifact covered three isolated sessions, core plan flow, private API
  denial, Memo/CSV/PDF, retry guidance, and a 390px viewport. No production load
  test was sent.
- There are 14 remote branch refs and zero open PRs. GitHub currently
  reports all 14 refs unprotected. No remote refs or tags were deleted
  or moved. The deployment ref remains active; the primary quality worktree and
  its untracked user artifacts remain untouched.
- All branch tips are preserved in `main`, but absence of external automation
  references and the complete Render tracking configuration cannot be proven from
  available evidence. Consequently, cleanup remains `BRANCH_CLEANUP_BLOCKED`;
  deletion eligibility is false for all branches. See the refreshed inventory,
  cleanup manifest, and consolidation acceptance artifacts.

Final Git result: `BRANCHES_PARTIALLY_CONSOLIDATED`; branch cleanup:
`BRANCH_CLEANUP_BLOCKED`; concurrency result: `PARTIAL` because the deployed API
returned 502 during the fresh post-decline verification.

## 2026-10-11 final stabilization audit (pre-deletion snapshot)

Captured after the clean-checkout implementation and CI fixes were fast-forwarded
from `e6cff560d3f58da5e36f91e9b8d095f929bb4db2` to `ebc24fedc124ecaa96a4411ab88ab1427333d930`.
GitHub compare reports every non-main branch tip is an ancestor of `main`.
Current compare ahead/behind counts, exact SHAs, worktree use, PR/protection,
deployment references, and deletion blockers are in
`artifacts/git/branch_cleanup_manifest.json`.

| Branch | Last SHA | Main ahead/behind | Main inclusion | Milestone / validation | Related artifacts | Pre-deletion decision |
|---|---|---:|---|---|---|---|
| `fix/public-demo-concurrency` | `32de2a38e5a9444d80d3bb497aaad9bf09c7fbbf` | 0/7 | yes | Public Demo session concurrency and proposal acceptance evidence. | `artifacts/concurrency/final_acceptance.json`; `artifacts/concurrency/proposal_acceptance_final.json` | eligible for individual deletion after final exact-SHA recheck |
| `fix/public-demo-ui-regression` | `467c7381bed8066e5d9205bfa5097534923a6fd2` | 0/18 | yes | Public Demo UI restoration with desktop/mobile screenshot evidence. | `artifacts/ui_regression/after/desktop/home.png`; `artifacts/ui_regression/after/mobile/home.png` | eligible for individual deletion after final exact-SHA recheck |
| `hotfix/render-api-502-20261010` | `e6cff560d3f58da5e36f91e9b8d095f929bb4db2` | 0/4 | yes | Health endpoint session exemption; recovery evidence retained; active hotfix worktree. | `artifacts/incidents/render_api_502.json`; `docs/RENDER_502_INCIDENT_REPORT.md` | A linked worktree currently has this branch checked out; preserve it. |
| `main` | `ebc24fedc124ecaa96a4411ab88ab1427333d930` | 0/0 | canonical | Clean-checkout harness and acceptance; full CI PASS. | `artifacts/qa/clean_checkout_acceptance.json`; `artifacts/qa/r1-r13-clean-checkout-c44d635.json` | Canonical default branch. |
| `maintenance/clean-checkout-branch-cleanup` | `ebc24fedc124ecaa96a4411ab88ab1427333d930` | 0/0 | yes | Clean-checkout fixture, isolation/bootstrap, CI and acceptance records. | `artifacts/qa/clean_checkout_acceptance.json`; `artifacts/qa/r1-r13-clean-checkout-c44d635.json`; `docs/CLEAN_CHECKOUT_TEST_GUIDE.md`; `docs/CLEAN_CHECKOUT_REPRODUCIBILITY_AUDIT.md` | eligible for individual deletion after final exact-SHA recheck |
| `quality/public-demo-stability-study` | `ce3bc40a1815b59f507a7b9cf2a95d32e1567d02` | 0/9 | yes | Quality/stability study; active primary user worktree with dirty files preserved. | `artifacts/quality_longrun_acceptance.json` | A linked worktree currently has this branch checked out; preserve it. |
| `release/villagecoverage-v5.2-rc1` | `c49a3a62c7b47094ab33c7d5807f23a0653824f0` | 0/24 | yes | V5.2 RC architecture correction; existing tag remains at its own SHA. | `docs/ARCHITECTURE.md` | eligible for individual deletion after final exact-SHA recheck |
| `submission/2026-ai-life-solution` | `8b3acde11329e65baca8a7f323436f49f9a6b0d2` | 0/20 | yes | Submission evidence and readiness gap documentation; retained due uncertain external references. | `submission/CLAIM_EVIDENCE_MAP.md`; `submission/SUBMISSION_GAP_MATRIX.md` | External submission references cannot be ruled out; retain this submission branch. |
| `submission/public-demo-deploy` | `7b696499c6c4b59fd613866faa89c1afe8934398` | 0/5 | yes | Active Render API/web deployment ref; latest successful deployment remains at the recorded SHA. | `artifacts/incidents/render_api_502.json`; `docs/RENDER_502_INCIDENT_REPORT.md` | A linked worktree currently has this branch checked out; preserve it.; GitHub deployment records identify this as an active deployment ref; retain it. |
| `v2-proposal-complete` | `1ffe575eac237dd024ca70f7ada4ce5812c189b3` | 0/84 | yes | V2 proposal acceptance evidence and requirements traceability. | `artifacts/proposal_acceptance_report.json`; `docs/PROPOSAL_REQUIREMENTS_TRACEABILITY.md` | eligible for individual deletion after final exact-SHA recheck |
| `v3-operational-hardening` | `2362190db69b5a6c3dfe39329672428168de9497` | 0/62 | yes | V3 benchmark and proposal acceptance evidence. | `artifacts/proposal_acceptance_report.json`; `artifacts/routing_benchmark.json` | eligible for individual deletion after final exact-SHA recheck |
| `v4-evidence-public-sector` | `a3c11e91ddf0615706a78a01cbf924fb769ea583` | 0/56 | yes | V4 proposal acceptance evidence. | `artifacts/proposal_acceptance_report.json` | eligible for individual deletion after final exact-SHA recheck |
| `v5-1-solver-completion` | `72f326782f79316e835e8855d017cb6e8f3e9b1e` | 0/41 | yes | V5.1 solver acceptance and audit evidence. | `artifacts/v5_1_acceptance_audit.json`; `docs/V5_1_ACCEPTANCE_AUDIT.md` | eligible for individual deletion after final exact-SHA recheck |
| `v5-2-field-pilot-readiness` | `db0e0409565704e0808f2c259ce1b01cacbfd99f` | 0/38 | yes | V5.2 pilot workflow, accessibility, API failure and solver evidence. | `artifacts/v5_2_acceptance.json`; `artifacts/external_api_failure_matrix.json` | eligible for individual deletion after final exact-SHA recheck |
| `v5-2-pilot-loop-completion` | `9b70724677daa2fd09897182e7a5eb536ce6d6cf` | 0/32 | yes | V5.2 readiness acceptance evidence. | `artifacts/v5_2_field_pilot_readiness_audit.json` | eligible for individual deletion after final exact-SHA recheck |
| `v5-field-reality-hardening` | `9fa163cb26ef53ddd31d16594751e66798b0364a` | 0/47 | yes | Public-sector workflow keyboard accessibility audit. | `frontend/e2e/public-sector-workflow.spec.ts` | eligible for individual deletion after final exact-SHA recheck |

GitHub reported 0 open PRs, 0 protected refs, 0 repository hooks, and 0 GitHub
Releases. The only deployment ref observed is `submission/public-demo-deploy`;
its web and API deployment records both report success at
`7b696499c6c4b59fd613866faa89c1afe8934398` on 2026-10-10. The Render service
configuration was not directly available. The final low-frequency health GETs
timed out at HTTP 000 and are `NOT_VERIFIABLE`; the historical incident remains
`RECOVERED_VERIFIED`.

Automation inspection covered GitHub PRs, protection, hooks and deployments,
`.github/workflows`, repository scripts, `render.yaml`, and linked worktrees.
No direct automation references to stale candidate refs were found in those
scopes. Non-GitHub automation cannot be exhaustively verified, so
`submission/2026-ai-life-solution` is retained. The active deployment ref and
refs used by active worktrees are also retained. Existing tag
`v5.2.0-rc1` remains unchanged. No remote ref has been deleted at this snapshot.
The primary `quality/public-demo-stability-study` checkout and its existing
untracked files remain untouched.

## 2026-10-11 post-deletion verification

The pre-deletion history and manifest were already in `main` at
`d2e2ffb2f9653a9669c3d28c64d43330f0f2ebf6` before any branch deletion. After
individual SHA/ancestry/protection/PR/worktree/deployment rechecks, the following
11 remote refs were deleted and absence verified:

| Deleted branch | Preserved SHA | Related evidence |
|---|---|---|
| `fix/public-demo-concurrency` | `32de2a38e5a9444d80d3bb497aaad9bf09c7fbbf` | `artifacts/concurrency/final_acceptance.json`; `artifacts/concurrency/proposal_acceptance_final.json` |
| `fix/public-demo-ui-regression` | `467c7381bed8066e5d9205bfa5097534923a6fd2` | `artifacts/ui_regression/after/desktop/home.png`; `artifacts/ui_regression/after/mobile/home.png` |
| `maintenance/clean-checkout-branch-cleanup` | `ebc24fedc124ecaa96a4411ab88ab1427333d930` | `artifacts/qa/clean_checkout_acceptance.json`; `artifacts/qa/r1-r13-clean-checkout-c44d635.json`; `docs/CLEAN_CHECKOUT_TEST_GUIDE.md`; `docs/CLEAN_CHECKOUT_REPRODUCIBILITY_AUDIT.md` |
| `release/villagecoverage-v5.2-rc1` | `c49a3a62c7b47094ab33c7d5807f23a0653824f0` | `docs/ARCHITECTURE.md` |
| `v2-proposal-complete` | `1ffe575eac237dd024ca70f7ada4ce5812c189b3` | `artifacts/proposal_acceptance_report.json`; `docs/PROPOSAL_REQUIREMENTS_TRACEABILITY.md` |
| `v3-operational-hardening` | `2362190db69b5a6c3dfe39329672428168de9497` | `artifacts/proposal_acceptance_report.json`; `artifacts/routing_benchmark.json` |
| `v4-evidence-public-sector` | `a3c11e91ddf0615706a78a01cbf924fb769ea583` | `artifacts/proposal_acceptance_report.json` |
| `v5-1-solver-completion` | `72f326782f79316e835e8855d017cb6e8f3e9b1e` | `artifacts/v5_1_acceptance_audit.json`; `docs/V5_1_ACCEPTANCE_AUDIT.md` |
| `v5-2-field-pilot-readiness` | `db0e0409565704e0808f2c259ce1b01cacbfd99f` | `artifacts/v5_2_acceptance.json`; `artifacts/external_api_failure_matrix.json` |
| `v5-2-pilot-loop-completion` | `9b70724677daa2fd09897182e7a5eb536ce6d6cf` | `artifacts/v5_2_field_pilot_readiness_audit.json` |
| `v5-field-reality-hardening` | `9fa163cb26ef53ddd31d16594751e66798b0364a` | `frontend/e2e/public-sector-workflow.spec.ts` |

Retained remote refs (5): `main`, `submission/public-demo-deploy`,
`hotfix/render-api-502-20261010`, `quality/public-demo-stability-study`, and
`submission/2026-ai-life-solution`. The deployment ref remains at
`7b696499c6c4b59fd613866faa89c1afe8934398`; the hotfix, quality, and deployment
worktrees remain in place. `submission/2026-ai-life-solution` remains because its
external submission use cannot be ruled out. The maintenance task branch was
deleted remotely after merge; its detached worktree and local branch ref remain
in place, including the untracked report artifact.

All 11 deleted branch SHAs remain reachable from `origin/main`. The remote ref
count moved from 16 before cleanup to 5. Existing tag `v5.2.0-rc1` is unchanged;
no force push, local branch deletion, worktree removal, or user-file deletion
was used. The primary checkout remains on
`quality/public-demo-stability-study` at `ce3bc40a1815b59f507a7b9cf2a95d32e1567d02`
with its 27 existing untracked paths.

Final Git cleanup status: `PARTIAL` because the submission branch remains
externally uncertain. Final low-frequency Render health requests returned HTTP
000 and current health is `NOT_VERIFIABLE`; deployment records still show the
last successful API and web deployment at the retained SHA. No redeployment was
performed because the changes are test harness, test-only route fixture, docs,
artifacts, and CI only. Machine-readable results: `artifacts/git/branch_cleanup_final.json`
and `artifacts/git/branch_cleanup_manifest.json`.
