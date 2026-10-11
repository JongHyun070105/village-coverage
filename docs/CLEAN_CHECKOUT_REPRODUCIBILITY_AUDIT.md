# Clean Checkout Reproducibility Audit

## Scope and baseline

Audit started from freshly fetched `origin/main` at `e6cff560d3f58da5e36f91e9b8d095f929bb4db2`. A detached baseline worktree had no `.venv`, `frontend/node_modules`, `data/village_coverage.sqlite`, `.env`, Playwright output, or cached route database. The implementation was kept in a separate maintenance worktree. The primary quality checkout, its worktree, and its untracked files were not changed.

The clean environment used `uv 0.11.7`, Python `3.12.2`, Node.js `26.9.0`, npm `11.19.1`, and Playwright `1.63.0`. The lockfiles are `uv.lock` and `frontend/package-lock.json`. CI continues to use Python 3.12 and Node 22.

## Original clean-checkout failure and classification

The ignored local file `data/village_coverage.sqlite` held the selected-region Kakao road cache in the developer checkout. `.gitignore` excludes SQLite files, and no cache snapshot is tracked. In a new checkout, `backend.travel` therefore opened an empty route database. Schedule planning correctly returned HTTP 503 / `ROUTE_UNAVAILABLE` when required provider road edges were absent.

The original 26 failure/error cases were re-run from the clean `e6cff56` baseline. The 16 setup errors and seven direct failures below each reached the same missing-cache response. Three other failures were downstream assertions against the response returned after route planning stopped. None established a separate production-code defect.

| Classification | Tests | Observed result |
|---|---|---|
| `ROUTE_CACHE_MISSING` | `tests/test_decision_memo.py::test_memo_json_structure_and_wording`; `test_unknown_costs_are_not_rendered_as_zero`; `test_html_is_print_ready_escaped_and_pdf_renders`; `test_memo_status_follows_approval_and_audit_trail`; `test_requested_changes_create_a_new_plan_version`; `test_compare_with_other_region_or_missing_plan_rejected` | All six `plan_id` fixture setup requests expected HTTP 201 and received 503 `ROUTE_UNAVAILABLE`. |
| `ROUTE_CACHE_MISSING` | `tests/test_governance.py::test_new_plan_is_draft_bound_to_snapshot_and_audited`; `test_approval_requires_review_and_correct_roles`; `test_plan_history_includes_current_approval_and_snapshot_state`; `test_reviewer_can_return_plan_to_draft`; `test_approved_plan_cannot_be_replanned`; `test_unknown_plan_approval_is_404`; `test_explanations_cover_every_area_with_deterministic_reasons`; `test_exports_are_csv_safe_and_pdf_is_valid`; `test_changes_requested_flow_and_resubmit`; `test_approved_plan_rounds_are_immutable_and_new_version_is_required` | All ten plan fixture setup requests expected HTTP 201 and received 503 `ROUTE_UNAVAILABLE`. |
| `ROUTE_CACHE_MISSING` | `tests/test_api.py::test_survey_endpoints_accept_korean_today_before_utc_date_rollover`; `test_provider_schedule_is_saved_for_the_selected_region`; `test_schedule_history_and_csv_export_are_region_scoped_and_auditable`; `tests/test_cost_model_v3.py::test_api_cost_model_for_stored_schedule`; `tests/test_db_integrity.py::test_replan_idempotency_via_api_and_find_existing_child`; `tests/test_operations.py::test_operations_attention_endpoint_and_builder`; `tests/test_underserved.py::test_underserved_scenario_schedule_is_accepted_by_api` | Seven direct failures: expected route-backed schedule/detail success, actual HTTP 503. |
| `ROUTE_CACHE_MISSING` (downstream response assertion) | `tests/test_api.py::test_survey_evidence_is_assessed_only_for_its_service_type`; `tests/test_resident_feedback.py::test_api_workflow_keeps_assessment_demand_fixed`; `tests/test_underserved.py::test_api_status_seed_and_four_policy_comparison` | Three response assertions tried to read `evidence` or `label` after an earlier route failure had returned an error payload. The stack traces were `KeyError`, but the failed prerequisite was the 503 route-cache miss. |

The previously recorded baseline was `556 passed, 10 failed, 16 errors, 1 skipped`. An independent rerun from the same `e6cff56` source was `555 passed, 11 failed, 16 errors, 1 skipped`: the 26 route-related cases above plus a separate 27th failure, `tests/test_public_demo.py::test_public_demo_storage_is_seeded_and_private_routes_fail_closed`. The latter passed in a focused run and in a complete run of `tests/test_public_demo.py` (`13 passed`), so it remains `UNKNOWN` / unreproduced rather than attributed to the route cache.

## Fixture choice and data integrity

The chosen design combines a deterministic code-generated test fixture with a per-run temporary SQLite database. It uses area IDs and coordinates from tracked `data/demo.json`; all off-diagonal distances are synthetic SHA-256-derived values, durations are deterministic, and the timestamp is fixed. The current 54 unique areas produce 2,916 directed route rows. The fixture does not copy or infer any Kakao response or cached road edge.

Every row uses routing version `test-fixture-synthetic-v1`. Runtime route results carry source `TEST_FIXTURE / SYNTHETIC; NOT A ROAD ROUTE`. The cache key has a separate version from Kakao and Public Demo. The fixture generator refuses paths outside the system temp directory and exclusively creates a new database file; it cannot overwrite an existing developer or operations DB. The pytest bootstrap creates a run-specific route DB and a per-test application DB, clears provider keys and local DB variables, and sets explicit test-mode values. It does not delete test output or any directory after the run.

Public Demo remains a separate mode with its existing explicit straight-line estimate source. Pilot/production mode still requires cached/API Kakao road routes; missing routes continue to fail with `ROUTE_UNAVAILABLE`. `tests/test_api.py::test_schedule_plan_fails_closed_without_provider_road_routes` and route failure tests remain in place. The fixture test also disables the fixture flag and confirms that its cache rows are not returned as Kakao routes.

Alternatives considered: a real-road snapshot was rejected because its source/licensing and provenance should not be hidden inside synthetic tests; an API mock was rejected because it would over-mock route handling; a shared checked-in SQLite snapshot was unnecessary for deterministic small data; a developer cache copy is the original hidden dependency. A synthetic fixture plus isolated SQLite best meets offline reproducibility and honest provenance.

## Changes

- `tests/route_fixtures.py`, `tests/conftest.py`, `tests/test_route_fixture.py`, and `tests/test_config.py`: deterministic synthetic route graph, per-test app DBs, explicit environment isolation, provenance assertions, and dotenv isolation.
- `backend/travel.py`: explicit test fixture route version/source. It activates only with the test fixture flag and a route DB below the system temporary directory; production defaults and fallback behavior remain unchanged.
- `scripts/api_smoke_test.py`: explicit empty environment variables now override `.env`; test mode never imports unset values from `.env`.
- `tests/prepare_playwright_route_cache.py` and the two Playwright configs: no developer cache dependency, unique temporary DB/output paths, explicit test mode, and cleared API keys.
- `tests/test_travel.py`: preserve cache-key version checks outside fixture mode and assert the explicit synthetic source for a synthetic cached edge.
- `README.md`, `docs/CLEAN_CHECKOUT_TEST_GUIDE.md`, `scripts/verify_clean_checkout.sh`, and `.github/workflows/ci.yml`: document/install/run the full offline check and add R1–R13 plus both Playwright suites to CI.
- `docs/RENDER_502_INCIDENT_REPORT.md` and `artifacts/incidents/render_api_502.json`: preserved the newer untracked incident evidence after SHA comparison; no duplicate report was created.

No assertion was removed. The only changed route assertions now verify the intentionally distinct fixture mode/source. The stress-test time bound was left unchanged.

## Verification runs

Results are recorded in `artifacts/qa/clean_checkout_acceptance.json`. The first complete local implementation run initially surfaced two travel-test expectation conflicts with the new explicit fixture version/source; the tests were adjusted to assert both routing-version isolation and synthetic provenance. The targeted travel, route fixture, and route-failure suites then passed (`16 passed`). A clean clone at `c44d635` then passed backend (`585 passed, 1 skipped`), Ruff, compileall, R1–R13 (`112 passed`), frontend lint/typecheck/build, standard Playwright (`12 passed`), and Public Demo Playwright (`5 passed`). A second independent clone reinstalled Python and Node dependencies, reproduced the same fixture fingerprint, passed nine targeted backend checks including the `ROUTE_UNAVAILABLE` guard, and passed both E2E suites (`12 + 5`). No unrun stage is marked as passed.

`npm ci` completed from `frontend/package-lock.json`. It reported six high-severity advisories. A production-only audit (`npm audit --omit=dev`) found one high-severity advisory affecting the currently pinned Next.js `16.3.7` dependency; no dependency upgrade was made because this task changes the test harness and a runtime dependency change would require a separate deployment review. This is a remaining release-hygiene item, not a test failure.

## CI follow-up

The first GitHub Actions run for `c44d635` confirmed the backend dependency setup, Ruff, and frontend lint/typecheck/build/browser installation, but the browser job failed because its Playwright web server could not find `.venv/bin/python`. The workflow now installs the locked Python test environment before starting the frontend E2E suites. That first run was cancelled while the backend suite was still running; no live API smoke step had started. The CI workflow no longer reads repository API secrets or runs live API smoke checks, so CI remains offline and secret-free.

The corrected workflow run `38139039667` passed the frontend job, including both browser suites, but backend pytest reported `584 passed, 1 failed, 1 skipped`. The one failure was `test_quick_synthetic_stress_scenario_invariants`: the 1.5-second wall-clock `joint` solve returned no schedule on that hosted runner, with no invariant violations, so the result was correctly `NOT_VERIFIABLE`. Three local repeats of that joint scenario returned `TIME_LIMIT` with a schedule; three repeats on the `decomposed` deterministic-time path returned `OPTIMAL` with a schedule. The smoke test now selects that deterministic path while keeping the same 16-area/3-provider input, seed, 1.5-second budget, and every assertion. The targeted stress test file passed (`17 passed`) after the change.

The clean GitHub Actions rerun `38139879078` completed successfully on `ebc24fe`: backend `585 passed, 1 skipped`; Ruff passed; R1–R13 passed (`112 passed`); frontend lint, typecheck, and build passed; standard Playwright passed (`12`), and Public Demo Playwright passed (`5`). CI installed from the locked Python and npm dependencies, used the deterministic stress path, and had no live API secret or smoke-test step.
