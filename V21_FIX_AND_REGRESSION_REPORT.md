# VillageCoverage v21 수정 및 회귀 검증 보고서

작성일: 2026-11-01 (KST)
기준 브랜치: `main` @ `99023e3f4cce4b2cb0e514e872c98b206b1a0d89`
작업 브랜치: `fix/v21-comprehensive-20261101`
최종 판정: **PARTIAL — IMPLEMENTATION_VERIFIED / MERGE_PENDING / DEPLOYMENT_PENDING**

## A. 발견 항목별 결과

| 문제 ID | 우선순위 | 수정 상태 | 실제 검증 | PR |
|---|---|---|---|---|
| VC-BUG-001 | P2 | FIXED_VERIFIED | 계획·라운드·경로·소유권·감사·재계획 장애 주입 후 롤백, FK 무결성 및 재시도 통과 | 생성 예정 |
| VC-REL-001 | P2 | CONFIRMED_UNRESOLVED | 30회/60초 전역 신규 세션 상한과 Retry-After를 유지. 검증된 클라이언트 식별 경계가 없어 안전한 방문자별 제한을 도입하지 않음 | 생성 예정 |
| VC-BUG-002 | P2 | FIXED_VERIFIED | 지역 변경 때 모든 비교 결과 패널 초기화, 늦게 도착한 구역 응답 무시를 Playwright로 검증 | 생성 예정 |
| VC-SEC-001 | P2 | FIXED_VERIFIED | 호칭 유무 한국어 이름, 전화번호·주소·식별번호 및 일반 명사 오탐을 fake Gemini client로 검증. 이름이 포함된 요청은 원격 호출하지 않음 | 생성 예정 |
| VC-SEC-002 | 조건부 P1 | FIXED_PARTIAL | 위조 역할은 인증으로 인정하지 않으며 비데모 민감 경로에서 익명 401·역할 불일치 403, 데이터 변경 없음 확인 | 생성 예정 |
| VC-REL-002 | P2 | FIXED_VERIFIED | SQLite 쓰기 잠금 중 세션 처리를 worker thread로 이동. 합성 잠금에서 health 200 응답 지연 없이 세션 요청 복구 확인 | 생성 예정 |
| VC-BUG-003 | P2 | FIXED_VERIFIED | 비즈니스 날짜를 `Asia/Seoul` 기준으로 통일하고 미래 관측일 차단. 저장·로그 시각은 UTC 유지. 날짜 경계 및 기존 유효성 테스트 통과 | 생성 예정 |
| VC-API-001 | 조건부 P2 | FIXED_VERIFIED | Content-Length 없이 읽는 스트림도 누적 바이트 제한. 정상·정확한 경계·초과 1바이트·잘못된 길이·중단 스트림 합성 테스트 통과 | 생성 예정 |
| VC-UX-001 | P3 | FIXED_VERIFIED | 화면 이탈·지역 변경 뒤 후속 POST 중단, 중복 쓰기 차단, 모호한 쓰기 결과 안내 및 계획 목록 확인을 Playwright로 검증 | 생성 예정 |
| VC-SEC-003 | P3 | FIXED_VERIFIED | Web/API 헤더와 HTTPS 전용 HSTS 동작 확인. `includeSubDomains` 및 `preload` 미설정 | 생성 예정 |
| VC-SEC-004 | P3 | FIXED_VERIFIED | checkout, setup-python, setup-uv, setup-node의 모든 workflow action을 immutable SHA로 고정. `contents: read` 유지 | 생성 예정 |
| VC-DEP-001 | P3 | CONFIRMED_UNRESOLVED | production npm 및 Python 의존성 취약점 0건. npm 개발 그래프의 moderate 16건은 남음; 감사가 요구하는 해결은 ESLint 생태계 major 변경 | 생성 예정 |

### 변경 요약 및 한계

- `save_schedule_plan`은 호출자가 트랜잭션을 소유하도록 `commit=False` 옵션을 추가했고, 계획 생성자는 본문·소유권·거버넌스·감사 이벤트가 모두 완료된 뒤 한 번만 commit합니다. 실패·재계획 실패는 연결의 열린 트랜잭션을 rollback합니다.
- CSV 본문은 헤더를 신뢰하지 않고 스트림을 바이트 단위로 제한합니다. 기존 import별 5 MiB/10 MiB 계약은 그대로 유지했습니다.
- 신규 세션의 서버 전체 발급 상한은 남아 있습니다. 신뢰 가능한 IP/사용자 식별 수단이 없고 조작 가능한 전달 헤더를 신뢰할 수 없어 방문자별 상한은 안전하게 구성할 수 없었습니다. 정상 방문자의 공정성을 완전히 해결하지 못한 공개 데모 위험입니다.
- 운영자 인증 provider는 현재 설정되어 있지 않습니다. 요청 본문의 역할 문자열을 신원 증거로 사용하지 않으며, 서버 검증 principal이 없는 비데모 민감 경로는 fail-closed입니다. 공개 데모 allowlist 경로는 기존 동작을 유지합니다. 실제 비데모 운영을 재개하려면 신뢰할 수 있는 인증 middleware/provider가 필요합니다.
- npm 전체 감사에서 발견된 16건은 모두 개발 의존성입니다. 핵심 advisories는 minimatch의 globparts 증폭 DoS입니다. npm 감사가 제시한 해결은 eslint 4 또는 eslint-config-next 12로의 major 변경이어서 현 Next 16/ESLint 9 조합에 자동 적용하지 않았습니다. `npm audit fix --force`는 실행하지 않았습니다.
- 추가 발견 `VC-UI-002`: 관리홈닥터 snapshot이 정상 `UNAVAILABLE` 상태로 `summary: null`을 반환하고 KOSIS 응답에서 선택 필드가 빠질 때 근거 화면이 렌더 오류로 깨졌습니다. 응답 타입을 nullable/optional로 맞추고 누락 필드를 안전하게 렌더링했습니다. 새 Playwright 테스트로 검증했습니다.

## B. 회귀 및 보안 검증

수정 전 재현:

- 계획 저장 중 DB trigger 장애를 주입해 API 실패 뒤 신규 하위 행이 남지 않는지 검사했습니다.
- bare-name Gemini 테스트의 첫 실패에서 이름 포함 입력이 원격 client까지 도달하고, safe demand text는 prompt에 전달되지 않는 것을 확인했습니다. 수정 뒤 개인정보 포함 입력은 원격 호출 0회이며 안전한 텍스트만 fake client payload로 전달됩니다.
- 인증 테스트의 첫 실패에서 호출자 역할 주장만으로 승인이 진행되는 경로를 재현했습니다. 수정 후 익명 요청은 401, 위조/불일치 역할은 403이며 draft/plan 기록이 바뀌지 않습니다.
- 지역 전환, 늦은 응답, 화면 이탈, ambiguous POST 및 snapshot 누락은 새 브라우저 테스트로 검증했습니다.

수정 후 실행 결과:

| 검증 | 결과 |
|---|---|
| Backend 전체 pytest | **667 passed, 1 skipped**, 4 기존 경고, 401.22초 |
| R1–R13 acceptance | **13/13 PASS**, 포함 테스트 113 passed |
| Backend ruff | PASS |
| Frontend ESLint | PASS |
| Frontend TypeScript | PASS |
| Frontend unit | **19 passed** |
| Frontend production build | PASS |
| Standard Playwright E2E | **19 passed, 1 skipped** (공개 서비스 실시간 E2E는 실행하지 않음) |
| Public Demo Playwright | **14 passed**, 로컬 synthetic API만 사용 |
| Production UI regression | **5 passed**, CI와 같은 standalone build 및 local API 사용 |
| CSV·날짜·세션·트랜잭션·헤더·개인정보 집중 테스트 | 전체 Backend/브라우저 회귀에 포함되어 PASS |
| npm production audit | **0건** |
| npm 전체 dependency audit | **16 moderate**, 전부 dev dependency |
| Python production lock audit (`pip-audit 2.10.1`) | **No known vulnerabilities** |
| 변경 파일 secret scan | 28개 변경 파일의 고신뢰 패턴 검사 0건. `gitleaks` 실행 파일은 환경에 없어 사용하지 못함 |
| `git diff --check` | PASS |

로컬 프런트엔드 검증은 private scratch checkout 및 기존 dependency cache를 사용했습니다. scratch의 symlinked `node_modules` 때문에 Next standalone trace에 외부 경로 파일 27개 경고가 있었지만 production standalone UI 회귀 5건은 실제 실행 환경에서 통과했습니다. GitHub CI는 repository의 보통 `npm ci` 환경에서 별도로 확인해야 합니다.

독립 검토:

- 두 cross-provider read-only reviewer의 보안/정확성 및 회귀/통합 검토를 받았습니다.
- 검토에서 확인된 P2는 source-text omission을 수정해 fake-client prompt 테스트로 확인했고, 역할 주장 승인 결함은 fail-closed 인증 및 401/403 테스트로 확인했습니다.
- 세션 발급 공정성은 신뢰 가능한 식별 수단 부재로 미해결 처리했습니다. 검토자의 나머지 주장은 코드와 실행 테스트로 재확인했습니다.

## C. Git 및 배포 상태

- Primary checkout은 작업 전에 기록한 상태와 동일합니다. primary branch `fix/demand-negation-20261029`, HEAD `ce3bc40a1815b59f507a7b9cf2a95d32e1567d02`; 기존 1,939 dirty/untracked 경로의 status manifest와 해시 모두 일치합니다.
- 모든 v21 변경은 별도 worktree와 브랜치 `fix/v21-comprehensive-20261101`에서 작성했습니다.
- 시작 시 원격 main은 기준 SHA `99023e3f4cce4b2cb0e514e872c98b206b1a0d89`; 마지막 main CI는 [run 41278741029](https://github.com/JongHyun070105/village-coverage/actions/runs/41278741029)에서 SUCCESS였습니다.
- Render Web/API의 작업 중 read-only 관측 SHA는 `36319c6551b5c80d3f8c4e1aaa43bc7bbf8fe6e3`이었습니다. 원격 deploy branch `submission/public-demo-deploy`도 이 SHA였으며 이번 변경은 배포하지 않았습니다.
- main 병합 없음. Render 설정·환경변수·서비스·배포 변경 없음. 공개 서비스 E2E 및 외부 Gemini 호출 없음.
- PR: 생성 예정. PR 생성 후 링크와 CI 결과를 이 보고서에 추가합니다.

## D. 미해결 위험

| 우선순위 | 미해결 항목 | 현재 영향 |
|---|---|---|
| P1 조건부 | 검증된 운영자 인증 provider 부재. 민감한 비데모 staff 작업은 fail-closed | 현재 공개 데모 allowlist에는 영향 없음. non-demo 파일럿/운영 전환 시 staff 워크플로 사용 불가 |
| P2 | 30회/60초 신규 세션 전역 issuance limit | 공개 데모에서 한 방문자의 발급 요청이 다른 신규 방문자를 제한할 수 있음. 신뢰 가능한 client 식별/분산 공유 한계가 남음 |
| P3 | 개발 의존성 moderate 16건 | production dependency risk는 확인되지 않음. 개발 도구 실행 경로의 minimatch advisory가 남음 |

## E. PR 및 최종 판정

하나의 통합 PR을 생성할 예정입니다. 트랜잭션, 인증, 세션, 프런트엔드, workflow 변경이 함께 검증되는 의존 관계가 있어 단일 변경 묶음으로 제출합니다.

**구현 검증은 통과했으나 미해결 항목이 남아 `PARTIAL`입니다.** PR CI SUCCESS 후에도 main 병합과 운영 배포는 진행하지 않습니다. 두 작업은 별도 사용자 승인 단계입니다.

PR 링크: 생성 예정
PR CI: pending
