# Public demo UI regression audit

Audit date: 2026-10-08

Repository: `JongHyun070105/village-coverage`

Deployment baseline: `submission/public-demo-deploy` at `04d64174cc69c033b2c4899566d98a1e8632cc53`

Repair branch: `fix/public-demo-ui-regression`

## Findings

The visual regression had two independently verified causes.

1. The pages had moved to the current component vocabulary, but 36 class selectors used by the existing JSX were absent from `frontend/app/globals.css`. `/scenarios` therefore rendered its four comparison options without their card treatment; its toolbar, result metrics, empty states, and explanatory lists also had no component layout rules. Several older screens shared the same gap. The provenance component had a separate contract mismatch: it emitted `prov-badge` / `prov-*`, while the stylesheet defines `provenance-badge`.
2. The fixed sidebar and content offset had no single owner. `.sidebar` was fixed at 232px, while `.app-content` had no offset; individual wrappers such as `.page-shell`, `.page-main`, and `.main-content` each tried to position themselves. The public-demo banner lived under `.app-content`, so it began at x=24 and painted behind the sidebar. At tablet widths, those separate offsets also made page starts inconsistent.

This was not a missing stylesheet download: the baseline Render HTML loaded its hashed CSS asset successfully with HTTP 200 (106,682 bytes). In Chromium, `/scenarios` had a `block` scenario grid, and each scenario card computed to zero padding, no border, and a transparent background. At 1440px, the banner began at x=24 while the fixed sidebar extended to x=232. The baseline scenario page had zero browser console errors, so the appearance was caused by missing style rules and layout ownership, not a hydration failure.

## CSS class inventory

The inventory used the TypeScript JSX AST over all 28 `.tsx`, `.jsx`, and `.js` files under `frontend/app/` and `frontend/components/`, then parsed class selectors in `globals.css` and the generated production CSS. Conditional class branches and interpolated template classes were inspected separately; the result was not used to delete selectors.

| Classification | Result |
| --- | --- |
| `DEFINED` | 500 statically resolved JSX class tokens have authored selectors. |
| `TAILWIND_UTILITY` | 0 used tokens rely only on generated Tailwind utility CSS. |
| `DYNAMIC_CLASS` | 29 template-expression sites; prefixes `approval-`, `freshness-`, `reality-`, and `tone-` have matching authored selector families. API-state and component-prop class values were treated as dynamic. |
| `MISSING` | 0 statically resolved used classes remain missing after repair. |
| `UNUSED` | 7 selector candidates were not found in JSX or known dynamic/prop flows: `low`, `map-diagnostic`, `quality-good`, `quality-warn`, `request-card`, `request-fields`, `service-registry`. They were retained; this audit does not authorize deleting them. |
| `AMBIGUOUS` | 6 computed `className` expressions need runtime values to enumerate fully (including provider state, approval status, and map state). Their selectors were retained and representative pages/states were exercised in browser tests. |

The 36 missing selector names at baseline were: `api-error`, `api-error-todo`, `callout`, `cell-sub`, `cell-title`, `compact`, `dashboard-page`, `demo-chip`, `empty-line`, `feedback-conflicts`, `feedback-duplicates`, `full-row`, `import-page`, `loading-line`, `metric-list`, `must-not`, `muted`, `page-lede`, `plain-list`, `plans-list-panel`, `prior-card`, `prior-grid`, `provider-resilience-panel`, `public-demo-restricted-page`, `reality-tag`, `scenario-card`, `scenario-grid`, `solver-status-sep`, `subhead`, `survey-long-field`, `survey-note`, `survey-workflow`, `toolbar-form`, `tradeoff-list`, `warning-line`, and `wide`. The base stylesheet also lacked `.panel`, `.page-header`, and `.primary-button`; those shared selectors are now defined. The provenance class mismatch is corrected in the component.

## Root-cause matrix

| Cause | Finding and evidence |
| --- | --- |
| A. Missing CSS selectors | **Confirmed.** The 36 baseline classes above, plus shared `.panel`, `.page-header`, and `.primary-button`, had no selector in the baseline stylesheet. Production browser computed styles confirmed the visual effect. |
| B. CSS import missing | **Ruled out.** `frontend/app/layout.tsx` imports `./globals.css`; the baseline browser loaded the stylesheet. |
| C. Production CSS asset 404 | **Ruled out for baseline.** Render returned HTTP 200 for the hashed CSS asset. The local standalone build also served CSS in Chromium without stylesheet request failures. |
| D. CSS priority conflict | **Not supported by evidence.** The affected cards had no matching selector at all; computed styles did not point to an overriding declaration. |
| E. Old and new layout contracts mixed | **Confirmed.** Sidebar, app wrapper, and multiple page wrappers each owned or omitted horizontal offset. The offset now belongs to `.app-content`; page wrappers no longer add a second sidebar margin. |
| F. Next.js standalone build issue | **Not observed.** Render is configured to start the standalone server and copy static assets. A production build and the same standalone server ran locally with its public/static files present. |
| G. Hydration/runtime error | **Not observed.** Baseline `/scenarios` and the repaired production route had zero console/page errors; the full route matrix reported no hydration errors. |
| H. Responsive breakpoint error | **Confirmed as a layout gap.** Recovered toolbar and comparison styles had no working 2-column tablet / 1-column phone rules. The shared offset also changed at 940px and 670px in separate wrappers. Responsive rules now provide 4/2/1 scenario columns and 4/2/1 form columns at the tested breakpoints. |
| I. Stale browser cache or deployment version | **No evidence of stale CSS.** Baseline HTML referenced a loaded hashed CSS asset. Render did not expose its deployed Git SHA in the observed response, so exact deployment SHA and cache identity remain `NOT_VERIFIABLE`. |

## Repair

- Added the missing shared page header, panel, form, scenario card/grid, metric, empty/error, provenance, and supporting page styles to `frontend/app/globals.css`.
- Established one responsive layout contract: `.app-content` owns the sidebar offset (232px desktop, 68px tablet, 0px mobile); `.page-shell`, `.page-main`, and `.main-content` no longer add another left offset. The public-demo banner now follows that wrapper.
- Added the missing phone/tablet grid rules, visible focus styling for scenario inputs/buttons, and the missing forecast/status states used by current JSX.
- Changed the shared provenance badge to the existing `.provenance-badge` design-system selector and kept the simulation indicator explicit.
- Added an isolated production-Chromium regression configuration and test. It does not change application functionality or public-demo protections.

## Routes and browser evidence

The actual public sidebar routes are `/`, `/scenarios`, `/plans`, `/providers`, `/calendar`, `/evidence`, `/data-quality`, `/region-comparison`, and `/methodology`. `/data-sources` and `/regions` are not sidebar routes and returned 404; the corresponding current paths are `/data-quality` and `/region-comparison`. The five restricted public-demo routes (`/demand`, `/feedback`, `/imports`, `/pilot-imports`, `/pilot-setup`) returned their intended guard UI with no form, rather than a page error.

The new Chromium suite exercises the 9 public and 5 guarded routes at 1440×900, 1280×800, 768×1024, and 390×844 (56 route/viewport checks). It checks CSS requests, console/page errors, heading visibility, clipping, horizontal overflow, sidebar/banner bounds, and computed scenario grid/card/form/provenance styles. It then submits the four-policy comparison and checks all four result cards, policy explanation, minimum-coverage analysis, provider-decline fallback, and button recovery.

Baseline Render screenshots are in `artifacts/ui_regression/before/{desktop,mobile}/`. Repaired local standalone production screenshots are in `artifacts/ui_regression/after/{desktop,mobile}/`. Both sets cover the nine public sidebar pages at 1440×900 and 390×844. Live post-deploy screenshots, if Render deployment is available, will be recorded under `artifacts/ui_regression/after/render/`.

## Verification results

| Check | Result |
| --- | --- |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm run build` with public-demo production settings | PASS; 17 routes generated |
| Next standalone Chromium UI regression | PASS, 2 Playwright tests; 56 route/viewport combinations plus a four-policy calculation flow |
| Existing browser E2E | PASS, 14 tests (12 general + 2 public-demo); includes scenario calculation, provider decline/replan, decision memo/evidence workflow, and public-demo restrictions |
| `uv run pytest -q` | PASS, 572 passed, 1 skipped (4 deprecation warnings). Earlier tracked release notes report 562 passed; the current run has 10 more passing tests. |
| Ruff / Python `compileall` | PASS |
| Proposal acceptance R1–R13 | PASS, 112 mapped tests; all 13 requirements PASS. Run report: `artifacts/ui_regression/r1-r13-acceptance.json`. |
| `git diff --check` | PASS |

The mapped proposal report records `04d64174cc69c033b2c4899566d98a1e8632cc53` as `checked_out_commit`, the unchanged repair-branch HEAD when that run completed. Its source fingerprints cover the mapped R1–R13 evidence files; the UI-only changes are separately covered by the production Chromium regression above.

No backend or public-demo policy code was changed. The existing public-demo E2E suite passed with synthetic-only mode, blocked contact/import/private routes, and guarded forms unchanged. Local checks do not establish a Render deployment or a live HTTPS pass.

## Modified files

- `frontend/app/globals.css`
- `frontend/components/provenance-badge.tsx`
- `frontend/e2e/ui-regression.spec.ts`
- `frontend/playwright.config.ts`
- `frontend/playwright.ui-regression.config.ts`
- `docs/UI_CSS_REGRESSION_AUDIT.md`
- `artifacts/ui_regression/` screenshots and R1–R13 run report
