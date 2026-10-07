# Verified metrics — VillageCoverage V5.2 RC1

이 파일은 현재 release candidate에서 직접 확인한 수치의 단일 목록입니다. 코드와 acceptance 결과의 기준 커밋은 `fe2c10486b5f05559619e0cdbdb6b71ac1deb7e3`입니다. 이전 날짜의 감사 artifact는 역사 기록으로 보존하며 아래 수치와 섞지 않습니다.

## RC 회귀 결과

| 점검 | 현재 결과 | 재현 범위와 한계 |
|---|---|---|
| Backend | **562 passed, 1 skipped** | Python 3.12.2, `uv run --frozen pytest -q`. 경로가 필요한 테스트에는 공개 route matrix의 임시 읽기 전용 복사본을 사용했습니다. live 외부 API는 호출하지 않았습니다. |
| Proposal acceptance | **R1–R13 PASS, 112 passed** | `artifacts/proposal_acceptance_rc1.json`; source SHA와 파일 fingerprint 포함. 소프트웨어 요구 수용이지 현장 효과 검증은 아닙니다. |
| Browser E2E | **12 passed** | Chromium Playwright, 대시보드부터 조사·주민 의견·4안 비교·공급자 불참·재계획·승인·내보내기까지 synthetic 데이터로 실행했습니다. |
| External API failure matrix | **40 passed, 1 skipped** | `artifacts/external_api_failure_matrix_rc1.json`; mocked transport. live KOSIS/data.go.kr smoke는 opt-in이라 실행하지 않았습니다. |
| Synthetic pilot lifecycle | **1 passed** | `artifacts/pilot_rehearsal_rc1.json`; 동일 synthetic context에서 import·4안 계산·decline/replan·승인·execution·실적 연결. 실제 field result가 아닙니다. |
| Solver smoke | **30·50·100·200 지역, invariant 위반 0** | `artifacts/v5_2_solver_smoke_rc1.json`과 CSV. 30/100/200은 `TIME_LIMIT`, 50은 `OPTIMAL`; 시간 제한은 해결/최적성 통과로 세지 않습니다. synthetic road edges 사용. |
| Privacy regression | **22 passed** | Resident feedback, API error redaction, demand PII redaction 관련 테스트. 패턴 기반 masking은 완전 익명화가 아닙니다. |
| Accessibility E2E | **12개 전체 E2E 안의 자동 점검 통과** | keyboard/focus, accessible labels와 tables, 390/1024/1280/1440px 반응형 점검. screen-reader 사용자와의 수동 검증은 미실시. |
| Ruff / compileall | **PASS** | `uv run --frozen ruff check .`; `uv run --frozen python -m compileall backend scripts`. |
| Frontend lint / typecheck / build | **PASS** | `npm run lint`, `npm run typecheck`, `npm run build`; clean install 뒤 build에서 17개 app 경로 생성. |
| Demo launcher | **PASS** | `scripts/start_demo.sh`가 새 임시 app DB를 만들고 API와 대시보드 health check를 통과했습니다. 종료 후 임시 DB를 삭제하지 않습니다. 기존 route cache와 분리됩니다. |

Playwright 캡처와 SHA-256 목록은 [`artifacts/v5_2_rc1_visual_qa/manifest.json`](../artifacts/v5_2_rc1_visual_qa/manifest.json)에 있습니다. 캡처는 demo/synthetic 입력을 사용하며 발표용 최종 그래픽은 아닙니다.

## Clean setup와 의존성

검증용 임시 checkout에서 `uv sync --frozen --all-groups`는 Python 3.12.2에 lock된 **54개 패키지**를 설치했습니다. `npm ci`는 lockfile에서 **363개 패키지**를 설치했습니다. 프로젝트가 선언한 버전 범위는 Python `>=3.12,<3.15`, Node.js `>=20.9`입니다. `uv` 자체 버전은 저장소가 고정하지 않습니다.

- `npm audit --omit=dev`: **0 vulnerabilities**.
- 전체 npm audit: **5 high**, 전부 development-only Next/ESLint 도구 체인. lockfile에서 runtime `source-map-js`는 `1.2.2`로 패치했습니다. registry에 `braces` 수정판이 없어 안전한 현재 major 내 수정을 찾지 못했고, 제안된 major downgrade는 적용하지 않았습니다. 상세는 [`TECH_DEBT.md`](TECH_DEBT.md).
- 깨끗한 frozen Python 환경의 `pip-audit`: **known vulnerabilities 0** (2026-10-07 검사 시점 기준).
- 설치·정적 검사 결과는 취약점 부재의 영구 보증이 아닙니다. advisory database와 lockfile은 다음 릴리스 전 재확인해야 합니다.

## Secret / privacy boundary

`.env`에는 로컬 API key 값이 존재하지만 `.env`는 Git에 없고 ignored 상태입니다. `DATA_GO_KR_SERVICE_KEY`, `KOSIS_API_KEY`, `KAKAO_REST_API_KEY`, `NEXT_PUBLIC_KAKAO_MAP_JS_KEY`, `GEMINI_API_KEY`는 현재 checkout에서 `PRESENT / NOT_TRACKED`이며, 값 단위 scan에서 reachable Git history는 모두 `NOT_PRESENT`였습니다. 쿠키·토큰·비밀번호·browser auth 값은 tracked artifact에서 확인되지 않았습니다. scan에는 값이나 인증 정보를 저장하지 않았습니다.

## Data and field validation

- 데모 fixture는 3개 지역, 법정리 집계 54곳을 사용합니다. 시설 세부 행은 재사용 근거가 확인된 부여 자료 일부에 한정됩니다. 출처·날짜·재사용 범위·hash는 [`DATA_PROVENANCE.md`](DATA_PROVENANCE.md)와 `artifacts/provider_source_audit.json`에서 확인합니다.
- 공급자 디렉터리 ingested 범위는 자활기업과 마을기업입니다. 사회적기업 자료는 출처 파일 확인이 안 되어 미수집이며, 협동조합은 재사용 권리가 불명확해 차단했습니다.
- **Field validation: NOT_STARTED.** 실제 파일럿 기관, 승인된 기관 dataset, 공급자 운영 확인, 현장 실행 기록, 현장 보정, production 인증·인가, live API smoke, 수동 screen-reader QA는 완료되지 않았습니다.

## 브라우저 QA 이미지

[`artifacts/v5_2_rc1_visual_qa/`](../artifacts/v5_2_rc1_visual_qa/)에는 Dashboard, village/survey, scenario comparison, provider participation, replan, approval/history, schedule, data sources, mobile approval 화면 PNG와 manifest가 있습니다. 테스트가 통과했다는 것은 자동화된 prototype 동선이 동작했다는 뜻이며 기관 사용자 검증은 아닙니다.

## Main 통합 후 smoke

`main`은 `65db48287138cae3f676565dab1814f0ec375e11`까지 fast-forward 통합했습니다. push 후 `10df27f15ee068a2d11a1cdf651b10cc54bc52e6`에서도 backend 핵심 smoke **9 passed**, frontend lint/typecheck/build **PASS**(17개 경로 생성), R1–R13 acceptance **112 passed**를 재확인했고 당시 `origin/main`과 SHA가 일치했습니다. 이 검증을 기록한 뒤 추가된 변경은 evidence 문서와 JSON뿐이며 application source는 바뀌지 않았습니다. 전체 RC 회귀는 application source SHA `fe2c10486b5f05559619e0cdbdb6b71ac1deb7e3`에서 수행했고, main 통합은 별도의 역사 재작성 없이 같은 source commit을 포함합니다.
