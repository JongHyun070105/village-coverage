# VillageCoverage v21.1 Pre-Merge Regression Report

**작성일:** 2026-11-02 (KST)
**대상:** PR #18 · `fix/v21-comprehensive-20261101`
**기준점:** `c32df431fd9b99d8a9710a4b5e6607a4749d3ea0`

## 판정

**PARTIAL — 수정과 로컬 검증 완료, CI의 기존 flake를 정밀화하고 최신 재실행 대기, 병합 보류.** 이 보고서는 운영 배포 검증을 의미하지 않는다.

## 재현 및 조치

| 항목 | 결과 | 근거 및 조치 |
|---|---|---|
| VC-SEC-005 개인정보 원문 전송 | **CONFIRMED** | 합성 문장 `세탁 서비스가 필요합니다. 담당자는 홍길동.` 및 유사 꼬리 이름 패턴을 fake Gemini client로 실행했다. 기존 코드에서 일부 이름은 `redact_pii()`를 통과했고, 원문을 포함한 `contents`가 원격 client에 전달됐다. 실 Gemini 호출은 하지 않았다. |
| VC-SEC-005 수정 | **FIXED_VERIFIED** | Gemini prompt에서 비식별 원문을 제거했다. 요청에는 고정 지시문과 로컬 deterministic parser가 이미 추출한 허용된 `service_type` ID만 포함한다. 이름을 검출한 입력은 이전과 같이 원격 호출 없이 deterministic fallback으로 처리한다. |
| VC-UI-003 Hydration mismatch | **NOT_REPRODUCIBLE** | 저장값이 없는 첫 렌더와 저장 guard를 넣은 새로고침·복귀에서 브라우저 DOM/콘솔에 hydration mismatch가 관찰되지 않았다. guard UI는 접힌 비교 패널 안에 있어 초기 SSR/CSR markup에는 나타나지 않았다. 기존 lazy initializer는 브라우저 저장값과 서버 초기값이 다를 수 있는 잠재적 패턴이므로 SSR-safe `null` 초기값과 hydration 후 복원으로 바꿨다. |
| 저장소 접근 실패 시 쓰기 보호 | **CONFIRMED_AND_FIXED** | 이전 경로에서는 `sessionStorage` 접근 예외가 `null`로 처리되어 공급 일정 생성 버튼이 열렸다. 현재는 읽기/쓰기 probe 실패 시 `storage-unavailable` guard를 설정하고, 복원 완료 전 버튼과 handler 모두 쓰기를 차단한다. 불확실 상태에서는 해제 버튼을 노출하지 않는다. |

### 개인정보 및 구조화 회귀

합성 인명 11개 사례를 fake client로 확인했다. 조사·마침표·쉼표·줄바꿈·문장 끝·호칭/라벨·복합 성씨·외국인 이름·전화번호/주소 조합을 포함한다. 탐지된 입력은 원격 호출 횟수 0과 deterministic fallback을 확인했고, 탐지되지 않은 입력도 fake Gemini payload가 아래 고정 문자열과 일치하며 원문·이름·주소·전화번호가 전혀 포함되지 않음을 확인했다.

> Select only service types explicitly requested from these locally extracted candidate IDs. Do not add requests or infer missing information. Return only the supplied candidate service types. No resident source text is provided. Candidate service_type IDs: laundry

로컬 parser의 요청 후보, 스키마, `_matches_explicit_facts()`의 정확한 요청 집합 일치, 검증 가능한 날짜·빈도·제약 조건 덮어쓰기, deterministic fallback은 유지했다. 기존 수요 테스트에서 일반 명사·지명 오탐, 부정/취소, 상충 빈도, 잘못된 서비스 추가, PII 입력 fallback도 함께 확인했다. 탐지 가능한 인명 패턴은 완전하지 않다. 따라서 개인정보 안전성은 이름 정규식의 완전성에 의존하지 않고 Gemini로 원문을 전송하지 않는 구조로 보장한다.

### Hydration 및 쓰기 보호 회귀

SSR-safe 초기값과 복원 완료 ref/state를 추가했다. 복원이 끝나기 전에 공급 일정 생성 버튼은 비활성화되고 handler도 즉시 반환한다. 저장된 `ambiguous-write` 또는 `plans-created`는 새로고침·지역 변경·`/plans` 이동 후 복귀·뒤로 가기·같은 탭에서 연 새 탭에서도 유지되며 새 계획 POST가 0회임을 확인했다. sessionStorage 접근 실패에서는 화면 경고와 비활성 버튼을 확인했고, 강제 DOM click도 계획 POST를 발생시키지 않았다.

지연 POST 중 페이지 이동 시 후속 쓰기 중단 및 재진입 guard 복원, 기존 ambiguous 504 중복 쓰기 차단 Playwright 사례도 재실행해 통과했다. 저장소가 계속 차단되는 환경은 이전 쓰기 여부를 확인할 수 없으므로 생성 기능을 fail-closed로 잠근다. 정상 저장소 환경의 계획 생성 흐름은 최신 PR CI 전체 브라우저 검증에서 확인한다.

## 테스트 및 검토

| 검증 | 결과 |
|---|---|
| `uv run pytest tests/test_demand.py -q` | **63 passed**, third-party Swig deprecation warnings 3건 |
| `uv run ruff check backend/demand.py tests/test_demand.py` | **PASS** |
| Frontend ESLint | **PASS** |
| Frontend TypeScript | **PASS** |
| Frontend unit tests | **19 passed** |
| 신규 Hydration Playwright | **4 passed** |
| 지연 POST 이탈 / 504 중복 방지 Playwright | **2 passed** |
| Production build | `npm run build -- --webpack` 격리 scratch copy에서 **PASS**. 캐시 `node_modules` symlink 환경에서 standalone tracing 경고가 있었으며, 표준 CI 빌드 결과가 최종 기준이다. |
| 전체 backend/frontend, R1–R13 | v21 기준 CI run [41299517965](https://github.com/JongHyun070105/village-coverage/actions/runs/41299517965)에서 backend/frontend SUCCESS, backend 670 passed/1 skipped, R1–R13 13/13 PASS(113 tests), Playwright 기본 19 passed/1 skipped, Public Demo 14 passed, responsive UI 5 passed. **이번 수정 head의 새 CI 결과는 아래 상태를 확인할 것.** |
| 독립 리뷰 | 두 cross-provider read-only 리뷰 및 최종 Claude Sonnet 리뷰에서 P1/P2 추가 발견 없음. 검토자가 제안한 payload 단언 약점은 정확한 전체 고정 prompt 일치 assertion으로 보강했다. storage 차단 시 계속 잠기는 동작은 개인정보/중복 쓰기 불확실성을 피하기 위한 fail-closed 선택이다. |

최초 수정 head `f03e369708460c5d4c3f30b0088067d382377b7b`의 GitHub run [41318664422](https://github.com/JongHyun070105/village-coverage/actions/runs/41318664422)에서 frontend job은 lint, unit, typecheck, production build, standard/Public Demo Playwright 및 네 viewport responsive 검증까지 **SUCCESS**했다. Backend pytest는 **680 passed, 1 skipped, 1 failed**였다. 유일한 실패는 기존 `test_survey_audit_event_never_stores_free_text`가 전체 JSON에서 짧은 문자열 `010`을 금지해 무작위 event ID `f874271f72010`과 충돌한 것이었다. 실제 audit details는 `{"survey_type":"phone","service_type":"laundry"}`로 안전했다. 테스트는 허용된 details의 정확한 구조와 합성 원문·이름·전체 전화번호의 부재를 검사하도록 정밀화했다. 이 변경은 검증을 약화하지 않으며 최신 head CI에서 전체 pytest를 다시 확인한다.

이번 로컬 Playwright 실행은 테스트 파일을 저장소 밖 job 임시 디렉터리로 복사한 설정에서 `--webpack`을 지정했다. 기본 로컬 Turbopack은 외부 캐시 `node_modules` symlink를 따라 패키지를 확인하지 못해 서버 시작 단계에서 실패했다. 저장소 테스트 설정은 변경하지 않았고, 브라우저 테스트는 로컬 합성 API만 사용했다.

## GitHub 및 변경 경계

- PR #18은 확인 시점에 OPEN, base `main` (`99023e3f4cce4b2cb0e514e872c98b206b1a0d89`), head `c32df431fd9b99d8a9710a4b5e6607a4749d3ea0`이었다.
- 같은 확인에서 `origin/main`은 `99023e3f…`, PR branch는 `c32df431…`, `submission/public-demo-deploy`는 `36319c6551b5c80d3f8c4e1aaa43bc7bbf8fe6e3`였다.
- Primary checkout은 `fix/demand-negation-20261029`, HEAD `ce3bc40a1815b59f507a7b9cf2a95d32e1567d02`, dirty 경로 1,939개 상태를 유지했다. 수정은 별도 PR worktree에서만 수행했다.
- 새 보고서와 이번 수정은 기존 PR #18에만 반영한다. main 병합, 배포 브랜치 push, 공개 서비스 쓰기, Render 변경, DB/환경 변경은 하지 않았다.
- PR 병합 상태: **MERGE_PENDING**.

## CI 및 잔여 위험

- 최초 수정 커밋 `f03e369`: frontend CI **SUCCESS**, backend **680 passed / 1 skipped / 1 flaky assertion failure**. 그 실패는 요청 데이터 누출이 아니라 무작위 event ID와 짧은 숫자 substring 단언의 충돌이었다.
- 안정화된 audit assertion 수정은 별도 커밋/푸시 후 새 head CI에서 재검증한다.
- 필수 backend/frontend 최신 head CI: **대기**.
- 기존 보고서의 관련 없는 잔여 위험은 그대로 남아 있다: 검증된 운영자 인증 provider 부재에 따른 조건부 P1(non-demo staff workflow fail-closed), 전역 신규 세션 발급 제한 공정성 P2. 이번 diff의 직접 파생 결함은 아니다.
- 남은 인명 정규식 미탐 가능성은 식별할 수 없는 이름이 존재할 수 있다는 한계로 기록한다. 원문 Gemini 전달은 이제 탐지 여부와 무관하게 차단된다.

## 사용자 판단 질문

1. **개인정보 합성 문장이 Gemini로 전송되는가?** 현재 요청 payload에는 주민 문장이 전송되지 않는다. 일부 이름 패턴은 fake client 호출 자체가 0회이고, 미탐 패턴도 허용된 서비스 ID만 전달된다.
2. **정상 수요 분류는 유지되는가?** 로컬 parser가 구조화한 기존 서비스 후보·사실 검증·fallback을 보존했고 관련 63개 테스트가 통과했다.
3. **저장값 새로고침에서 hydration은 정상인가?** 브라우저 재현에서 warning/DOM mismatch는 확인되지 않았다. SSR-safe 복원 방식으로 잠재적 초기값 차이도 제거했다.
4. **복원 중 중복 계획 생성이 가능한가?** 복원 전 handler/button이 차단되며 저장 guard 복원·storage 오류·지연 POST/504 사례에서 중복 POST 0회를 확인했다.
5. **새 수정 회귀가 있는가?** 독립 리뷰 P1/P2 없음; 타깃 테스트 통과. 새 PR head 전체 CI 결과 확인이 남아 있다.
6. **PR #18을 안전하게 병합할 수 있는가?** 새 head의 필수 backend/frontend CI가 모두 SUCCESS로 확인된 뒤 판단할 수 있다. 지금은 **NO-GO / CI 대기**, merge는 수행하지 않는다.
