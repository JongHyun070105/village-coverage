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
