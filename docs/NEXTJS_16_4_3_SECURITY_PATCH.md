# October 2026 Next.js security patch

Verified 2026-10-24 KST. Candidate source: `1150aa3c285dda521ce0b2e2ec3aeb8b760ccf21`. Runtime verification uses Node 22.18.0. This is candidate security evidence; the public Render runtime has not been upgraded by this task.

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
