# 실제 화면 캡처 출처

- 캡처 일자: 2026-10-13
- 소스 코드: `security/release-readiness-20261012` 기반 SHA `b6ff52adb2fa8b4287e6c62250802d8c07196907`
- 실행: `frontend/e2e/public-sector-workflow.spec.ts` — 로컬 Playwright, 격리 임시 DB와 고정 합성 route fixture, 외부 Gemini 키 없음.
- 상태: 1 E2E 통과. 테스트가 앱 코드와 브라우저 화면을 직접 실행한 결과다.
- 원본 캡처: `source/dashboard.png`, `source/scenario-comparison.png`, `source/plan-replanned.png`.
- PPT 안의 이미지: 이 캡처의 직접 crop이며 UI를 다시 그리거나 수치를 덧씌우지 않았다.
- 한계: 원격 Render 배포본의 캡처가 아니다. 원격 첫 화면의 데이터 재조회가 두 차례 실패했으므로 원격 전체 흐름은 `NOT_VERIFIABLE`.
- 테스트는 합성 데이터를 쓰며 실제 주민, 제공자, 계약, 서비스 이행, 행정 승인을 증명하지 않는다.
