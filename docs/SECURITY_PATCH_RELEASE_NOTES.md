# Security Patch Release Notes — 2026-10-12

## Final state

- Patch preparation: `PATCH_PARTIAL`
- Git preservation: `COMMITTED_AND_PUSHED` to `security/nextjs-16-3-8-review-rerun`
- Deployment: `NOT_DEPLOYED`
- Base: `4f2089e9da83308c011fc9cafb306f18baeca8f6`
- Source diff SHA-256: `6b6d1e0fe081db5e0b38dfb5d7086969c8d67a571e71101ed769fd923c55d29a`

This branch preserves the Next.js 16.3.8 patch and verification evidence. It was not merged to `main`, pushed to `submission/public-demo-deploy`, or deployed to Render. The final branch SHA is available in Git history and the task completion record.

## Dependency and audit result

- `next`: 16.3.7 → 16.3.8.
- `eslint-config-next`: 16.3.7 → 16.3.8.
- React and React DOM remain 19.2.8.
- `npm ci` and `npm ls` confirm the exact manifest and lockfile versions.
- npm audit: all High 6 → 5, Critical 0 → 0; production High 1 → 0, production Critical 0 → 0.
- The remaining five High reports are the development-only `braces <=3.0.3` dependency path under the ESLint toolchain. No compatible fix was applied and no force fix was run.
- `UPSTREAM_ADVISORY_PENDING`: Next.js has announced a 2026-10-14 security update, but affected and fixed versions are not yet published. Do not infer the impact or block preservation of this 16.3.8 branch on unpublished details.

## Verification result

- Backend: 585 passed, 1 skipped; compileall passed.
- Ruff: backend source and whole repository excluding generated `artifacts/security/run-tmp` passed. The literal unfiltered `uv run ruff check .` reported two findings in the bundled Node runtime's `lldb_commands.py`, not project source; this is the reason patch preparation remains `PATCH_PARTIAL`.
- Frontend lint, typecheck, and Node 22.18.0 Next.js 16.3.8 build passed.
- Existing E2E: 17/17 passed (12 standard + 5 Public Demo).
- UI regression: 2/2 passed on 390×844, 768×1024, 1280×800, and 1440×900 for Dashboard, Scenario Compare, Plans, Providers, Evidence, and generated Decision Memo.
- Provenance race: the test now waits for the two expected evidence rows and their correct source/classification badges before taking the layout snapshot. This corrected test synchronization; application behavior was unchanged.
- Standalone browser flow: CSS/JS 200; API calls remained same-origin; demo session cookie flags were verified; CSV and Decision Memo PDF exports returned expected file types.
- R1–R13: 112/112 passed. New result: `artifacts/qa/r1-r13-security-completion-20261012T061759Z.json`.
- Existing Session Hash PII safeguard remains in `tests/test_public_demo.py`: contact-pattern checks continue to cover stored text, with only the 64-hex session digest treated as opaque; session ownership/provider isolation and health-probe cases remain in `tests/test_public_demo_sessions.py`. The fresh backend run passed them.
- The UI matrix produced 28 task-local screenshots; these are not committed and do not count as a full manual visual review. No attached Android device was available for ARTEMIS.
- Health-capacity evidence retained from the prior isolated run: `/health` and `/api/health` each returned 300/300 HTTP 200 at 256 sessions, no cookie issuance, and no session-count change. The targeted 600-request run was not repeated in this completion.
- Static scan of intended commit candidates: no matching secrets, contact details, local paths, SQLite, or raw response logs. Dedicated gitleaks/trufflehog scanning is `NOT_VERIFIABLE` because the binaries are unavailable.

See `docs/FRONTEND_SECURITY_AUDIT.md` and the sanitized acceptance artifacts in `artifacts/security/` and `artifacts/release/` for details and limitations.

## Preserved work and pending cleanup

The primary checkout and existing worktrees were left intact. No user or historical data was deleted. The earlier external OS-temp SQLite database containing 256 synthetic sessions remains untouched while approval `060ecb10c9f54ccd` is pending. Task-local browser screenshots and build/test caches remain outside the commit.

## Later deployment work

After the 2026-10-14 announcement, verify the official affected/fixed-version matrix and apply only a supported patch. Re-run the relevant audit, backend/frontend tests, UI matrix, and standalone checks. Re-run the unfiltered Ruff command without the generated Node runtime in its scan tree. Deployment to Render remains a separate action and requires the project's GO gate.
