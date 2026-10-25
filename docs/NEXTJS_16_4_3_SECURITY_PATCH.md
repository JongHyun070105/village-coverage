# October 2026 Next.js security patch

Verified 2026-10-24 KST. Candidate source: `9a8c4bed60bca57cce2941a028945b2f002c6f01`. Runtime verification uses Node 22.18.0. This is candidate security evidence; the public Render runtime has not been upgraded by this task.

| Package | Before | Candidate |
|---|---|---|
| next | 16.3.8 | 16.4.3 |
| eslint-config-next | 16.3.8 | 16.4.3 |
| react / react-dom | 19.2.8 | 19.2.9 |
| sharp | 0.35.5 | 0.35.5 |
| zod (development only) | 4.6.5 | 4.6.7 |

The npm registry latest tag and [official release](https://github.com/vercel/next.js/releases/tag/v16.4.3) agreed on stable 16.4.3. No top-level prerelease, unrelated major upgrade, force audit fix, or dependency override was added. npm peer dependencies accept React 19.2.9.

## Advisory verification

- [GHSA-2464-fhr4-w9xw](https://github.com/advisories/GHSA-2464-fhr4-w9xw): Next 16.0.0–16.4.0 affected; 16.4.1 patched. Candidate 16.4.3 passes the fixed range.
- [GHSA-673q-mjm6-r5xr](https://github.com/advisories/GHSA-673q-mjm6-r5xr): typed-array RSC/use-cache RCE; Next 16.4.1 patched.
- [GHSA-p3m5-59mp-jv5r](https://github.com/advisories/GHSA-p3m5-59mp-jv5r): App Router Server Action DoS; Next 16.4.1 patched.
- [GHSA-xqc2-xf4c-x3h3](https://github.com/react/react/security/advisories/GHSA-xqc2-xf4c-x3h3): RSC packages 19.2.0–19.2.8 affected, 19.2.9 patched. `npm ls` correctly reports no separately installed react-server-dom-webpack/turbopack package. Next vendors these runtimes.
- The two installed vendored server.node.production.js files exactly match the [Next security patch a4cea6a](https://github.com/vercel/next.js/commit/a4cea6a) byte for byte. Their detached-buffer and copied-view guards are present. Vendored package peer metadata still names `19.3.0-canary-278794d7-20261002`; this metadata is not evidence of an unpatched bundle and was not presented as installed stable RSC 19.2.9. See `artifacts/release/evidence-20261024/rsc-bundle-verification.json` for both hashes.
- [sharp GHSA-wq5f-xc86-pv6w](https://github.com/advisories/GHSA-wq5f-xc86-pv6w): patched sharp 0.35.5 provides librsvg 2.63.2. Local `require('sharp').versions` confirms 0.35.5 / rsvg 2.63.2 / vips 8.18.7. Linux runtime itself awaits deployment verification.
- [Zod GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5): development-only eslint-plugin-react-hooks dependency was updated within its existing compatible range to 4.6.7 (patched >=4.6.6).

## Executed evidence

Clean `npm ci`, `npm ls`, full and production `npm audit --json`, lint, typecheck, Node 22 standalone build and Chromium tests were executed. Before full audit: 2 vulnerable package entries (1 Critical next, 1 High development zod); next includes three advisories. Before production audit: 1 Critical next package entry. After audit: all severities 0 in both full and production scope. Package JSON and lock pins agree. Detailed raw audit files are in `artifacts/release/evidence-20261024/`.

The prior GitHub Render deploy record points to 7b696499 (Next 16.3.7 / React 19.2.8). It is in the affected version range; neither the new lockfile nor local/CI success proves that runtime has been patched. A zero audit does not prove absence of all application vulnerabilities. Gemini was not called; secrets and security middleware were not removed.

## Additional production Python security patch

The independent review identified the missing Python production audit. pip-audit 2.10.1 found 39 advisory records across 3 of 46 locked production packages. They are separate from the zero npm audit result.

| Package | Before | Patched stable | Reason |
|---|---|---|---|
| certifi | 2026.7.22 | 2026.10.23 | [Compromised CA chain](https://github.com/advisories/GHSA-6q48-6c7w-9gw2), fixed >=2026.10.19 |
| opentelemetry-api | 1.45.0 | 1.45.1 | [Unbounded tracestate parsing](https://github.com/advisories/GHSA-xcq7-p3pf-p88h) |
| Pillow | 12.3.0 | 13.0.0 | 37 advisory records fixed in [stable 13.0.0](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html) |

Pillow 13.0.0 was released 2026-10-16 and requires Python >=3.11; the project uses Python 3.12. Pinned ReportLab 4.5.1 declares Pillow>=9.0.0 with no upper bound. The Pillow major update is directly required by the security findings; unrelated ReportLab 5.x was not adopted. Only these three locked Python packages changed. Decision Memo/PDF tests passed 7/7 before the new complete regression. A fresh production audit scans the same 46 packages and reports zero known advisories. CI now exports the frozen production lock and audits it with pinned pip-audit 2.10.1.

The compact before-audit evidence contains advisory IDs, aliases, fixed versions and the original raw audit hash. Long exploit descriptions are omitted from public evidence. Prior local/CI success on source 1150aa3 is historical and does not validate the later Python lock. Full validation is repeated on the new source SHA.

Development warning: npm still reports ESLint 9.39.5 as no longer supported. The full npm vulnerability audit is zero after the compatible Zod security update. ESLint is development-only; an unrelated ESLint major upgrade was not included. Test-library deprecation warnings remain visible in the preserved logs.

## Resume verification

On resumption, registry `next/latest` and `eslint-config-next/latest` still resolved to 16.4.3. React/DOM latest resolved to 19.3.1, but the candidate deliberately retains the existing 19.2 minor line at the officially patched 19.2.9; no further compatibility change was needed. Package JSON, lock pins and installed tree agree. Both installed vendored RSC production bundle hashes were rechecked and still match the recorded official patch. Node 22.18.0 and standalone server artifact were observed again. Fresh full and production npm audits returned zero findings. Exact-source CI 40073124556 also passed the Python production audit and complete regression. No assertion here upgrades the unknown public runtime to SECURITY_PASS.
