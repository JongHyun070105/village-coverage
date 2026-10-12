# Pre-Release Security Gap Audit

확인 시각: 2026-10-12 17:00 KST
기준 SHA: d93bc31aace96428e38f6f7b1818f40ce36a7e0a
작업 브랜치: security/release-readiness-20261012
결론: SECURITY_PARTIAL — 현재 공개 데모는 Next.js 16.3.7 배포 기록이며, 패치 브랜치의 16.3.8은 아직 배포되지 않았다. 10월 14일 예고된 상위 의존성 보안 공지는 아직 세부 정보가 공개되지 않았다.

## 확인한 실행 및 형상

- 기준 원격: origin/main=4f2089e9da83308c011fc9cafb306f18baeca8f6, origin/security/nextjs-16-3-8-review-rerun=d93bc31aace96428e38f6f7b1818f40ce36a7e0a.
- Render GitHub deployment records: web/API 모두 submission/public-demo-deploy의 7b696499c6c4b59fd613866faa89c1afe8934398, 상태 success. 해당 SHA의 manifest는 Next.js / eslint-config-next 16.3.7, React/React DOM 19.2.8이다.
- 보안 패치 브랜치 lockfile은 Next.js / eslint-config-next 16.3.8, React/React DOM 19.2.8이다. 현재 앱은 App Router를 사용한다.
- 단발 읽기 요청: web / → HTTP 200 (22.685초), API /api/health → HTTP 200 (52.644초), TLS 검증 통과. 이는 해당 시각의 두 endpoint 확인이지 지속 가용성이나 브라우저 사용자 흐름 확인은 아니다.
- 외부 부하 테스트, 계획 생성/수정, Render 변경 및 배포는 하지 않았다.

## 우선순위 finding

### P2 — 패치 브랜치와 실제 배포 버전이 다름

- 위치: Render deployment records, submission/public-demo-deploy SHA 7b6964…; 패치: frontend/package.json, frontend/package-lock.json.
- 근거: 성공 배포 기록은 16.3.7이며, 16.3.8 패치는 별도 security branch에만 있다. 이 실행에서 main 병합·배포를 하지 않았다.
- 영향: 최신 16.3.8 보안 수정은 공개 데모에 반영됐다고 말할 수 없다.
- 재현: GitHub deployment record를 조회하고 그 SHA의 manifest를 확인한다.
- 조치: 패치 브랜치의 PR/CI 검토 후 별도의 GO를 받아야 배포할 수 있다. 이번 실행에는 배포하지 않았다.
- 회귀: 현재 버전 간격을 확인했다. 최종 16.3.8 CI 결과는 이 문서 아래의 실행 기록과 Actions SHA를 연결해 갱신한다.
- 잔여 위험: Oct 14 상위 의존성 공지의 영향은 미공개다. 현재 설정에서 조건부로만 적용되는 공개 advisories를 아래에 따로 평가했다.

### P2 — 보안 브랜치 push가 기본 CI를 시작하지 않음

- 위치: .github/workflows/ci.yml.
- 근거: 기존 push.branches: [main]이고 UI 회귀는 test:e2e:all과 별도 config에 있었다.
- 영향: 보안 브랜치의 일반 push는 전체 검증을 자동 실행하지 않았고, responsive matrix와 production npm audit도 빠져 있었다.
- 조치: security/** push trigger, source-scoped Ruff/compileall, production npm audit, Node/Python 버전 기록, 4 viewport UI regression을 CI에 추가했다.
- 재현/회귀: 새 워크플로는 Node 22, Python 3.12를 기록하고 모든 검증을 실행한다. 이 수정 SHA의 GitHub Actions 결과는 별도 결과 JSON에 기록한다.
- 잔여 위험: CI 결과는 정확한 커밋 SHA가 success일 때만 PASS다.

### P2 — pytest 개발 도구 advisory

- 위치: pyproject.toml, uv.lock.
- 근거: 잠금 버전 pytest 8.4.2는 GitHub Advisory GHSA-6w46-j5rx-g56g 영향 범위(<9.0.3)에 해당했고, upstream 수정은 9.0.3이다. 개발 그룹만 영향을 받는다.
- 영향: UNIX에서 로컬 사용자가 취약한 pytest temporary directory 이름을 악용해 테스트 실행자의 가용성 또는 권한 경계를 위협할 수 있다. 서비스 프로덕션 의존성은 아니다.
- 조치: 개발 constraint를 pytest>=9.0.3,<10으로 올려 uv가 9.1.1을 lock하도록 했다.
- 재현/회귀: 전체 pytest suite와 all-groups pip-audit를 다시 실행한다.
- 잔여 위험: Python advisory DB 범위 안의 결과이며, OS/런타임 침투 테스트는 아니다.

### P2 — 심사 자료가 임시 저장 계획의 소실 가능성을 알리지 않음

- 위치: frontend/app/layout.tsx, frontend/app/page.tsx.
- 근거: 기존 배너에 30분 세션 만료는 설명했지만, Render Free의 ephemeral filesystem에 둔 임시 계획이 서비스 restart/redeploy/spin-down 뒤 사라질 수 있다는 설명은 없었다. 첫 화면의 초기 대기 문구도 서버 시작을 설명하지 않았다.
- 영향: 심사자가 데이터 영구 보존 또는 즉시 응답을 기대할 수 있다.
- 조치: 공개 데모 배너에 계획 초기화 가능성을 추가하고 첫 데이터 대기 시 무료 서버 wake-up으로 약 1분 걸릴 수 있음을 표시했다. 기존 API 오류 화면의 안내와 수동 재시도 버튼을 유지했다.
- 재현/회귀: UI regression/E2E를 실행한다.
- 잔여 위험: 대기시간은 보장이 아니며, UI 메시지는 서버의 상태를 실시간 진단하지 않는다.

### P2 — 이전 제출 문서의 테스트 URL 및 세션 설명이 오래됨

- 위치: README.md, docs/SUBMISSION_REQUIREMENTS_2026.md, submission/SUBMISSION_CHECKLIST.md, submission/SUBMISSION_GAP_MATRIX.md, submission/TESTER_GUIDE.md, submission/JUDGE_FAQ.md, submission/DEPLOYMENT_PLAN.md, submission/SUBMISSION_EMAIL.md.
- 근거: URL 없음, 미배포, 방문자 세션 공유로 적혀 있으나 현재 URL과 10월 10일 성공 배포 기록, 브랜치의 session-isolation 구현 및 회귀 테스트가 확인됐다.
- 영향: 제출 가능 상태와 구현 경계를 잘못 전달한다.
- 조치: URL 존재·과거 배포·현재 HTTPS GET·브라우저 사용자 흐름·배포 SHA·제출 준비를 분리해 갱신한다.
- 회귀: 문서와 기계 판독 JSON은 fresh endpoint/배포 확인만 반영하며 원격 브라우저 사용자 흐름은 PASS로 승격하지 않는다.
- 잔여 위험: KEIT 10월 12일 Q&A 첨부 본문은 사이트 WAF 때문에 원문 대조가 불가능했다. 신청자/원 제안자 검토가 남는다.

## Next.js / React advisory matrix

| 대상 | 상태 | 확인 내용 |
|---|---|---|
| Next 16.3.8 | PATCH_AVAILABLE / local branch | 현재 후보 lockfile은 16.3.8이다. GitHub release notes는 SSRF·metadata/cache·dev MCP 보안 수정을 포함한다고 기록한다. Render에는 미배포. |
| Next 16.3.7 (현재 Render 배포 SHA) | CONDITIONAL / further update available | 배포 manifest에서 확인. 알려진 CVE 전체에 대해 무조건 취약하다고 보지 않는다. 아래 코드 조건 평가를 적용한다. |
| Next 16.4 stable | AVAILABLE / NOT_SELECTED | 10월 6일 공개된 안정 버전. React 19.3, 새 cache 동작과 빌드/번들 변경을 포함한다. 이번 앱에서 16.4 standalone·cache·CSS 동작은 실행 검증하지 않았다. |
| React / React DOM 19.2.8 | CONFIRMED_NOT_AFFECTED by current npm audit scope | lockfile tree에서 동일 19.2.8 resolution. npm audit --omit=dev는 0 vulnerabilities. 이는 등록된 audit DB 범위의 결과다. |
| React Server Components deps | STATIC / NOT_SEPARATELY_VERIFIABLE | 앱은 App Router이며 npm ls의 runtime tree와 lockfile을 확인했다. 현 npm audit production 결과에서 해당 runtime dependency advisory는 보고되지 않았다. 10/14 공지의 upstream package는 미공개다. |
| Next upstream dependencies (Oct 14 notice) | UNDISCLOSED / NOT_VERIFIABLE | Next.js는 Critical 2건, High 1건의 upstream dependency 보안 공지를 예고했다. 오늘은 영향 패키지/버전/수정 버전이 공개되지 않아 구체적 판정은 하지 않는다. |

현재 코드의 조건 비교:

- 공개된 Critical GHSA-2xp9-vwfh-vxw4 (AVIF Image Optimization RCE)는 Next 16.3.3에서 수정됐고, GHSA-vcvr-r3jv-pc5j (next/og Node ImageResponse RCE)는 16.3.6에서 수정됐다. 이 두 advisory는 배포 16.3.7보다 낮은 패치 버전을 포함하며 현재 배포 버전 자체를 영향 범위라고 과장하지 않는다.
- 공개된 High Image Optimization SSRF advisory는 16.3.8 release에 수정으로 기재되어 있다. advisory상 images.remotePatterns가 전혀 없는 앱은 영향받지 않는다고 되어 있고, 현재 frontend/next.config.ts에 해당 설정은 없다. 실제 요청으로 악용 가능성을 검사하지 않았다.
- Metadata image route 취약점은 관련 opengraph-image / twitter-image route를 찾지 못했다. self-hosted Pages Router SSG/ISR cache advisory는 현재 frontend/app App Router와 대상 구성 조건이 다르다. next dev MCP advisory는 production deployment가 아닌 development server만 대상으로 한다.
- CSP의 frame-ancestors 'none'와 X-Frame-Options는 frame 삽입을 제한한다. 이를 XSS 방어라고 표현하지 않는다. default-src/script-src CSP는 없다. Next hydration 호환성 회귀 없이 별도 allowlist CSP를 넣지 않았다.

### Emergency patch assessment for current Render release

The public deployment is still Next 16.3.7, but the reviewed public advisories do not establish a currently reachable Critical exploit in this exact configuration: AVIF Image Optimization RCE is patched at 16.3.3; Node next/og ImageResponse RCE at 16.3.6; the reviewed image-optimization SSRF advisory says apps with no images.remotePatterns are not affected, and the current/deployed next.config.ts has no such setting. App Router metadata-image and Cache Components conditions were not found in the source. Thus this audit finds no evidence requiring an emergency deployment before Oct 14 solely for the reviewed, disclosed advisories. This does not make 16.3.7 current or certify the app against undisclosed advisories; the prepared 16.3.8 patch and Oct 14 update still need review, CI, and a separate deployment GO.

### Next 16.3.8 vs 16.4

현재 고정 16.3.8은 Node 최소요건 20.9+를 충족하고 React 19.2.8을 사용한다. 16.4 공식 공지는 React 19.3, 지연 컴파일, 더 작은 Turbopack 캐시, 빌드 번들 최적화와 신규 프로젝트의 Cache Components 기본값을 발표했다. 신규 cache와 React upgrade를 같이 가져오면 캐시 경계·UI·standalone을 다시 검증해야 한다. 16.4 안정 버전이 있다는 이유만으로 이번 minor update를 진행하지 않는다. 10월 14일 advisory가 별도 버전을 요구할 때만 평가한다.

## Dependency scan

- npm lockfile: next@16.3.8, eslint-config-next@16.3.8, react@19.2.8, react-dom@19.2.8. npm ci, npm ls --depth=0 실행.
- full npm audit: 5 High, 0 Critical. 다섯 패키지 보고는 모두 동일 GHSA-vfj7-8cjw-p6xm이 ESLint 개발 의존성 체인을 따라 중복 표시된 것이다. production npm audit --omit=dev: 0 vulnerabilities.
- 경로: eslint-config-next → @next/eslint-plugin-next → fast-glob → micromatch → braces@3.0.3. braces advisory는 <=3.0.3; npm에는 patched release가 없다. audit의 ESLint 14.x force-fix는 현재 Next 16 ESLint 설정과 호환성이 없어 적용하지 않았다. Maintainer는 linked issue에서 해당 취약점이 upstream에선 수정할 것이 없다는 입장을 기록했다. 실행 입력은 repository source/glob; public request가 서버 production runtime에서 이 lint dependency를 호출하는 경로는 확인되지 않았다.
- Python: lock 전체를 pip-audit로 검사한다. 수정 후 pytest는 9.1.1이며 이전 CVE 영향범위 밖이다. production-only export의 의존성 감사 결과도 별도로 기록한다. 스캐너 결과는 해당 시각 DB 범위로 한정한다.
- 과거 Ruff 기록은 artifacts/security/run-tmp/node-v22.18.0-darwin-arm64/share/doc/node/lldb_commands.py의 F401/F841을 지목한다. 그 파일은 이번 감사에서 primary checkout과 clean worktree 모두에서 발견되지 않아 해당 3건은 새로 재현되지 않았다. 현재 전체 checkout Ruff와 backend/scripts/tests Ruff는 통과했다. CI와 clean-checkout은 명시한 프로젝트 Python source만 검사해 사용자 생성 artifact 경로를 스캔 범위와 분리한다. 타사 파일을 수정하거나 ignore 규칙으로 숨기지 않았다.

## Proxy / session / response boundary

- frontend/next.config.ts의 rewrite destination은 배포 환경 변수의 고정 API origin에 /api/:path*를 붙인다. Host/query/path에서 upstream hostname을 만들지 않는다. arbitrary origin SSRF 우회는 정적 구성에서 찾지 못했다.
- 공개 demo route는 backend의 explicit allowlist에 따라 처리된다. 세션 쿠키는 HttpOnly, SameSite=Lax, Path=/api; SQLite owner hash로 plans, provider participation, approval/export 범위를 분리한다. fresh regression에서 두 방문자간 plan list/detail/replan/provider decline/export/approval가 404 격리되는 테스트를 실행한다.
- API fetch는 same-origin credentials와 client cache: no-store를 사용한다. 새 public mode 응답의 remote cache behavior는 E2E와 소스 검사로만 말하고, 이번 단발 health GET은 쿠키/응답 헤더 회귀 검사가 아니다.
- 503/429/network 오류에는 사용자 안내와 수동 retry가 구현돼 있다. 서버 내부 stack trace·환경변수가 UI 메시지로 노출된다는 재현 증거는 찾지 못했다. 원격에서 임의 오류를 주입하지 않았으므로 전 응답 redaction은 별도 security assertion의 범위다.
- SameSite/Lax 및 same-origin JSON 호출은 교차 사이트 write를 줄이는 경계지만, 별도의 CSRF token은 없다. 공개 URL은 인증 없는 synthetic demo이며 실주민/pilot data를 제공하지 않는다. 외부 침투 테스트는 하지 않았다.
- 256 session health/regression은 기존 테스트·보존 evidence를 구분한다. full test에서 회귀가 통과해도 256개 원격 load test가 새 실행됐다고 주장하지 않는다.

## Render Free / data reliability

공식 Free 제한상 15분 유휴 뒤 서비스가 sleep하고, 깨는 데 약 1분 걸릴 수 있으며 local files는 재시작·재배포·spin-down에 영구 보존되지 않는다. 앱은 임시 SQLite를 사용하고 세션 30분 idle expiry를 표시한다. 화면에 초기 wake-up 대기와 임시 계획 초기화 가능성을 안내하게 했다. API 503 안내와 수동 다시 시도 UI가 이미 있다. 자동 polling/keep-alive, 유료 DB, load test는 도입하지 않았다.

## Submission evidence

- 공개 URL: web/API 두 주소가 존재한다. 현재 low-frequency HTTPS health checks는 200. 배포 SHA는 7b6964…로 확인되지만 16.3.7이다.
- 브라우저 사용자 흐름: CURRENT_BROWSER_FLOW_VERIFIED=NO. 현재 원격 origin에서 end-to-end 브라우저 흐름을 실행하지 않았다. local Playwright는 독립된 demo fixture로 실행한다.
- 성과보고서: 내용 초안 Markdown과 빈 Word/HWP/PPT 템플릿 사본만 repository에 있다. 최종 승인본 및 페이지 확인 증거는 없음.
- 참가신청서: 참가자 작성본/서명/동의 파일 없음. 개인정보는 조사·기록하지 않았다. 저장소 밖 파일은 검증하지 못한다.
- 동영상: repository 안에 MP4/MOV/WebM 없음. 실제 2–5분 길이·음성·비밀정보는 검증되지 않았다.
- KEIT: 공식 10월 12일 사전질의 답변서 게시 확인. 첨부 ZIP 다운로드는 KEIT WAF error로 실패해 답변 본문, 추가 FAQ/정정의 실제 변경 내용은 NOT_VERIFIABLE. 아이디어 번호, 가점 자격, 제안자/개발자 관계, 지식재산권의 최종 기재는 신청자/원 제안자가 답변과 대조해야 한다.
- 내부 제출 목표 10월 23일 18:00 KST까지 11일 1시간 남아 있다(2026-10-12 기준). 최종 보고서, 신청서·서명·동의, Q&A 대조, URL fresh-browser flow, 영상 녹화/검수, 설명 자료의 AI/규칙/solver/통계/합성/인간 결정 구분이 남는다.

## Fresh execution record

- Python 3.12.2 / uv 0.11.7, pytest 9.1.1: 585 passed, 1 skipped. Ruff source and full scan passed; compileall passed. Four deprecation warnings remain (Starlette TestClient/httpx and OR-Tools SWIG types); no test failure.
- R1–R13 acceptance: 112/112 passed; report: artifacts/qa/r1-r13-pre-release-20261012.json.
- Frontend Node v22.23.3: npm ci, lint, typecheck, production build, 12 standard E2E + 5 Public Demo E2E passed. Production npm audit: 0 findings. The separate full npm audit reports 5 High / 0 Critical, all one braces advisory.
- Responsive standalone UI: initial run failed because the test build omitted VILLAGE_COVERAGE_PUBLIC_DEMO_API_ORIGIN and NEXT_PUBLIC_PUBLIC_DEMO_MODE; routes-manifest.json therefore had no /api rewrite and API-backed controls stayed disabled. CI/clean-checkout now set both values at build time; repeat build passed 2/2 responsive tests over 4 viewports.
- pip-audit 2.10.1: all 54 locked installed packages and production-only 46 package export reported no known vulnerabilities after pytest update. This is limited to the scanner database at scan time.
- GitHub Actions and its exact run/head SHA are added after push. Local verification does not imply GitHub CI verification.

## Sources

- [Next.js 16.3.8 release](https://github.com/vercel/next.js/releases/tag/v16.3.8)
- [Next.js 16.4 release](https://nextjs.org/blog/next-16-4)
- [Upcoming Next.js Oct 14 security update](https://nextjs.org/blog/upcoming-nextjs-security-update-october-2026)
- [GitHub braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) · [maintainer discussion](https://github.com/micromatch/braces/issues/84)
- [pytest advisory](https://github.com/advisories/GHSA-6w46-j5rx-g56g)
- [Render Free docs](https://render.com/docs/free)
- [KEIT Q&A notice, posted 2026-10-12](https://www.keit.re.kr/board.es?act=view&bid=0009&list_no=128451&mid=a10301010000&nPage=1)
